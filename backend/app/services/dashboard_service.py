"""Aggregated dashboard statistics derived from stored records (no mock data)."""

from __future__ import annotations

from statistics import mean

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    Analysis,
    AnalysisStatus,
    BenchmarkRun,
    CoverageSnapshot,
    Repository,
    TestRun,
)


class DashboardService:
    async def stats(self, db: AsyncSession) -> dict:
        repositories = await db.scalar(select(func.count()).select_from(Repository)) or 0
        analyses = await db.scalar(select(func.count()).select_from(Analysis)) or 0
        completed = (
            await db.scalar(
                select(func.count())
                .select_from(Analysis)
                .where(Analysis.status == AnalysisStatus.COMPLETED)
            )
            or 0
        )
        benchmarks = await db.scalar(select(func.count()).select_from(BenchmarkRun)) or 0
        test_runs = await db.scalar(select(func.count()).select_from(TestRun)) or 0
        coverage = await db.scalar(select(func.count()).select_from(CoverageSnapshot)) or 0

        analysis_rows = list(
            (
                await db.execute(
                    select(Analysis)
                    .where(Analysis.status == AnalysisStatus.COMPLETED)
                    .order_by(Analysis.created_at.desc())
                    .limit(200)
                )
            )
            .scalars()
            .all()
        )
        durations = [
            a.analysis_duration_ms for a in analysis_rows if a.analysis_duration_ms
        ]
        reductions: list[float] = []
        for analysis in analysis_rows:
            selection = analysis.test_recommendations or {}
            optimized = selection.get("optimized") or {}
            value = optimized.get("reduction_percent")
            if isinstance(value, (int, float)):
                reductions.append(float(value))

        repo_ids = list((await db.execute(select(Repository.id))).scalars().all())
        tracked_tests = 0
        for repo_id in repo_ids:
            snapshot = await db.scalar(
                select(CoverageSnapshot)
                .where(
                    CoverageSnapshot.repository_id == repo_id,
                    CoverageSnapshot.status.in_(("completed", "partial")),
                )
                .order_by(CoverageSnapshot.collected_at.desc())
                .limit(1)
            )
            if snapshot:
                tracked_tests += snapshot.measured_tests or 0

        recent_analyses = list(
            (
                await db.execute(
                    select(Analysis).order_by(Analysis.created_at.desc()).limit(5)
                )
            )
            .scalars()
            .all()
        )
        recent_benchmarks = list(
            (
                await db.execute(
                    select(BenchmarkRun)
                    .order_by(BenchmarkRun.created_at.desc())
                    .limit(5)
                )
            )
            .scalars()
            .all()
        )

        return {
            "repositories": repositories,
            "analyses": analyses,
            "completed_analyses": completed,
            "benchmark_runs": benchmarks,
            "test_runs": test_runs,
            "coverage_snapshots": coverage,
            "total_tracked_tests": tracked_tests,
            "average_analysis_ms": round(mean(durations), 1) if durations else None,
            "average_selection_reduction": (
                round(mean(reductions), 1) if reductions else None
            ),
            "recent_analyses": recent_analyses,
            "recent_benchmarks": recent_benchmarks,
        }
