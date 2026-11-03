"""
Repository Scanner Service.

Orchestrates file discovery and AST parsing to produce a complete
picture of a Python repository's code structure.
"""

import time
from pathlib import Path
from dataclasses import dataclass, field

from app.engine.scanner.file_discovery import FileDiscovery, DiscoveryResult
from app.engine.parser.python_parser import (
    PythonASTParser,
    ModuleParseResult,
    file_path_to_module_name,
)
from app.core.logging import logger


@dataclass
class ScanSummary:
    """Summary statistics from a repository scan.

    Every value is derived from the discovery/parse pass. ``total_dependencies``
    is filled in after graph construction; it counts resolved dependency edges,
    not raw import statements (``total_imports``).
    """

    total_files: int = 0
    total_functions: int = 0
    total_classes: int = 0
    total_methods: int = 0
    total_imports: int = 0
    total_dependencies: int = 0
    total_lines: int = 0
    total_size_bytes: int = 0
    directories_explored: int = 0
    files_parsed: int = 0
    files_with_errors: int = 0
    files_skipped: int = 0
    skipped_directories: int = 0
    parse_errors: list[str] = field(default_factory=list)
    scan_duration_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "total_files": self.total_files,
            "total_functions": self.total_functions,
            "total_classes": self.total_classes,
            "total_methods": self.total_methods,
            "total_imports": self.total_imports,
            "total_dependencies": self.total_dependencies,
            "total_lines": self.total_lines,
            "total_size_bytes": self.total_size_bytes,
            "directories_explored": self.directories_explored,
            "files_parsed": self.files_parsed,
            "files_with_errors": self.files_with_errors,
            "files_skipped": self.files_skipped,
            "skipped_directories": self.skipped_directories,
            "parse_errors": self.parse_errors,
            "scan_duration_ms": round(self.scan_duration_ms, 1),
        }


@dataclass
class RepositoryScanResult:
    """Complete result of scanning a repository."""

    repo_path: str
    repo_name: str
    summary: ScanSummary
    discovery: DiscoveryResult
    modules: list[ModuleParseResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class RepositoryScanner:
    """
    Scans a Python repository to discover and parse all source files.

    Pipeline:
    1. File discovery — find all .py files, skip ignored directories
    2. AST parsing — extract functions, classes, imports from each file
    3. Aggregation — compute summary statistics

    Usage:
        scanner = RepositoryScanner()
        result = scanner.scan("/path/to/repo")
    """

    def __init__(self):
        self.file_discovery = FileDiscovery()
        self.parser = PythonASTParser()

    def scan(self, repo_path: str | Path) -> RepositoryScanResult:
        """
        Scan a repository and extract its full code structure.

        Args:
            repo_path: Absolute path to the repository root.

        Returns:
            RepositoryScanResult with all discovered files and parsed entities.

        Raises:
            ValueError: If the path is invalid.
        """
        repo_path = Path(repo_path).resolve()
        start_time = time.monotonic()

        logger.info(f"Starting repository scan: {repo_path}")

        # Validate path
        if not repo_path.exists():
            raise ValueError(f"Repository path does not exist: {repo_path}")
        if not repo_path.is_dir():
            raise ValueError(f"Repository path is not a directory: {repo_path}")

        repo_name = repo_path.name

        # Phase 1: Discover files
        discovery = self.file_discovery.discover(repo_path)

        # Phase 2: Parse each file
        modules: list[ModuleParseResult] = []
        warnings: list[str] = []

        for discovered_file in discovery.files:
            module_name = file_path_to_module_name(
                discovered_file.relative_path, str(repo_path)
            )

            parse_result = self.parser.parse_file(
                discovered_file.absolute_path, module_name
            )
            # Store repository-relative paths everywhere downstream: the graph,
            # change detector and test selector must agree on node identity.
            # The parser needs the absolute path to read the file, but once the
            # file is read the absolute path is only noise (and breaks matching
            # against Git diff paths).
            parse_result.file_path = discovered_file.relative_path.replace("\\", "/")

            if parse_result.parse_errors:
                for error in parse_result.parse_errors:
                    warnings.append(f"{discovered_file.relative_path}: {error}")

            modules.append(parse_result)

        # Phase 3: Aggregate statistics
        summary = self._compute_summary(discovery, modules)
        summary.scan_duration_ms = (time.monotonic() - start_time) * 1000

        # Add discovery errors to warnings
        warnings.extend(discovery.errors)

        result = RepositoryScanResult(
            repo_path=str(repo_path),
            repo_name=repo_name,
            summary=summary,
            discovery=discovery,
            modules=modules,
            warnings=warnings,
        )

        logger.info(
            f"Scan complete: {summary.total_files} files, "
            f"{summary.total_functions} functions, "
            f"{summary.total_classes} classes, "
            f"{summary.total_methods} methods, "
            f"{summary.scan_duration_ms:.1f}ms"
        )

        return result

    def _compute_summary(
        self, discovery: DiscoveryResult, modules: list[ModuleParseResult]
    ) -> ScanSummary:
        """Compute aggregate statistics from parsed modules."""
        summary = ScanSummary(
            total_files=len(discovery.files),
            total_size_bytes=discovery.total_size_bytes,
            directories_explored=discovery.directories_explored,
            files_skipped=len(discovery.files_skipped),
            skipped_directories=len(discovery.skipped_dirs),
        )

        for module in modules:
            summary.total_functions += len(module.functions)
            summary.total_classes += len(module.classes)
            summary.total_imports += len(module.imports)
            summary.total_lines += module.line_count

            for cls in module.classes:
                summary.total_methods += len(cls.methods)

            if module.parse_errors:
                summary.files_with_errors += 1
                for error in module.parse_errors:
                    summary.parse_errors.append(f"{module.file_path}: {error}")
            else:
                summary.files_parsed += 1

        return summary
