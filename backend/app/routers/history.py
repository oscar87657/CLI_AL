from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.models.schemas import HistoryDetail, HistoryResponse
from app.services.history_service import (
    delete_history,
    get_history_detail,
    list_history,
)

router = APIRouter(prefix="/history", tags=["history"])


@router.get("", response_model=HistoryResponse)
def get_history(limit: int = Query(default=20, ge=1, le=100)) -> HistoryResponse:
    return list_history(limit=limit)


@router.get("/{rewrite_id}", response_model=HistoryDetail)
def get_one(rewrite_id: str) -> HistoryDetail:
    detail = get_history_detail(rewrite_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="이력을 찾을 수 없습니다.")
    return detail


@router.delete("/{rewrite_id}", status_code=204)
def delete_one(rewrite_id: str) -> None:
    delete_history(rewrite_id)
    return None
