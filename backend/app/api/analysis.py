"""Analysis, graph, coverage and test-execution API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.database import get_db
from app.core.logging import logger
from app.core.security import PathValidationError
from app.engine.git.change_detector import GitDetectionError, is_git_repository
from app.engine.test_selection.discovery import TestDiscovery
from app.schemas.schemas import (
    AnalysisDetailResponse,
    AnalysisListResponse,
    AnalysisRequest,
    AnalysisResponse,
    CoverageCollectRequest,
    CoverageCollectResponse,
    CoverageSnapshotResponse,
    DiscoveredTestResponse,
    DiscoveredTestsResponse,
    GraphResponse,
    GraphStatsResponse,
    ImpactResponse,
    RunAnalysisResponse,
    SelectionResponse,
    TestExecutionResponse,
    TestRunHistoryResponse,
    TestRunRequest,
    TestRunResponse,
)
from app.services.analysis_service import AnalysisService, analysis_detail_dict
from app.services.coverage_service import CoverageService
from app.services.graph_service import GraphService
from app.services.repository_service import RepositoryService
from app.services.test_run_service import TestRunService

router = APIRouter(prefix="/api", tags=["Analysis"])

_analysis_service = AnalysisService()
_coverage_service = CoverageService()
_graph_service = GraphService()
_test_run_service = TestRunService()
_repository_service = RepositoryService()


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, (ValueError, GitDetectionError, PathValidationError)):
        return HTTPException(status_code=400, detail=str(exc))
    logger.error("Unhandled analysis error: %s", exc, exc_info=True)
    return HTTPException(status_code=500, detail=f"Analysis failed: {exc}")


def _analysis_detail(analysis) -> AnalysisDetailResponse:
    return AnalysisDetailResponse.model_validate(analysis_detail_dict(analysis))


def _analysis_summary(analysis) -> AnalysisResponse:
    return AnalysisResponse.model_validate(analysis)


def _test_run_response(run, execution, coverage_snapshot_id=None) -> TestRunResponse:
    return TestRunResponse(
        id=run.id,
        repository_id=run.repository_id,
        analysis_id=run.analysis_id,
        mode=run.mode,
        status=run.status,
        exit_code=run.exit_code,
        total_tests=run.total_tests,
        passed=run.passed,
        failed=run.failed,
        errors=run.errors,
        skipped=run.skipped,
        duration_ms=run.duration_ms,
        timed_out=bool(run.timed_out),
        created_at=run.created_at,
        execution=TestExecutionResponse.model_validate(execution),
        coverage_snapshot_id=coverage_snapshot_id,
        warnings=execution.get("warnings", []),
    )


# ── repositories: analysis ─────────────────────────────────────


@router.post(
    "/repositories/{repo_id}/analyze",
    response_model=RunAnalysisResponse,
    status_code=201,
)
async def analyze_repository(
    repo_id: str,
    request: AnalysisRequest,
    db: AsyncSession = Depends(get_db),
):
    """Run a Git-diff impact analysis and select tests.

    Coverage is used when a snapshot already exists for the repository. When no
    per-test coverage is available the selector records an explicit fallback.
    """
    try:
        analysis, pipeline = await _analysis_service.run(
            db,
            repo_id,
            request.base_ref,
            request.head_ref,
            include_tests=request.include_tests,
        )
    except Exception as exc:
        raise _http_error(exc) from exc
    return RunAnalysisResponse(
        analysis=_analysis_detail(analysis),
        graph_stats=GraphStatsResponse.model_validate(pipeline.graph.stats()),
    )


@router.get("/analysis", response_model=AnalysisListResponse)
async def list_analyses(
    repository_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    analyses = await _analysis_service.list(
        db, repository_id=repository_id, limit=limit
    )
    return AnalysisListResponse(
        analyses=[_analysis_summary(a) for a in analyses], total=len(analyses)
    )


@router.get("/analysis/{analysis_id}", response_model=AnalysisDetailResponse)
async def get_analysis(analysis_id: str, db: AsyncSession = Depends(get_db)):
    try:
        analysis = await _analysis_service.require(db, analysis_id)
    except Exception as exc:
        raise _http_error(exc) from exc
    return _analysis_detail(analysis)


@router.get("/analysis/{analysis_id}/impact", response_model=ImpactResponse)
async def get_analysis_impact(analysis_id: str, db: AsyncSession = Depends(get_db)):
    try:
        analysis = await _analysis_service.require(db, analysis_id)
    except Exception as exc:
        raise _http_error(exc) from exc
    if not analysis.impact_results:
        raise HTTPException(status_code=404, detail="No impact result stored")
    return ImpactResponse.model_validate(analysis.impact_results)


@router.get("/analysis/{analysis_id}/tests", response_model=SelectionResponse)
async def get_analysis_tests(analysis_id: str, db: AsyncSession = Depends(get_db)):
    try:
        analysis = await _analysis_service.require(db, analysis_id)
    except Exception as exc:
        raise _http_error(exc) from exc
    if not analysis.test_recommendations:
        raise HTTPException(status_code=404, detail="No test selection stored")
    return SelectionResponse.model_validate(analysis.test_recommendations)


@router.post(
    "/analysis/{analysis_id}/run-tests",
    response_model=TestRunResponse,
    status_code=201,
)
async def run_analysis_tests(
    analysis_id: str,
    request: TestRunRequest,
    db: AsyncSession = Depends(get_db),
):
    """Execute tests in a subprocess. Requires ``confirm=true``."""
    try:
        run, execution, coverage_id = await _test_run_service.run(
            db,
            analysis_id,
            mode=request.mode,
            test_ids=request.test_ids,
            confirm=request.confirm,
            collect_coverage=request.collect_coverage,
            timeout_seconds=request.timeout_seconds,
        )
    except Exception as exc:
        raise _http_error(exc) from exc
    return _test_run_response(run, execution, coverage_id)


@router.get(
    "/analysis/{analysis_id}/test-runs", response_model=TestRunHistoryResponse
)
async def analysis_test_runs(analysis_id: str, db: AsyncSession = Depends(get_db)):
    runs = await _test_run_service.history(db, analysis_id=analysis_id)
    payload = [
        _test_run_response(run, _test_run_service.execution_for_run(run)) for run in runs
    ]
    return TestRunHistoryResponse(runs=payload, total=len(payload))


# ── repositories: graph / tests / coverage ─────────────────────


@router.get("/repositories/{repo_id}/graph", response_model=GraphResponse)
async def repository_graph(
    repo_id: str,
    include_tests: bool = Query(default=True),
    include_modules: bool = Query(default=True),
    db: AsyncSession = Depends(get_db),
):
    try:
        payload = await _graph_service.build(
            db,
            repo_id,
            include_tests=include_tests,
            include_modules=include_modules,
        )
    except Exception as exc:
        raise _http_error(exc) from exc
    payload.pop("scan_warnings", None)
    return GraphResponse.model_validate(payload)


@router.get("/repositories/{repo_id}/tests", response_model=DiscoveredTestsResponse)
async def repository_tests(repo_id: str, db: AsyncSession = Depends(get_db)):
    repo = await _repository_service.get_repository(db, repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    try:
        tests = await run_in_threadpool(
            TestDiscovery().discover, repo.path
        )
    except Exception as exc:
        raise _http_error(exc) from exc
    return DiscoveredTestsResponse(
        repository_id=repo.id,
        tests=[DiscoveredTestResponse(**t.to_dict()) for t in tests],
        total=len(tests),
    )


@router.get(
    "/repositories/{repo_id}/coverage",
    response_model=list[CoverageSnapshotResponse],
)
async def repository_coverage(
    repo_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select
    from app.models.models import CoverageSnapshot

    repo = await _repository_service.get_repository(db, repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    result = await db.execute(
        select(CoverageSnapshot)
        .where(CoverageSnapshot.repository_id == repo_id)
        .order_by(CoverageSnapshot.collected_at.desc())
        .limit(limit)
    )
    return [
        CoverageSnapshotResponse.model_validate(snapshot)
        for snapshot in result.scalars().all()
    ]


@router.post(
    "/repositories/{repo_id}/coverage",
    response_model=CoverageCollectResponse,
    status_code=201,
)
async def collect_repository_coverage(
    repo_id: str,
    request: CoverageCollectRequest,
    db: AsyncSession = Depends(get_db),
):
    """Collect per-test coverage with Coverage.py dynamic contexts.

    Requires ``confirm=true`` because repository test code is executed.
    """
    try:
        snapshot, execution, merged = await _coverage_service.collect(
            db,
            repo_id,
            test_ids=request.test_ids,
            confirm=request.confirm,
            timeout_seconds=request.timeout_seconds,
        )
    except Exception as exc:
        raise _http_error(exc) from exc
    return CoverageCollectResponse(
        snapshot=CoverageSnapshotResponse.model_validate(snapshot),
        execution=TestExecutionResponse.model_validate(execution),
        merged_with_previous=merged,
    )


@router.get("/repositories/{repo_id}/git-status")
async def repository_git_status(repo_id: str, db: AsyncSession = Depends(get_db)):
    repo = await _repository_service.get_repository(db, repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    is_git = await run_in_threadpool(is_git_repository, repo.path)
    return {"repository_id": repo.id, "is_git_repository": is_git}
