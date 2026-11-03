"""Benchmark API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logging import logger
from app.schemas.schemas import (
    BenchmarkDetailResponse,
    BenchmarkListResponse,
    BenchmarkRequest,
    BenchmarkResponse,
    TestExecutionResponse,
)
from app.services.benchmark_service import BenchmarkService

router = APIRouter(prefix="/api/benchmarks", tags=["Benchmarks"])

_benchmark_service = BenchmarkService()


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    logger.error("Benchmark error: %s", exc, exc_info=True)
    return HTTPException(status_code=500, detail=f"Benchmark failed: {exc}")


@router.get("", response_model=BenchmarkListResponse)
async def list_benchmarks(
    repository_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List measured benchmark runs."""
    runs = await _benchmark_service.list(
        db, repository_id=repository_id, limit=limit
    )
    return BenchmarkListResponse(
        benchmarks=[BenchmarkResponse.model_validate(run) for run in runs],
        total=len(runs),
    )


@router.post("/run", response_model=BenchmarkDetailResponse, status_code=201)
async def run_benchmark(
    request: BenchmarkRequest,
    db: AsyncSession = Depends(get_db),
):
    """Execute the full suite and the selected suite and record real timings.

    This is a measurement, not a synthetic improvement estimate: both suites
    run in subprocesses with the same interpreter, working directory and timeout.
    """
    try:
        benchmark, metrics = await _benchmark_service.run(
            db,
            repository_id=request.repository_id,
            analysis_id=request.analysis_id,
            base_ref=request.base_ref,
            head_ref=request.head_ref,
            mode=request.mode,
            dataset_name=request.dataset_name,
            confirm=request.confirm,
            timeout_seconds=request.timeout_seconds,
        )
    except Exception as exc:
        raise _http_error(exc) from exc

    payload = BenchmarkResponse.model_validate(benchmark).model_dump()
    payload["full_run"] = TestExecutionResponse.model_validate(
        metrics.get("full_run") or {}
    )
    payload["selected_run"] = TestExecutionResponse.model_validate(
        metrics.get("selected_run") or {}
    )
    return BenchmarkDetailResponse.model_validate(payload)


@router.get("/{benchmark_id}", response_model=BenchmarkDetailResponse)
async def get_benchmark(benchmark_id: str, db: AsyncSession = Depends(get_db)):
    benchmark = await _benchmark_service.get(db, benchmark_id)
    if not benchmark:
        raise HTTPException(status_code=404, detail="Benchmark not found")
    metrics = benchmark.metrics or {}
    payload = BenchmarkResponse.model_validate(benchmark).model_dump()
    payload["full_run"] = TestExecutionResponse.model_validate(
        metrics.get("full_run") or {}
    )
    payload["selected_run"] = TestExecutionResponse.model_validate(
        metrics.get("selected_run") or {}
    )
    return BenchmarkDetailResponse.model_validate(payload)
