"""Graph retrieval built from a fresh parse of the repository."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.security import PathValidationError, validate_repository_path
from app.engine.graph.code_graph import GraphBuilder
from app.engine.scanner.repository_scanner import RepositoryScanner
from app.services.repository_service import RepositoryService


def _build(repo_path: str, include_tests: bool, include_modules: bool) -> dict:
    scan = RepositoryScanner().scan(repo_path)
    graph = GraphBuilder().build(scan)
    payload = graph.to_dict(include_tests=include_tests, include_modules=include_modules)
    payload["scan_warnings"] = scan.warnings
    return payload


class GraphService:
    def __init__(self) -> None:
        self.repositories = RepositoryService()

    async def build(
        self,
        db: AsyncSession,
        repo_id: str,
        *,
        include_tests: bool = True,
        include_modules: bool = True,
    ) -> dict:
        repo = await self.repositories.get_repository(db, repo_id)
        if not repo:
            raise LookupError("Repository not found")
        try:
            validate_repository_path(repo.path)
        except PathValidationError as exc:
            raise ValueError(str(exc)) from exc
        return await run_in_threadpool(
            _build, repo.path, include_tests, include_modules
        )
