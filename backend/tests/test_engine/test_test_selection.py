"""Tests for pytest discovery and intelligent test selection."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.engine.git.change_detector import GitChangeDetector
from app.engine.graph.code_graph import GraphBuilder
from app.engine.impact.impact_analyzer import ImpactAnalyzer
from app.engine.scanner.repository_scanner import RepositoryScanner
from app.engine.test_selection.coverage_collector import merge_coverage_data
from app.engine.test_selection.discovery import TestDiscovery
from app.engine.test_selection.selector import TestSelector


@pytest.fixture
def changed_sample(git_repo: Path) -> Path:
    helper = git_repo / "utils" / "math_helpers.py"
    helper.write_text(helper.read_text().replace("return a + b", "return a + b + 0"))
    return git_repo


def context(repo: Path):
    graph = GraphBuilder().build(RepositoryScanner().scan(repo))
    changeset = GitChangeDetector(repo).detect("HEAD", "WORKING")
    impact = ImpactAnalyzer(graph).analyze(changeset)
    tests = TestDiscovery().discover(repo)
    return graph, changeset, impact, tests


def synthetic_coverage(test_id: str, file_path: str, line: int) -> dict:
    return {
        "version": 1,
        "tests": [test_id],
        "files": {
            file_path: {
                "executed_lines": [line],
                "lines": {str(line): [0]},
                "test_indexes": [0],
            }
        },
        "contexts_available": True,
        "collected_at": "2026-01-01T00:00:00+00:00",
        "source_root": "/repo",
    }


class TestTestDiscovery:
    def test_discovers_functions_and_class_methods(self, sample_repo_copy: Path):
        tests = TestDiscovery().discover(sample_repo_copy)
        ids = {test.node_id for test in tests}
        assert "tests/test_math_helpers.py::test_add" in ids
        assert "tests/test_calculator.py::TestCalculator::test_add" in ids
        assert len(tests) == 20

    def test_ignores_non_test_files(self, tmp_path: Path):
        (tmp_path / "helpers.py").write_text("def test_looking():\n    pass\n")
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_real.py").write_text(
            "def test_one():\n    pass\n\nasync def test_async():\n    pass\n"
        )
        tests = TestDiscovery().discover(tmp_path)
        assert [t.node_id for t in tests] == [
            "tests/test_real.py::test_async",
            "tests/test_real.py::test_one",
        ]

    def test_handles_syntax_errors(self, tmp_path: Path):
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_broken.py").write_text("def test_broken(:\n")
        (tests_dir / "test_ok.py").write_text("def test_ok():\n    pass\n")
        tests = TestDiscovery().discover(tmp_path)
        assert [t.node_id for t in tests] == ["tests/test_ok.py::test_ok"]


class TestSelectorWithoutCoverage:
    def test_safe_falls_back_to_full_suite(self, changed_sample: Path):
        graph, changeset, impact, tests = context(changed_sample)
        result = TestSelector(graph, changeset, impact, tests, None).select()
        assert result.coverage_available is False
        assert result.safe.fallback_used is True
        assert result.safe.selected_count == len(tests)
        assert any("unavailable" in warning for warning in result.warnings)

    def test_optimized_uses_static_evidence(self, changed_sample: Path):
        graph, changeset, impact, tests = context(changed_sample)
        result = TestSelector(graph, changeset, impact, tests, None).select()
        ids = [test.test_id for test in result.optimized.selected]
        assert ids == ["tests/test_math_helpers.py::test_add"]
        assert result.optimized.fallback_used is False
        assert any("static" in warning.lower() for warning in result.optimized.warnings)

    def test_no_static_match_falls_back_with_warning(self, git_repo: Path):
        (git_repo / "orphan.py").write_text("def orphan():\n    return 1\n")
        graph, changeset, impact, tests = context(git_repo)
        result = TestSelector(graph, changeset, impact, tests, None).select()
        assert result.optimized.fallback_used is True
        assert result.optimized.selected_count == len(tests)
        assert any("fell back" in warning for warning in result.optimized.warnings)

    def test_changed_test_file_is_boosted(self, git_repo: Path):
        test_file = git_repo / "tests" / "test_validators.py"
        test_file.write_text(test_file.read_text() + "\n\ndef test_extra():\n    assert True\n")
        graph, changeset, impact, tests = context(git_repo)
        result = TestSelector(graph, changeset, impact, tests, None).select()
        changed = [
            test for test in result.safe.selected if test.file_path == "tests/test_validators.py"
        ]
        assert changed
        assert all(test.source in ("changed_test", "static", "conservative") for test in changed)
        assert any("test file itself changed" in " ".join(t.reasons) for t in changed)


class TestSelectorWithCoverage:
    def test_coverage_links_test_to_changed_entity(self, changed_sample: Path):
        graph, changeset, impact, tests = context(changed_sample)
        coverage = synthetic_coverage(
            "tests/test_math_helpers.py::test_add", "utils/math_helpers.py", 6
        )
        result = TestSelector(graph, changeset, impact, tests, coverage).select()
        assert result.coverage_available is True
        optimized = [t.test_id for t in result.optimized.selected]
        assert optimized == ["tests/test_math_helpers.py::test_add"]
        selected = result.optimized.selected[0]
        assert selected.source == "coverage"
        assert "Covers changed code" in " ".join(selected.reasons)

    def test_safe_keeps_coverage_linked_tests(self, changed_sample: Path):
        graph, changeset, impact, tests = context(changed_sample)
        coverage = synthetic_coverage(
            "tests/test_math_helpers.py::test_add", "utils/math_helpers.py", 6
        )
        result = TestSelector(graph, changeset, impact, tests, coverage).select()
        ids = [t.test_id for t in result.safe.selected]
        assert "tests/test_math_helpers.py::test_add" in ids
        assert result.safe.selected_count < len(tests)

    def test_precision_recall_are_measured(self, changed_sample: Path):
        graph, changeset, impact, tests = context(changed_sample)
        coverage = synthetic_coverage(
            "tests/test_math_helpers.py::test_add", "utils/math_helpers.py", 6
        )
        selector = TestSelector(graph, changeset, impact, tests, coverage)
        precision, recall = selector.coverage_precision_recall(
            ["tests/test_math_helpers.py::test_add"]
        )
        assert precision == 1.0
        assert recall == 1.0

    def test_missing_contexts_uses_fallback(self, changed_sample: Path):
        graph, changeset, impact, tests = context(changed_sample)
        coverage = synthetic_coverage(
            "tests/test_math_helpers.py::test_add", "utils/math_helpers.py", 6
        )
        coverage["contexts_available"] = False
        result = TestSelector(graph, changeset, impact, tests, coverage).select()
        assert result.coverage_available is False
        assert result.safe.fallback_used is True

    def test_historical_failure_boosts_score(self, changed_sample: Path):
        graph, changeset, impact, tests = context(changed_sample)
        coverage = synthetic_coverage(
            "tests/test_math_helpers.py::test_add", "utils/math_helpers.py", 6
        )
        selector = TestSelector(
            graph,
            changeset,
            impact,
            tests,
            coverage,
            historical_failures=["tests/test_math_helpers.py::test_add"],
        )
        result = selector.select()
        selected = result.optimized.selected[0]
        assert selected.previously_failed is True
        assert any("failed" in reason.lower() for reason in selected.reasons)
        assert selected.score >= 20


class TestCoverageMerge:
    def test_merge_unions_tests_and_lines(self):
        first = synthetic_coverage("tests/test_a.py::test_one", "pkg/a.py", 4)
        second = synthetic_coverage("tests/test_b.py::test_two", "pkg/a.py", 8)
        merged = merge_coverage_data(first, second)
        assert merged["tests"] == [
            "tests/test_a.py::test_one",
            "tests/test_b.py::test_two",
        ]
        assert merged["files"]["pkg/a.py"]["lines"]["4"] == [0]
        assert merged["files"]["pkg/a.py"]["lines"]["8"] == [1]
        assert merged["merged"] is True

    def test_merge_into_empty_returns_new(self):
        data = synthetic_coverage("tests/test_a.py::test_one", "pkg/a.py", 4)
        assert merge_coverage_data(None, data) is data
