"""Collect per-test coverage contexts with Coverage.py."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

import coverage

from app.core.logging import logger
from app.core.security import is_within
from app.engine.graph.code_graph import is_test_path
from app.engine.test_selection.discovery import TestCase
from app.engine.test_selection.executor import TestExecutionResult, TestExecutor


CONTEXT_PLUGIN_SOURCE = '''"""Tiny pytest plugin: attribute measured lines to the running test."""
import coverage

_cov = coverage.Coverage.current()


def pytest_runtest_setup(item):
    if _cov is not None:
        _cov.switch_context(item.nodeid)


def pytest_runtest_teardown(item, nextitem):
    if _cov is not None:
        _cov.switch_context(None)
'''


@dataclass
class CoverageCollectionResult:
    status: str  # completed | partial | error
    data: dict[str, Any] | None = None
    execution: TestExecutionResult | None = None
    duration_ms: float = 0.0
    total_tests: int = 0
    measured_tests: int = 0
    covered_files: int = 0
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


class CoverageCollector:
    """Run pytest under ``coverage run`` and read dynamic contexts.

    The context plugin is standalone (it only imports ``coverage``) and lives in
    a temporary directory. Test code is executed in a subprocess with a timeout
    and a sanitized environment.
    """

    def __init__(
        self,
        repo_path: str | Path,
        python_executable: str | None = None,
        timeout_seconds: int | None = None,
    ):
        self.repo_path = Path(repo_path).resolve()
        self.executor = TestExecutor(
            self.repo_path,
            python_executable=python_executable,
            timeout_seconds=timeout_seconds,
        )

    def collect(
        self,
        tests: list[TestCase] | list[str] | None = None,
        test_ids: list[str] | None = None,
        timeout_seconds: int | None = None,
    ) -> CoverageCollectionResult:
        """Collect coverage for all tests or a specific set.

        ``tests`` may be discovered :class:`TestCase` objects. ``test_ids`` is a
        lower-level override used by benchmarks and tests.
        """
        if test_ids is None and tests is not None:
            test_ids = [
                t.node_id if isinstance(t, TestCase) else str(t) for t in tests
            ]

        with tempfile.TemporaryDirectory(prefix="impactmap-coverage-") as tmp:
            tmp_path = Path(tmp)
            plugin_dir = tmp_path / "plugin"
            plugin_dir.mkdir()
            (plugin_dir / "impactmap_coverage_plugin.py").write_text(
                CONTEXT_PLUGIN_SOURCE, encoding="utf-8"
            )
            data_file = tmp_path / ".coverage"

            execution = self.executor.run(
                test_ids,
                coverage_data_file=data_file,
                context_plugin_dir=plugin_dir,
                timeout_seconds=timeout_seconds,
            )
            warnings = list(execution.warnings)
            if execution.status == "timeout":
                warnings.append("Coverage may be incomplete because the test run timed out.")
            if not data_file.exists():
                message = (
                    "Coverage data was not produced. The repository's Python "
                    "environment may not have coverage.py installed."
                )
                return CoverageCollectionResult(
                    status="error",
                    execution=execution,
                    duration_ms=execution.duration_ms,
                    warnings=warnings,
                    error=message,
                )

            try:
                return self._read_coverage(
                    data_file, execution, warnings
                )
            except Exception as exc:  # coverage format errors are surfaced, not hidden
                logger.exception("Failed to read coverage data")
                return CoverageCollectionResult(
                    status="error",
                    execution=execution,
                    duration_ms=execution.duration_ms,
                    warnings=warnings,
                    error=f"Could not read coverage data: {exc}",
                )

    def _read_coverage(
        self,
        data_file: Path,
        execution: TestExecutionResult,
        warnings: list[str],
    ) -> CoverageCollectionResult:
        coverage_data = coverage.CoverageData(basename=str(data_file))
        coverage_data.read()

        test_contexts = sorted(
            context for context in coverage_data.measured_contexts() if context
        )
        context_index = {context: index for index, context in enumerate(test_contexts)}

        files: dict[str, Any] = {}
        for filename in sorted(coverage_data.measured_files()):
            path = Path(filename).resolve()
            if not is_within(path, self.repo_path) or path.suffix != ".py":
                continue
            relative = PurePosixPath(path.relative_to(self.repo_path).as_posix())
            if is_test_path(relative.as_posix()):
                continue
            try:
                executed_lines = sorted(coverage_data.lines(filename) or [])
                contexts_by_line = coverage_data.contexts_by_lineno(filename)
            except Exception:
                continue
            if not executed_lines:
                continue
            lines: dict[str, list[int]] = {}
            file_tests: set[int] = set()
            for line, contexts in contexts_by_line.items():
                indexes = sorted(
                    {
                        context_index[context]
                        for context in contexts
                        if context in context_index
                    }
                )
                if indexes:
                    lines[str(line)] = indexes
                    file_tests.update(indexes)
            files[relative.as_posix()] = {
                "executed_lines": executed_lines,
                "lines": lines,
                "test_indexes": sorted(file_tests),
            }

        contexts_available = bool(test_contexts)
        if not contexts_available:
            warnings.append(
                "Coverage was collected without per-test contexts. "
                "Test selection will use the conservative fallback."
            )
        if not files:
            warnings.append("Coverage did not record any project Python files.")

        data = {
            "version": 1,
            "tests": test_contexts,
            "files": files,
            "contexts_available": contexts_available,
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "source_root": str(self.repo_path),
        }
        status = "completed" if contexts_available and files else "partial"
        return CoverageCollectionResult(
            status=status,
            data=data,
            execution=execution,
            duration_ms=execution.duration_ms,
            total_tests=execution.total_tests,
            measured_tests=len(test_contexts),
            covered_files=len(files),
            warnings=warnings,
        )


def merge_coverage_data(existing: dict[str, Any] | None, new: dict[str, Any]) -> dict[str, Any]:
    """Union two coverage snapshots' context mappings.

    Coverage from a selected test run must not erase contexts collected from the
    full suite, so persisted snapshots are merged.
    """
    if not existing or existing.get("version") != new.get("version"):
        return new
    tests = list(dict.fromkeys(existing.get("tests", []) + new.get("tests", [])))
    index = {test: i for i, test in enumerate(tests)}
    files: dict[str, Any] = {}

    def add_file(rel: str, payload: dict[str, Any], old_tests: list[str]) -> None:
        old_index = {test: index[test] for test in old_tests if test in index}
        entry = files.setdefault(
            rel,
            {"executed_lines": set(), "lines": {}, "test_indexes": set()},
        )
        entry["executed_lines"].update(payload.get("executed_lines", []))
        for line, indexes in payload.get("lines", {}).items():
            mapped = {old_index[old_tests[i]] for i in indexes if i < len(old_tests)}
            entry["lines"].setdefault(str(line), set()).update(mapped)
            entry["test_indexes"].update(mapped)

    for rel, payload in (existing.get("files") or {}).items():
        add_file(rel, payload, existing.get("tests", []))
    for rel, payload in (new.get("files") or {}).items():
        add_file(rel, payload, new.get("tests", []))

    serialized = {
        rel: {
            "executed_lines": sorted(payload["executed_lines"]),
            "lines": {
                line: sorted(indexes)
                for line, indexes in sorted(payload["lines"].items(), key=lambda kv: int(kv[0]))
            },
            "test_indexes": sorted(payload["test_indexes"]),
        }
        for rel, payload in files.items()
    }
    return {
        "version": 1,
        "tests": tests,
        "files": serialized,
        "contexts_available": bool(tests),
        "collected_at": new.get("collected_at") or existing.get("collected_at"),
        "source_root": new.get("source_root"),
        "merged": True,
    }
