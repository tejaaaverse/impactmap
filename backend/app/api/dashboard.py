"""Dashboard aggregate API."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.schemas import (
    AnalysisResponse,
    BenchmarkResponse,
    DashboardStatsResponse,
)
from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/api", tags=["Dashboard"])

_dashboard_service = DashboardService()


@router.get("/dashboard", response_model=DashboardStatsResponse)
async def dashboard(db: AsyncSession = Depends(get_db)):
    """Real, database-derived counts and recent activity.

    Nothing in this response is hardcoded; averages are computed from stored
    analysis and benchmark records.
    """
    stats = await _dashboard_service.stats(db)
    stats["recent_analyses"] = [
        AnalysisResponse.model_validate(item) for item in stats["recent_analyses"]
    ]
    stats["recent_benchmarks"] = [
        BenchmarkResponse.model_validate(item) for item in stats["recent_benchmarks"]
    ]
    return DashboardStatsResponse.model_validate(stats)
