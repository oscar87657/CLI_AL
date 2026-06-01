from __future__ import annotations

from fastapi import APIRouter

from app.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, object]:
    s = get_settings()
    return {
        "status": "ok",
        "upstage_configured": bool(s.upstage_api_key),
        "supabase_configured": bool(s.supabase_url and s.supabase_secret_key),
        "model": s.solar_model,
    }
