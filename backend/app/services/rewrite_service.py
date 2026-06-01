"""Orchestration for the /rewrite endpoint.

Four-call rewrite pipeline
---------------------------
Call 0  relevance_check_v1 — classifies whether the input is an administrative
                              document. Short-circuits with a guidance message
                              if is_relevant=false; result is never persisted.
Call 1  rewrite_v2          — focused rewrite + citations only.
                              RAG context (up to 3 related chunks) is injected
                              into the user message before this call.
Call 2  analysis_v1         — glossary + key_info + checklist.
                              Receives both original text AND the rewrite result
                              so glossary definitions match the rewrite's wording.
Call 3  summary (inline)    — condenses the rewrite into a single sentence
                              (≤30 chars) for the history list preview.

RAG flow
--------
1. hybrid_search() BEFORE indexing → avoids returning the current text
   as its own top result.
2. index_text() AFTER a successful rewrite → accumulates corpus for
   future requests.
"""

from __future__ import annotations

import logging
from typing import Any

from app.config import get_settings
from app.models.schemas import (
    ChecklistItem,
    GlossaryTerm,
    GroundednessResult,
    KeyInfoItem,
    RelevanceResult,
    RewriteResponse,
)
from app.rag.indexer import format_rag_context, index_text
from app.rag.retriever import hybrid_search
from app.rag.store import get_store
from app.services.algorithms import (
    bfs_related_terms,
    build_term_graph,
    counting_sort_checklist,
    dedup_glossary,
    lcs_word_ratio,
    merge_sort_glossary,
)
from app.services.cache_service import HashTableCache
from app.services.prompt_loader import load_prompt
from app.services.upstage_client import get_upstage

logger = logging.getLogger(__name__)

# CLRS 11.2 / 11.3.1 — hash table with chaining, division method
_cache = HashTableCache(table_size=256, max_entries=128, ttl_seconds=3600.0)

_ESCAPED_NEWLINE: str = chr(92) + chr(110)  # literal backslash + n as emitted by some LLMs
_REAL_NEWLINE: str = chr(10)                # actual line-feed character


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _label_to_badge(label: str) -> str:
    """Map Groundedness label to UI badge level."""
    if label == "grounded":
        return "high"
    if label == "notSure":
        return "medium"
    return "low"


def _safe_list(raw: Any, key: str) -> list[Any]:
    val = raw.get(key) if isinstance(raw, dict) else None
    return val if isinstance(val, list) else []


def _sanitize(value: object) -> str:
    """Strip whitespace; replace literal backslash-n sequences with real newlines.

    LLMs sometimes emit JSON strings where a newline was encoded as the literal
    two-character sequence backslash + n instead of a real line-feed character.
    This helper normalises both cases and strips surrounding whitespace so that
    callers can use ``if not _sanitize(v)`` to drop blank values.
    """
    if not isinstance(value, str):
        value = str(value)
    value = value.replace(_ESCAPED_NEWLINE, _REAL_NEWLINE)
    return value.strip()


_SUMMARY_SYSTEM = (
    "다음 문장을 30자 안팎 한 문장으로 요약하세요. "
    "핵심 의무·기한·금액을 우선 살리고, 인용 마커([1] 등)와 따옴표·괄호 메모는 빼세요. "
    "결과는 한 문장만, 추가 설명 없이 본문 텍스트만 출력하세요."
)


