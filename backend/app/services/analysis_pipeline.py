"""Shared synchronous analysis pipeline used by analysis and benchmark services."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.engine.git.change_detector import ChangeSet, GitChangeDetector
from app.engine.graph.code_graph import CodeGraph, GraphBuilder
from app.engine.impact.impact_analyzer import ImpactAnalyzer, ImpactResult
from app.engine.scanner.repository_scanner import RepositoryScanResult, RepositoryScanner
from app.engine.test_selection.discovery import TestCase, TestDiscovery
from app.engine.test_selection.selector import SelectionResult, TestSelector


@dataclass
class AnalysisPipeline:
    """All intermediate results from one analysis pass."""

    repo_path: str
    scan: RepositoryScanResult
    graph: CodeGraph
    changeset: ChangeSet
    impact: ImpactResult
    tests: list[TestCase]
    selector: TestSelector
    selection: SelectionResult
    duration_ms: float = 0.0
    warnings: list[str] = field(default_factory=list)

    @property
    def graph_stats(self) -> dict[str, Any]:
        return self.graph.stats()


def run_analysis_pipeline(
    repo_path: str,
    base_ref: str,
    head_ref: str,
    *,
    include_tests: bool = False,
    coverage_data: dict[str, Any] | None = None,
    historical_failures: list[str] | None = None,
) -> AnalysisPipeline:
    """Run scan -> graph -> diff -> impact -> test discovery -> selection.

    This function is intentionally synchronous: callers run it in a worker
    thread so the FastAPI event loop is never blocked by CPU-bound AST work or
    Git subprocesses.
    """
    start = time.monotonic()
    repo = Path(repo_path).resolve()

    scan = RepositoryScanner().scan(repo)
    graph = GraphBuilder().build(scan)
    changeset = GitChangeDetector(repo).detect(base_ref=base_ref, head_ref=head_ref)
    impact = ImpactAnalyzer(graph, include_tests=include_tests).analyze(changeset)
    tests = TestDiscovery().discover(repo)
    selector = TestSelector(
        graph=graph,
        changeset=changeset,
        impact=impact,
        tests=tests,
        coverage_data=coverage_data,
        historical_failures=historical_failures,
    )
    selection = selector.select()

    duration_ms = (time.monotonic() - start) * 1000
    warnings = list(dict.fromkeys(scan.warnings + changeset.warnings + selection.warnings))
    return AnalysisPipeline(
        repo_path=str(repo),
        scan=scan,
        graph=graph,
        changeset=changeset,
        impact=impact,
        tests=tests,
        selector=selector,
        selection=selection,
        duration_ms=duration_ms,
        warnings=warnings,
    )
