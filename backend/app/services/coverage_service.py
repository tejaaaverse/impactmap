"""Coverage snapshot collection and persistence."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.logging import logger
from app.core.security import PathValidationError, validate_repository_path
from app.engine.test_selection.coverage_collector import (
    CoverageCollectionResult,
    CoverageCollector,
    merge_coverage_data,
)
from app.models.models import CoverageSnapshot, Repository
from app.services.repository_service import RepositoryService


class CoverageService:
    def __init__(self) -> None:
        self.repositories = RepositoryService()

    async def _repository(self, db: AsyncSession, repo_id: str) -> Repository:
        repo = await self.repositories.get_repository(db, repo_id)
        if not repo:
            raise LookupError("Repository not found")
        try:
            validate_repository_path(repo.path)
        except PathValidationError as exc:
            raise ValueError(str(exc)) from exc
        return repo

    async def latest(self, db: AsyncSession, repo_id: str) -> CoverageSnapshot | None:
        stmt = (
            select(CoverageSnapshot)
            .where(CoverageSnapshot.repository_id == repo_id)
            .order_by(CoverageSnapshot.collected_at.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def collect(
        self,
        db: AsyncSession,
        repo_id: str,
        *,
        test_ids: list[str] | None,
        confirm: bool,
        timeout_seconds: int | None = None,
    ) -> tuple[CoverageSnapshot, dict, bool]:
        if not confirm:
            raise ValueError(
                "Coverage collection executes repository test code. "
                "Set confirm=true to acknowledge this."
            )
        repo = await self._repository(db, repo_id)
        previous = await self.latest(db, repo_id)

        collector = CoverageCollector(
            repo.path, timeout_seconds=timeout_seconds
        )
        result: CoverageCollectionResult = await run_in_threadpool(
            collector.collect,
            None,
            test_ids,
            timeout_seconds,
        )

        merged = False
        data = result.data
        if data is not None and previous and previous.data:
            data = merge_coverage_data(previous.data, data)
            merged = True

        snapshot = CoverageSnapshot(
            repository_id=repo_id,
            status=result.status,
            collected_at=datetime.now(timezone.utc),
            duration_ms=result.duration_ms,
            total_tests=result.total_tests,
            measured_tests=result.measured_tests,
            covered_files=result.covered_files,
            data=data,
            error_message=result.error,
            warnings=result.warnings,
        )
        db.add(snapshot)
        await db.flush()
        logger.info(
            "Coverage snapshot persisted: %s (%s, %d/%d tests, %d files)",
            snapshot.id,
            snapshot.status,
            snapshot.measured_tests,
            snapshot.total_tests,
            snapshot.covered_files,
        )
        execution = result.execution.to_dict() if result.execution else {
            "status": "error",
            "exit_code": None,
            "test_ids": test_ids or [],
            "total_tests": 0,
            "passed": 0,
            "failed": 0,
            "errors": 0,
            "skipped": 0,
            "duration_ms": 0,
            "timed_out": False,
            "results": [],
            "stdout_tail": "",
            "stderr_tail": "",
            "warnings": result.warnings,
            "command": [],
        }
        return snapshot, execution, merged
