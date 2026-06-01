from typing import Literal

from pydantic import BaseModel, Field


class RewriteRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20000, description="원본 행정문서 텍스트")
    save_history: bool = Field(default=True, description="Supabase 이력 저장 여부")


class RelevanceResult(BaseModel):
    """관련성 판별 LLM(Call 0) 결과."""

    is_relevant: bool = Field(description="행정문서 여부")
    confidence: Literal["high", "medium", "low"] = Field(
        default="medium", description="판단 확신도"
    )
    reason: str | None = Field(
        default=None, description="판단 근거 한 문장 (30자 이내)"
    )


class GlossaryTerm(BaseModel):
    term: str
    definition: str
    example: str | None = None
    related_terms: list[str] = Field(default_factory=list, description="BFS로 찾은 연관 용어 목록")


KeyInfoType = Literal["의무", "권리", "기한", "금액", "연락처"]


class KeyInfoItem(BaseModel):
    type: KeyInfoType
    content: str
    deadline: str | None = None
    amount: str | None = None
    contact: str | None = None


class ChecklistItem(BaseModel):
    text: str
    priority: Literal["high", "medium", "low"] = "medium"


class GroundednessResult(BaseModel):
    label: Literal["grounded", "notGrounded", "notSure"]
    score: float | None = None
    badge: Literal["high", "medium", "low"]


class RewriteResponse(BaseModel):
    rewrite: str = Field(description="쉬운말로 재작성된 본문 (인용 마커 [1] [2] 포함)")
    citations: list[str] = Field(
        default_factory=list,
        description="인용 마커 번호 순으로 원문 발췌 텍스트",
    )
    glossary: list[GlossaryTerm] = Field(default_factory=list)
    key_info: list[KeyInfoItem] = Field(default_factory=list)
    checklist: list[ChecklistItem] = Field(default_factory=list)
    groundedness: GroundednessResult
    preservation_ratio: float | None = Field(
        default=None,
        description="LCS 기반 원문 보존율 (0~1). 단어 단위 LCS / max(원문단어수, 재작성단어수)",
    )
    summary: str | None = Field(
        default=None,
        description="결과 본문을 30자 안팎 한 문장으로 요약한 헤드라인 (chat_text 보조 호출)",
    )
    relevance: RelevanceResult | None = Field(
        default=None,
        description="Call 0 관련성 판별 결과. is_relevant=false 이면 조기 반환.",
    )
    document_id: str | None = Field(
        default=None, description="Supabase에 저장된 documents.id (저장 안 했으면 null)"
    )


class HistoryItem(BaseModel):
    id: str
    created_at: str
    original_text_preview: str
    rewrite_preview: str
    groundedness_label: str


class HistoryResponse(BaseModel):
    items: list[HistoryItem]


class HistoryDetail(BaseModel):
    """단일 이력 전체 — 변환 페이지에서 결과를 복원할 때 사용."""

    id: str
    created_at: str
    original_text: str
    rewrite: str
    citations: list[str] = Field(default_factory=list)
    glossary: list[GlossaryTerm] = Field(default_factory=list)
    key_info: list[KeyInfoItem] = Field(default_factory=list)
    checklist: list[ChecklistItem] = Field(default_factory=list)
    groundedness: GroundednessResult


class ParseResponse(BaseModel):
    text: str = Field(description="Document Parse가 추출한 Markdown 본문")
    char_count: int
