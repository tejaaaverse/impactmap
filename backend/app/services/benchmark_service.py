"""Measured full-suite vs selected-suite benchmarks."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.logging import logger
from app.core.security import PathValidationError, validate_repository_path
from app.engine.test_selection.executor import TestExecutionResult, TestExecutor
from app.models.models import Analysis, BenchmarkRun, Repository
from app.services.analysis_service import AnalysisService
from app.services.repository_service import RepositoryService


class BenchmarkService:
    def __init__(self) -> None:
        self.repositories = RepositoryService()
        self.analyses = AnalysisService()

    async def _repository(self, db: AsyncSession, repo_id: str) -> Repository:
        repo = await self.repositories.get_repository(db, repo_id)
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

    async def run(
        self,
        db: AsyncSession,
        *,
        repository_id: str,
        analysis_id: str | None,
        base_ref: str,
        head_ref: str,
        mode: str,
        dataset_name: str | None,
        confirm: bool,
        timeout_seconds: int | None = None,
    ) -> tuple[BenchmarkRun, dict[str, Any]]:
        if not confirm:
            raise ValueError(
                "Benchmarks execute the full and selected suites. "
                "Set confirm=true to acknowledge this."
            )
        if mode not in ("safe", "optimized"):
            raise ValueError("Benchmark mode must be 'safe' or 'optimized'")

        repo = await self._repository(db, repository_id)
        reused_analysis: Analysis | None = None
        if analysis_id:
            reused_analysis = await self._analysis(db, analysis_id)
            if reused_analysis.repository_id != repo.id:
                raise ValueError("Analysis does not belong to the requested repository")
            base_ref = reused_analysis.base_ref or base_ref
            head_ref = reused_analysis.head_ref or head_ref

        started = time.monotonic()
        prepared = await self.analyses.prepare(
            db, repo.id, base_ref, head_ref, include_tests=False
        )
        analysis = reused_analysis or await self.analyses.persist_analysis(
            db, repo.id, base_ref, head_ref, prepared.pipeline
        )
        selection = prepared.pipeline.selection
        mode_selection = selection.safe if mode == "safe" else selection.optimized
        selected_ids = (
            [test.test_id for test in mode_selection.selected]
            if mode_selection
            else []
        )
        total_tests = selection.total_tests_discovered

        executor = TestExecutor(repo.path, timeout_seconds=timeout_seconds)
        full_execution: TestExecutionResult = await run_in_threadpool(
            executor.run, None
        )
        if selected_ids:
            selected_execution: TestExecutionResult = await run_in_threadpool(
                executor.run, selected_ids
            )
        else:
            selected_execution = TestExecutionResult(
                status="no_tests",
                test_ids=[],
                warnings=["No tests were selected; the selected suite was not executed."],
            )

        precision, recall = prepared.pipeline.selector.coverage_precision_recall(
            selected_ids
        )
        full_ms = full_execution.duration_ms
        selected_ms = selected_execution.duration_ms
        reduction = (
            (1.0 - selected_ms / full_ms) * 100.0
            if full_ms > 0 and selected_ids
            else 0.0
        )
        selection_count_reduction = (
            (1.0 - len(selected_ids) / total_tests) * 100.0 if total_tests else 0.0
        )
        total_ms = (time.monotonic() - started) * 1000

        notes: list[str] = list(
            dict.fromkeys(
                prepared.pipeline.warnings
                + (mode_selection.warnings if mode_selection else [])
            )
        )
        if not selected_ids:
            notes.append(
                "No selected tests were available; the measured time reduction is 0."
            )
        if not selection.coverage_available:
            notes.append(
                "Per-test coverage was unavailable. Selection used the documented "
                "static/full-suite fallbacks, so precision and recall are not reported."
            )
        error_message = None
        if full_execution.status in ("timeout", "error"):
            error_message = f"Full suite finished with status {full_execution.status}."
        elif selected_execution.status in ("timeout", "error"):
            error_message = (
                f"Selected suite finished with status {selected_execution.status}."
            )

        metrics = {
            "full_run": full_execution.to_dict(),
            "selected_run": selected_execution.to_dict(),
            "selection_count_reduction_percent": round(selection_count_reduction, 1),
            "measured_time_reduction_percent": round(reduction, 1),
            "coverage_available": selection.coverage_available,
            "measured_coverage_tests": selection.measured_tests,
            "fallback_used": bool(mode_selection.fallback_used) if mode_selection else False,
            "selection_rationale": mode_selection.rationale if mode_selection else "",
            "precision_recall_definition": (
                "Precision = selected tests that cover at least one affected entity "
                "divided by selected tests. Recall = affected entities covered by the "
                "full suite that selected tests also cover. Coverage-based; not a "
                "fault-detection score."
            ),
            "mode": mode,
        }

        benchmark = BenchmarkRun(
            repository_id=repo.id,
            analysis_id=analysis.id,
            dataset_name=dataset_name,
            mode=mode,
            base_ref=base_ref,
            head_ref=head_ref,
            total_tests=total_tests,
            selected_tests=len(selected_ids),
            full_duration_ms=full_ms,
            selected_duration_ms=selected_ms if selected_ids else 0.0,
            analysis_duration_ms=prepared.pipeline.duration_ms,
            reduction_percent=round(reduction, 1),
            selection_precision=precision,
            selection_recall=recall,
            metrics=metrics,
            notes={"warnings": notes, "total_elapsed_ms": round(total_ms, 1)},
            error_message=error_message,
            created_at=datetime.now(timezone.utc),
        )
        db.add(benchmark)
        await db.flush()
        logger.info(
            "Benchmark persisted: %s (%s, %d/%d tests, %.1f%% time reduction)",
            benchmark.id,
            mode,
            len(selected_ids),
            total_tests,
            reduction,
        )
        return benchmark, metrics

    async def list(
        self, db: AsyncSession, *, repository_id: str | None = None, limit: int = 50
    ) -> list[BenchmarkRun]:
        stmt = select(BenchmarkRun).order_by(BenchmarkRun.created_at.desc()).limit(limit)
        if repository_id:
            stmt = stmt.where(BenchmarkRun.repository_id == repository_id)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get(self, db: AsyncSession, benchmark_id: str) -> BenchmarkRun | None:
        stmt = select(BenchmarkRun).where(BenchmarkRun.id == benchmark_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()
