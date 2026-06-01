"""Supabase persistence for /rewrite history."""

from __future__ import annotations

import logging
from typing import Any

from app.models.schemas import (
    ChecklistItem,
    GlossaryTerm,
    GroundednessResult,
    HistoryDetail,
    HistoryItem,
    HistoryResponse,
    KeyInfoItem,
    RewriteResponse,
)
from app.services.supabase_client import get_supabase

logger = logging.getLogger(__name__)


def save_rewrite(original_text: str, response: RewriteResponse) -> str | None:
    """Persist a rewrite to Supabase. Returns the document_id, or None on failure."""
    sb = get_supabase()
    if sb is None:
        return None

    document_id: str | None = None
    try:
        doc = (
            sb.table("documents")
            .insert({"original_text": original_text})
            .execute()
        )
        document_id = doc.data[0]["id"] if doc.data else None
        if not document_id:
            logger.warning("documents insert returned no id")
            return None

        sb.table("rewrites").insert(
            {
                "document_id": document_id,
                "rewrite_text": response.rewrite,
                "citations": response.citations,
                "glossary": [g.model_dump() for g in response.glossary],
                "key_info": [k.model_dump() for k in response.key_info],
                "checklist": [c.model_dump() for c in response.checklist],
                "groundedness_label": response.groundedness.label,
                "groundedness_badge": response.groundedness.badge,
            }
        ).execute()
        return str(document_id)
    # TODO: 완전한 원자성을 위해서는 Supabase RPC로 전환 필요
    # 현재는 rewrites 실패 시 documents를 수동 삭제하는 보상 트랜잭션으로 처리
    except Exception as e:  # noqa: BLE001 — persistence failure shouldn't block response
        logger.warning("save_rewrite failed: %s", e)
        if document_id:
            try:
                sb.table("documents").delete().eq("id", document_id).execute()
            except Exception as cleanup_err:  # noqa: BLE001
                logger.warning("save_rewrite cleanup (document rollback) failed: %s", cleanup_err)
        return None


def list_history(limit: int = 20) -> HistoryResponse:
    sb = get_supabase()
    if sb is None:
        return HistoryResponse(items=[])
    try:
        # Join rewrites with documents via FK
        result = (
            sb.table("rewrites")
            .select("id, created_at, rewrite_text, groundedness_label, documents(original_text)")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        items: list[HistoryItem] = []
        for row in result.data or []:
            doc: dict[str, Any] = row.get("documents") or {}
            original = doc.get("original_text") or ""
            items.append(
                HistoryItem(
                    id=str(row["id"]),
                    created_at=str(row["created_at"]),
                    original_text_preview=(original[:100] + "...") if len(original) > 100 else original,
                    rewrite_preview=(row["rewrite_text"][:100] + "...")
                    if len(row["rewrite_text"]) > 100
                    else row["rewrite_text"],
                    groundedness_label=row.get("groundedness_label") or "notSure",
                )
            )
        return HistoryResponse(items=items)
    except Exception as e:  # noqa: BLE001
        logger.warning("list_history failed: %s", e)
        return HistoryResponse(items=[])


def delete_history(rewrite_id: str) -> bool:
    """이력(rewrite + 연결된 document) 삭제.

    documents → rewrites 는 ON DELETE CASCADE 라 document 한 번 삭제로 양쪽 모두 정리됨.
    rewrite_id 가 존재하지 않으면 False.
    """
    sb = get_supabase()
    if sb is None:
        return False
    try:
        r = (
            sb.table("rewrites")
            .select("document_id")
            .eq("id", rewrite_id)
            .limit(1)
            .execute()
        )
        rows = r.data or []
        if not rows:
            return False
        doc_id = rows[0].get("document_id")
        if not doc_id:
            # 안전망: document_id 가 비어 있으면 rewrite 만이라도 지움
            sb.table("rewrites").delete().eq("id", rewrite_id).execute()
            return True
        sb.table("documents").delete().eq("id", doc_id).execute()
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("delete_history failed: %s", e)
        return False


def get_history_detail(rewrite_id: str) -> HistoryDetail | None:
    sb = get_supabase()
    if sb is None:
        return None
    try:
        result = (
            sb.table("rewrites")
            .select(
                "id, created_at, rewrite_text, citations, glossary, key_info, "
                "checklist, groundedness_label, groundedness_badge, "
                "documents(original_text)"
            )
            .eq("id", rewrite_id)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        if not rows:
            return None
        row = rows[0]
        doc: dict[str, Any] = row.get("documents") or {}
        label = row.get("groundedness_label") or "notSure"
        badge = row.get("groundedness_badge") or "medium"
        return HistoryDetail(
            id=str(row["id"]),
            created_at=str(row["created_at"]),
            original_text=doc.get("original_text") or "",
            rewrite=row.get("rewrite_text") or "",
            citations=list(row.get("citations") or []),
            glossary=[GlossaryTerm(**g) for g in (row.get("glossary") or [])],
            key_info=[KeyInfoItem(**k) for k in (row.get("key_info") or [])],
            checklist=[ChecklistItem(**c) for c in (row.get("checklist") or [])],
            groundedness=GroundednessResult(label=label, badge=badge, score=None),
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("get_history_detail failed: %s", e)
        return None
