"""Impact analysis orchestration and persistence."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.logging import logger
from app.core.security import PathValidationError, validate_repository_path
from app.engine.git.change_detector import GitDetectionError
from app.models.models import Analysis, AnalysisStatus, CoverageSnapshot, Repository, TestRun
from app.services.analysis_pipeline import AnalysisPipeline, run_analysis_pipeline
from app.services.repository_service import RepositoryService


@dataclass
class PreparedAnalysis:
    repository: Repository
    pipeline: AnalysisPipeline
    coverage_snapshot: CoverageSnapshot | None
    historical_failures: list[str]


class AnalysisService:
    """Run analyses and persist their full evidence trail."""

    def __init__(self) -> None:
        self.repositories = RepositoryService()

    async def get_repository(self, db: AsyncSession, repo_id: str) -> Repository | None:
        return await self.repositories.get_repository(db, repo_id)

    async def latest_coverage(
        self, db: AsyncSession, repo_id: str
    ) -> CoverageSnapshot | None:
        stmt = (
            select(CoverageSnapshot)
            .where(
                CoverageSnapshot.repository_id == repo_id,
                CoverageSnapshot.status.in_(("completed", "partial")),
            )
            .order_by(CoverageSnapshot.collected_at.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def latest_failed_tests(
        self, db: AsyncSession, repo_id: str
    ) -> list[str]:
        stmt = (
            select(TestRun)
            .where(TestRun.repository_id == repo_id)
            .order_by(TestRun.created_at.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        run = result.scalar_one_or_none()
        if not run or not run.results:
            return []
        failed: list[str] = []
        for item in run.results:
            if not isinstance(item, dict):
                continue
            if item.get("status") in ("FAILED", "ERROR"):
                test_id = item.get("test_id")
                if test_id:
                    failed.append(str(test_id))
        return failed

    async def prepare(
        self,
        db: AsyncSession,
        repo_id: str,
        base_ref: str,
        head_ref: str,
        *,
        include_tests: bool = False,
    ) -> PreparedAnalysis:
        repo = await self.get_repository(db, repo_id)
        if not repo:
            raise LookupError("Repository not found")

        try:
            validate_repository_path(repo.path)
        except PathValidationError as exc:
            raise ValueError(str(exc)) from exc

        coverage = await self.latest_coverage(db, repo_id)
        historical = await self.latest_failed_tests(db, repo_id)

        pipeline = await run_in_threadpool(
            run_analysis_pipeline,
            repo.path,
            base_ref,
            head_ref,
            include_tests=include_tests,
            coverage_data=coverage.data if coverage else None,
            historical_failures=historical,
        )
        return PreparedAnalysis(
            repository=repo,
            pipeline=pipeline,
            coverage_snapshot=coverage,
            historical_failures=historical,
        )

    async def persist_analysis(
        self,
        db: AsyncSession,
        repo_id: str,
        base_ref: str,
        head_ref: str,
        pipeline: AnalysisPipeline,
        *,
        status: AnalysisStatus = AnalysisStatus.COMPLETED,
        error_message: str | None = None,
    ) -> Analysis:
        impact = pipeline.impact.to_dict()
        selection = pipeline.selection.to_dict()
        analysis = Analysis(
            repository_id=repo_id,
            status=status,
            base_ref=base_ref,
            head_ref=head_ref,
            changed_files=impact.get("changed_files", []),
            changed_entities=impact.get("changed_entities", []),
            impact_results=impact,
            test_recommendations=selection,
            total_changed_files=len(pipeline.changeset.files),
            total_affected_entities=impact.get("summary", {}).get("total_affected", 0),
            analysis_duration_ms=pipeline.duration_ms,
            error_message=error_message,
            completed_at=datetime.now(timezone.utc),
        )
        db.add(analysis)
        await db.flush()
        logger.info(
            "Analysis persisted: %s (%d changed files, %d affected entities)",
            analysis.id,
            analysis.total_changed_files,
            analysis.total_affected_entities,
        )
        return analysis

    async def run(
        self,
        db: AsyncSession,
        repo_id: str,
        base_ref: str,
        head_ref: str,
        *,
        include_tests: bool = False,
    ) -> tuple[Analysis, AnalysisPipeline]:
        prepared = await self.prepare(
            db,
            repo_id,
            base_ref,
            head_ref,
            include_tests=include_tests,
        )
        analysis = await self.persist_analysis(
            db, repo_id, base_ref, head_ref, prepared.pipeline
        )
        return analysis, prepared.pipeline

    async def get(self, db: AsyncSession, analysis_id: str) -> Analysis | None:
        stmt = select(Analysis).where(Analysis.id == analysis_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def list(
        self,
        db: AsyncSession,
        *,
        repository_id: str | None = None,
        limit: int = 50,
    ) -> list[Analysis]:
        stmt = select(Analysis).order_by(Analysis.created_at.desc()).limit(limit)
        if repository_id:
            stmt = stmt.where(Analysis.repository_id == repository_id)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def require(self, db: AsyncSession, analysis_id: str) -> Analysis:
        analysis = await self.get(db, analysis_id)
        if not analysis:
            raise LookupError("Analysis not found")
        return analysis


def analysis_detail_dict(analysis: Analysis) -> dict[str, Any]:
    """Merge stored analysis JSON into an API-ready mapping."""
    return {
        "id": analysis.id,
        "repository_id": analysis.repository_id,
        "status": analysis.status.value
        if hasattr(analysis.status, "value")
        else str(analysis.status),
        "base_ref": analysis.base_ref,
        "head_ref": analysis.head_ref,
        "total_changed_files": analysis.total_changed_files,
        "total_affected_entities": analysis.total_affected_entities,
        "analysis_duration_ms": analysis.analysis_duration_ms,
        "created_at": analysis.created_at,
        "completed_at": analysis.completed_at,
        "error_message": analysis.error_message,
        "changed_files": analysis.changed_files or [],
        "changed_entities": analysis.changed_entities or [],
        "impact": analysis.impact_results,
        "selection": analysis.test_recommendations,
    }
