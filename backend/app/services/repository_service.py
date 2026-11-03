"""
Repository-related API service layer.

Handles business logic between API routes and the engine,
including database persistence.
"""

import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.models import Repository, CodeEntity, RepoStatus, EntityType
from app.engine.graph.code_graph import GraphBuilder
from app.engine.scanner.repository_scanner import RepositoryScanner, RepositoryScanResult
from app.core.security import validate_repository_path
from app.core.logging import logger


class RepositoryService:
    """Service for repository operations."""

    def __init__(self):
        self.scanner = RepositoryScanner()

    async def scan_repository(self, db: AsyncSession, repo_path: str) -> tuple[Repository, RepositoryScanResult]:
        """
        Scan a repository and persist results to the database.

        Returns:
            Tuple of (Repository model, ScanResult data).
        """
        resolved = str(validate_repository_path(repo_path))

        # Check if repo already exists
        stmt = select(Repository).where(Repository.path == resolved)
        result = await db.execute(stmt)
        repo = result.scalar_one_or_none()

        if repo:
            # Re-scan: delete old entities
            repo.status = RepoStatus.SCANNING
            # Delete existing entities
            for entity in await self._get_entities(db, repo.id):
                await db.delete(entity)
            await db.flush()
        else:
            repo = Repository(
                path=resolved,
                name=Path(resolved).name,
                status=RepoStatus.SCANNING,
            )
            db.add(repo)
            await db.flush()

        try:
            # Run the scan (CPU-bound, synchronous)
            scan_result = self.scanner.scan(resolved)

            # Build the graph once during the scan so the stored dependency
            # count reflects resolved relationships rather than raw imports.
            graph = GraphBuilder().build(scan_result)
            scan_result.summary.total_dependencies = sum(
                1 for _ in graph.dependency_edges()
            )

            # Persist entities
            await self._persist_entities(db, repo.id, scan_result)

            # Update repository record
            repo.status = RepoStatus.SCANNED
            repo.total_files = scan_result.summary.total_files
            repo.total_functions = scan_result.summary.total_functions
            repo.total_classes = scan_result.summary.total_classes
            repo.total_dependencies = scan_result.summary.total_dependencies
            repo.last_scanned_at = datetime.now(timezone.utc)
            repo.scan_error = None
            repo.metadata_ = {
                "scan_summary": scan_result.summary.to_dict(),
                "graph_stats": graph.stats(),
                "warnings": scan_result.warnings[:100],
            }

            await db.flush()
            logger.info(f"Repository persisted: {repo.name} ({repo.id})")

            return repo, scan_result

        except Exception as e:
            repo.status = RepoStatus.ERROR
            repo.scan_error = str(e)
            await db.flush()
            logger.error(f"Scan failed for {resolved}: {e}")
            raise

    async def get_repositories(self, db: AsyncSession) -> list[Repository]:
        """Get all repositories."""
        stmt = select(Repository).order_by(Repository.created_at.desc())
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_repository(self, db: AsyncSession, repo_id: str) -> Repository | None:
        """Get a repository by ID."""
        stmt = select(Repository).where(Repository.id == repo_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_repository_detail(self, db: AsyncSession, repo_id: str) -> Repository | None:
        """Get a repository with its entities."""
        stmt = (
            select(Repository)
            .where(Repository.id == repo_id)
            .options(selectinload(Repository.entities))
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_entities(self, db: AsyncSession, repo_id: str) -> list[CodeEntity]:
        """Get all entities for a repository."""
        stmt = select(CodeEntity).where(CodeEntity.repository_id == repo_id)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def _persist_entities(
        self, db: AsyncSession, repo_id: str, scan_result: RepositoryScanResult
    ) -> None:
        """Persist parsed code entities to the database."""
        for module in scan_result.modules:
            # Create file entity
            file_entity = CodeEntity(
                repository_id=repo_id,
                name=Path(module.file_path).name,
                qualified_name=module.module_name or Path(module.file_path).stem,
                entity_type=EntityType.FILE,
                file_path=module.file_path,
                line_start=1,
                line_end=module.line_count,
                imports=[
                    {
                        "module": imp.module,
                        "name": imp.name,
                        "alias": imp.alias,
                        "is_from": imp.is_from_import,
                    }
                    for imp in module.imports
                ],
            )
            db.add(file_entity)
            await db.flush()

            # Create function entities
            for func in module.functions:
                func_entity = CodeEntity(
                    repository_id=repo_id,
                    name=func.name,
                    qualified_name=func.qualified_name,
                    entity_type=EntityType.FUNCTION,
                    file_path=module.file_path,
                    line_start=func.line_start,
                    line_end=func.line_end,
                    parent_entity_id=file_entity.id,
                    docstring=func.docstring,
                    decorators=func.decorators,
                )
                db.add(func_entity)

            # Create class entities and their methods
            for cls in module.classes:
                cls_entity = CodeEntity(
                    repository_id=repo_id,
                    name=cls.name,
                    qualified_name=cls.qualified_name,
                    entity_type=EntityType.CLASS,
                    file_path=module.file_path,
                    line_start=cls.line_start,
                    line_end=cls.line_end,
                    parent_entity_id=file_entity.id,
                    docstring=cls.docstring,
                    decorators=cls.decorators,
                )
                db.add(cls_entity)
                await db.flush()

                for method in cls.methods:
                    method_entity = CodeEntity(
                        repository_id=repo_id,
                        name=method.name,
                        qualified_name=method.qualified_name,
                        entity_type=EntityType.METHOD,
                        file_path=module.file_path,
                        line_start=method.line_start,
                        line_end=method.line_end,
                        parent_entity_id=cls_entity.id,
                        docstring=method.docstring,
                        decorators=method.decorators,
                    )
                    db.add(method_entity)
