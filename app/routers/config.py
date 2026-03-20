"""
app/routers/config.py
──────────────────────
Lightweight API endpoints the frontend uses to:
  • Fetch on-prem model configuration (from .env)
  • Health check
  • View request audit logs (admin use)
"""

from __future__ import annotations
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.config import Settings, get_settings
from app.database import get_db, RequestLog
from app.schemas import AppConfig, OnPremConfig

router = APIRouter(prefix="/api")


@router.get("/health", summary="Health check")
async def health(settings: Settings = Depends(get_settings)):
    return {
        "status": "ok",
        "app": "velocis-intelli-agent",
        "ai_defense_mode": settings.ai_defense_mode,
        "ai_defense_configured": bool(
            settings.ai_defense_api_key or settings.ai_defense_mode == "gateway"
        ),
        "llm_provider": settings.llm_provider,
        "onprem_model": settings.onprem_model_name,
    }


@router.get("/config", response_model=AppConfig, summary="App config for frontend")
async def get_config(settings: Settings = Depends(get_settings)):
    """
    Returns non-sensitive configuration that the frontend needs —
    specifically the on-prem model name so the UI can display it.
    API keys are NEVER exposed.
    """
    return AppConfig(
        onprem=OnPremConfig(
            model_name=settings.onprem_model_name,
            base_url=settings.onprem_base_url,
            has_api_key=bool(settings.onprem_api_key),
        ),
        ai_defense_mode=settings.ai_defense_mode,
        ai_defense_configured=bool(
            settings.ai_defense_api_key or settings.ai_defense_mode == "gateway"
        ),
    )


@router.get("/logs", summary="Request audit logs (last 100)")
async def get_logs(
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    """Returns the last N request logs for audit/debug purposes."""
    result = await db.execute(
        select(RequestLog)
        .order_by(RequestLog.created_at.desc())
        .limit(limit)
    )
    logs = result.scalars().all()
    return [
        {
            "id": log.id,
            "created_at": log.created_at.isoformat() if log.created_at else None,
            "source_ip": log.source_ip,
            "http_status": log.http_status,
            "blocked": log.blocked,
            "block_stage": log.block_stage,
            "latency_ms": log.latency_ms,
            "defense_input": log.defense_input_result,
            "defense_output": log.defense_output_result,
        }
        for log in logs
    ]


@router.get("/stats", summary="Session statistics")
async def get_stats(db: AsyncSession = Depends(get_db)):
    """Aggregate statistics from request logs."""
    total = await db.scalar(select(func.count()).select_from(RequestLog))
    blocked = await db.scalar(
        select(func.count()).select_from(RequestLog).where(RequestLog.blocked == True)
    )
    return {
        "total_requests": total or 0,
        "blocked_requests": blocked or 0,
        "passed_requests": (total or 0) - (blocked or 0),
    }
