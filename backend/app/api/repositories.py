"""
Repository API routes.

Provides endpoints for scanning repositories, listing them,
and viewing their details.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.database import get_db
from app.engine.git.change_detector import get_git_info, is_git_repository
from app.schemas.schemas import (
    RepositoryScanRequest,
    RepositoryResponse,
    RepositoryDetailResponse,
    ScanResultResponse,
    CodeEntityResponse,
)
from app.services.file_service import FileAccessError, read_repository_file
from app.services.repository_service import RepositoryService
from app.core.logging import logger

router = APIRouter(prefix="/api/repositories", tags=["Repositories"])

# Service singleton
_repo_service = RepositoryService()


@router.post("/scan", response_model=ScanResultResponse, status_code=201)
async def scan_repository(
    request: RepositoryScanRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Scan a local Python repository.

    Discovers all Python files, parses them using AST analysis,
    and extracts functions, classes, methods, and imports.
    """
    logger.info(f"API: Scan requested for {request.path}")

    try:
        repo, scan_result = await _repo_service.scan_repository(db, request.path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Scan failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Scan failed: {str(e)}")

    return ScanResultResponse(
        repository=RepositoryResponse.model_validate(repo),
        files_discovered=scan_result.summary.total_files,
        functions_discovered=scan_result.summary.total_functions,
        classes_discovered=scan_result.summary.total_classes,
        methods_discovered=scan_result.summary.total_methods,
        dependencies_discovered=scan_result.summary.total_dependencies,
        directories_explored=scan_result.summary.directories_explored,
        files_parsed=scan_result.summary.files_parsed,
        files_skipped=scan_result.summary.files_skipped,
        files_with_errors=scan_result.summary.files_with_errors,
        imports_discovered=scan_result.summary.total_imports,
        parse_errors=scan_result.summary.parse_errors[:100],
        scan_duration_ms=scan_result.summary.scan_duration_ms,
        warnings=scan_result.warnings,
    )


@router.get("", response_model=list[RepositoryResponse])
async def list_repositories(db: AsyncSession = Depends(get_db)):
    """List all scanned repositories."""
    repos = await _repo_service.get_repositories(db)
    return [RepositoryResponse.model_validate(r) for r in repos]


@router.get("/{repo_id}", response_model=RepositoryDetailResponse)
async def get_repository(repo_id: str, db: AsyncSession = Depends(get_db)):
    """Get repository details including discovered entities."""
    repo = await _repo_service.get_repository_detail(db, repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    entities = [CodeEntityResponse.model_validate(e) for e in repo.entities]
    resp = RepositoryDetailResponse.model_validate(repo)
    resp.entities = entities
    resp.is_git_repository = await run_in_threadpool(is_git_repository, repo.path)
    resp.scan_stats = (repo.metadata_ or {}).get("scan_summary", {})
    return resp


@router.get("/{repo_id}/git-refs")
async def repository_git_refs(repo_id: str, db: AsyncSession = Depends(get_db)):
    """Describe commits, branches and working-tree state for the ref picker.

    Returns recommended base/head refs that are valid for this repository (for
    example ``HEAD`` instead of ``HEAD~1`` when only one commit exists).
    """
    repo = await _repo_service.get_repository(db, repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    info = await run_in_threadpool(get_git_info, repo.path)
    return info.to_dict()


@router.get("/{repo_id}/file")
async def repository_file(
    repo_id: str,
    path: str = Query(..., description="Repository-relative file path"),
    start_line: int | None = Query(default=None, ge=1),
    end_line: int | None = Query(default=None, ge=1),
    db: AsyncSession = Depends(get_db),
):
    """Read a repository file for the code viewer (read-only, path-validated)."""
    repo = await _repo_service.get_repository(db, repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    try:
        content = await run_in_threadpool(
            read_repository_file,
            repo.path,
            path,
            start_line=start_line,
            end_line=end_line,
        )
    except FileAccessError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return content.to_dict()
