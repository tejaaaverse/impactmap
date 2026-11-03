"""Measured test execution (full, safe, optimized or custom)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

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
from app.engine.test_selection.executor import TestExecutionResult, TestExecutor
from app.models.models import Analysis, CoverageSnapshot, Repository, TestRun
from app.services.repository_service import RepositoryService


class TestRunService:
    def __init__(self) -> None:
        self.repositories = RepositoryService()

    async def _repository(self, db: AsyncSession, analysis: Analysis) -> Repository:
        repo = await self.repositories.get_repository(db, analysis.repository_id)
        if not repo:
            raise LookupError("Repository not found")
        try:
            validate_repository_path(repo.path)
        except PathValidationError as exc:
            raise ValueError(str(exc)) from exc
        return repo

    async def _analysis(self, db: AsyncSession, analysis_id: str) -> Analysis:
        stmt = select(Analysis).where(Analysis.id == analysis_id)
        result = await db.execute(stmt)
        analysis = result.scalar_one_or_none()
        if not analysis:
            raise LookupError("Analysis not found")
        return analysis

    async def previous_coverage(
        self, db: AsyncSession, repo_id: str
    ) -> CoverageSnapshot | None:
        stmt = (
            select(CoverageSnapshot)
            .where(CoverageSnapshot.repository_id == repo_id)
            .order_by(CoverageSnapshot.collected_at.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def run(
        self,
        db: AsyncSession,
        analysis_id: str,
        *,
        mode: str,
        test_ids: list[str] | None = None,
        confirm: bool = False,
        collect_coverage: bool = False,
        timeout_seconds: int | None = None,
    ) -> tuple[TestRun, dict[str, Any], str | None]:
        if not confirm:
            raise ValueError(
                "Test execution runs repository test code. "
                "Set confirm=true to acknowledge this."
            )
        if mode not in ("full", "safe", "optimized", "custom"):
            raise ValueError(f"Unsupported test mode: {mode}")

        analysis = await self._analysis(db, analysis_id)
        repo = await self._repository(db, analysis)
        resolved_ids: list[str] | None
        if mode == "full":
            resolved_ids = None
        elif mode == "custom":
            if not test_ids:
                raise ValueError("mode=custom requires a non-empty test_ids list")
            resolved_ids = test_ids
        else:
            selection = (analysis.test_recommendations or {}).get(mode)
            if not selection:
                raise ValueError(
                    f"No {mode} selection is stored for this analysis"
                )
            resolved_ids = [
                item["test_id"]
                for item in selection.get("selected_tests", [])
                if item.get("test_id")
            ]

        coverage_snapshot_id: str | None = None
        coverage_warnings: list[str] = []

        if collect_coverage:
            collector = CoverageCollector(repo.path, timeout_seconds=timeout_seconds)
            coverage_result: CoverageCollectionResult = await run_in_threadpool(
                collector.collect, None, resolved_ids, timeout_seconds
            )
            execution = coverage_result.execution
            previous = await self.previous_coverage(db, repo.id)
            data = coverage_result.data
            if data is not None and previous and previous.data:
                data = merge_coverage_data(previous.data, data)
            snapshot = CoverageSnapshot(
                repository_id=repo.id,
                status=coverage_result.status,
                collected_at=datetime.now(timezone.utc),
                duration_ms=coverage_result.duration_ms,
                total_tests=coverage_result.total_tests,
                measured_tests=coverage_result.measured_tests,
                covered_files=coverage_result.covered_files,
                data=data,
                error_message=coverage_result.error,
                warnings=coverage_result.warnings,
            )
            db.add(snapshot)
            await db.flush()
            coverage_snapshot_id = snapshot.id
            coverage_warnings = coverage_result.warnings
            if execution is None:
                execution = TestExecutionResult(
                    status="error",
                    warnings=coverage_result.warnings,
                )
        else:
            executor = TestExecutor(repo.path, timeout_seconds=timeout_seconds)
            execution = await run_in_threadpool(executor.run, resolved_ids)

        execution_dict = execution.to_dict()
        run = TestRun(
            repository_id=repo.id,
            analysis_id=analysis.id,
            mode=mode,
            status=execution.status,
            exit_code=execution.exit_code,
            test_ids=execution.test_ids,
            total_tests=execution.total_tests,
            passed=execution.passed,
            failed=execution.failed,
            errors=execution.errors,
            skipped=execution.skipped,
            duration_ms=execution.duration_ms,
            timed_out=int(execution.timed_out),
            results=execution.results,
            stdout_tail=execution.stdout_tail,
            stderr_tail=execution.stderr_tail,
            created_at=datetime.now(timezone.utc),
        )
        db.add(run)
        await db.flush()
        logger.info(
            "Test run persisted: %s (%s, %s, %d passed / %d failed, %.1fms)",
            run.id,
            mode,
            execution.status,
            execution.passed,
            execution.failed,
            execution.duration_ms,
        )
        all_warnings = list(
            dict.fromkeys(
                execution.warnings
                + coverage_warnings
                + ([] if resolved_ids is None else [])
            )
        )
        return run, execution_dict, coverage_snapshot_id

    async def history(
        self,
        db: AsyncSession,
        *,
        analysis_id: str | None = None,
        repository_id: str | None = None,
        limit: int = 50,
    ) -> list[TestRun]:
        stmt = select(TestRun).order_by(TestRun.created_at.desc()).limit(limit)
        if analysis_id:
            stmt = stmt.where(TestRun.analysis_id == analysis_id)
        if repository_id:
            stmt = stmt.where(TestRun.repository_id == repository_id)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    def execution_for_run(run: TestRun) -> dict[str, Any]:
        return {
            "status": run.status,
            "exit_code": run.exit_code,
            "test_ids": run.test_ids or [],
            "total_tests": run.total_tests,
            "passed": run.passed,
            "failed": run.failed,
            "errors": run.errors,
            "skipped": run.skipped,
            "duration_ms": run.duration_ms or 0,
            "timed_out": bool(run.timed_out),
            "results": run.results or [],
            "stdout_tail": run.stdout_tail or "",
            "stderr_tail": run.stderr_tail or "",
            "warnings": [],
            "command": [],
        }