def _generate_summary(rewrite_text: str) -> str | None:
    """chat_text 보조 호출 — 본문을 한 줄로 요약. 실패 시 None."""
    text = rewrite_text.strip()
    if not text:
        return None
    try:
        upstage = get_upstage()
        out = upstage.chat_text(system=_SUMMARY_SYSTEM, user=text, temperature=0.2)
        # 첫 줄만, 좌우 공백/따옴표 제거, 60자 캡 (UI safety)
        first = out.strip().splitlines()[0] if out.strip() else ""
        first = first.strip().strip('"').strip("'")
        return first[:60] if first else None
    except Exception as e:  # noqa: BLE001 — 요약 실패는 결과 차단 사유 아님
        logger.warning("summary generation failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# Call 0: Relevance check
# ---------------------------------------------------------------------------

_NOT_RELEVANT_BADGE = GroundednessResult(label="notSure", score=None, badge="low")
_NOT_RELEVANT_REWRITE = (
    "입력하신 내용이 행정문서·공문·약관·계약서가 아닌 것 같아요. "
    "변환하고 싶은 행정문서 텍스트를 붙여 넣어 주세요."
)


def check_relevance(text: str, upstage: object) -> RelevanceResult:
    """Call 0: LLM으로 입력 텍스트가 행정문서인지 판별.

    응답 JSON: { "is_relevant": bool, "confidence": str, "reason": str }
    파싱 실패나 예외 발생 시 is_relevant=True (false negative 방지) 로 복원.
    """
    system = load_prompt("relevance_check_v1")
    try:
        raw = upstage.chat_json(  # type: ignore[attr-defined]
            system=system,
            user=text,
            temperature=0.0,
            max_tokens=128,
        )
        is_rel = bool(raw.get("is_relevant", True))
        confidence_raw = raw.get("confidence", "medium")
        confidence = confidence_raw if confidence_raw in {"high", "medium", "low"} else "medium"
        reason = _sanitize(raw.get("reason") or "")
        result = RelevanceResult(
            is_relevant=is_rel,
            confidence=confidence,  # type: ignore[arg-type]
            reason=reason or None,
        )
        logger.info(
            "Relevance check: is_relevant=%s confidence=%s reason=%s",
            result.is_relevant,
            result.confidence,
            result.reason,
        )
        return result
    except Exception as e:  # noqa: BLE001 — 판별 실패 시 true로 복원 (false negative 방지)
        logger.warning("Relevance check failed (defaulting to relevant): %s", e)
        return RelevanceResult(is_relevant=True, confidence="low", reason=None)


def _build_rewrite_user_message(text: str, rag_context: str) -> str:
    """User message for Call 1: inject RAG context block when available."""
    if rag_context:
        return (
            "[참고 자료 - 법제처 어려운 표현 정비 사례]\n"
            f"{rag_context}\n\n"
            "[변환할 원문]\n"
            f"{text}"
        )
    return text


def _build_analysis_user_message(original: str, rewrite: str) -> str:
    """User message for Call 2: original + rewrite so glossary matches rewrite wording."""
    return f"[원문]\n{original}\n\n[재작성 결과]\n{rewrite}"


# ---------------------------------------------------------------------------
# Call-2 parse helpers
# ---------------------------------------------------------------------------

def _parse_glossary(raw: dict) -> list[GlossaryTerm]:
    """Extract and validate the glossary list from a raw analysis response dict.

    Ch. 11.2 - deduplication via hash table chaining, then Ch. 2.3 - merge sort.
    """
    glossary: list[GlossaryTerm] = []
    for g in _safe_list(raw, "glossary"):
        if not isinstance(g, dict):
            continue
        term = _sanitize(g.get("term") or "")
        definition = _sanitize(g.get("definition") or "")
        if not term or not definition:
            continue
        glossary.append(
            GlossaryTerm(
                term=term,
                definition=definition,
                example=(_sanitize(ex) if (ex := g.get("example")) else None) or None,
            )
        )
    # Ch. 11.2 — remove duplicates via hash table chaining, then Ch. 2.3 — merge sort
    return merge_sort_glossary(dedup_glossary(glossary))


def _parse_key_info(raw: dict) -> list[KeyInfoItem]:
    """Extract and validate the key_info list from a raw analysis response dict."""
    key_info: list[KeyInfoItem] = []
    for k in _safe_list(raw, "key_info"):
        if not isinstance(k, dict):
            continue
        kt = k.get("type")
        content = _sanitize(k.get("content") or "")
        if kt not in {"의무", "권리", "기한", "금액", "연락처"} or not content:
            continue
        key_info.append(
            KeyInfoItem(
                type=kt,  # type: ignore[arg-type]
                content=content,
                deadline=k.get("deadline"),
                amount=k.get("amount"),
                contact=k.get("contact"),
            )
        )
    return key_info


def _parse_checklist(raw: dict) -> list[ChecklistItem]:
    """Extract and validate the checklist list from a raw analysis response dict.

    Ch. 8.2 - stable sort high to medium to low in O(n + k).
    """
    checklist: list[ChecklistItem] = []
    for c in _safe_list(raw, "checklist"):
        if not isinstance(c, dict):
            continue
        ct = _sanitize(c.get("text") or "")
        if not ct:
            continue
        priority = c.get("priority")
        if priority not in {"high", "medium", "low"}:
            priority = "medium"
        checklist.append(ChecklistItem(text=ct, priority=priority))
    # Ch. 8.2 — stable sort high → medium → low in Θ(n + k)
    return counting_sort_checklist(checklist)


def _run_groundedness(text: str, rewrite_text: str, upstage: object) -> GroundednessResult:
    """Call the Upstage Groundedness API and return a GroundednessResult.

    Falls back to notSure / low on any exception so callers never crash.
    """
    try:
        gnd = upstage.groundedness_check(context=text, answer=rewrite_text)
        label = gnd["label"]
    except Exception as e:  # noqa: BLE001 — surface as low-confidence, never crash
        logger.warning("Groundedness check failed: %s", e)
        label = "notSure"
    
    badge = _label_to_badge(label)
    return GroundednessResult(label=label, score=None, badge=badge)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_rewrite(text: str) -> RewriteResponse:
    cached = _cache.get(text)
    if cached is not None:
        return cached

    settings = get_settings()
    upstage = get_upstage()
    store = get_store()

    # ── Call 0: relevance check ────────────────────────────────────────────────
    relevance = check_relevance(text, upstage)
    if not relevance.is_relevant:
        return RewriteResponse(
            rewrite=_NOT_RELEVANT_REWRITE,
            citations=[],
            glossary=[],
            key_info=[],
            checklist=[],
            groundedness=_NOT_RELEVANT_BADGE,
            preservation_ratio=None,
            summary=None,
            relevance=relevance,
        )

    # ── RAG: retrieve related chunks BEFORE indexing (no self-reference) ──────
    rag_results = hybrid_search(text, store, n=3)
    rag_context = format_rag_context(rag_results)
    if rag_context:
        logger.info(
            "RAG: %d chunk(s) passed relevance threshold (scores: %s)",
            len(rag_results),
            [f"{s:.3f}" for _, s in rag_results],
        )
    else:
        logger.info("RAG: no chunks cleared relevance threshold — proceeding without context")

    # ── Call 1: rewrite + citations (focused) ─────────────────────────────────
    system_rewrite = load_prompt("rewrite_v2")
    user_rewrite = _build_rewrite_user_message(text, rag_context)
    raw_rewrite = upstage.chat_json(system=system_rewrite, user=user_rewrite)

    rewrite_text = _sanitize(raw_rewrite.get("rewrite", "") if isinstance(raw_rewrite, dict) else "")
    citations = [s for c in _safe_list(raw_rewrite, "citations") if (s := _sanitize(c))]

    if not rewrite_text:
        logger.warning("Call 1 returned empty rewrite — skipping Call 2")
        return RewriteResponse(
            rewrite="",
            citations=citations,
            glossary=[],
            key_info=[],
            checklist=[],
            groundedness=_NOT_RELEVANT_BADGE,
            preservation_ratio=None,
            summary=None,
            relevance=relevance,
        )

    # ── Call 2: glossary + key_info + checklist ────────────────────────────────
    system_analysis = load_prompt("analysis_v1")
    user_analysis = _build_analysis_user_message(text, rewrite_text)
    raw_analysis = upstage.chat_json(system=system_analysis, user=user_analysis)

    glossary = _parse_glossary(raw_analysis)
    key_info = _parse_key_info(raw_analysis)
    checklist = _parse_checklist(raw_analysis)

    # Ch. 15.4 — word-level LCS preservation ratio (original vs rewrite)
    preservation_ratio = lcs_word_ratio(text, rewrite_text)
    logger.info("LCS preservation_ratio=%.4f", preservation_ratio)

    # Ch. 22.1 + 22.2 — build term dependency graph, BFS-attach related_terms
    term_graph = build_term_graph(glossary)
    for gt in glossary:
        gt.related_terms = bfs_related_terms(term_graph, gt.term)

    # ── Groundedness check ─────────────────────────────────────────────────────
    groundedness = _run_groundedness(text, rewrite_text, upstage)

    # ── Summary (보조 호출) ────────────────────────────────────────────────────
    summary = _generate_summary(rewrite_text)

    # ── RAG: index current text for future retrievals ──────────────────────────
    try:
        added = index_text(text, store)
        logger.info("RAG: indexed %d chunk(s) from current request", len(added))
    except Exception as e:  # noqa: BLE001
        logger.warning("RAG indexing failed (non-fatal): %s", e)

    result = RewriteResponse(
        rewrite=rewrite_text,
        citations=citations,
        glossary=glossary,
        key_info=key_info,
        checklist=checklist,
        groundedness=groundedness,
        preservation_ratio=preservation_ratio,
        summary=summary,
        relevance=relevance,
    )
    _cache.put(text, result)
    return result
