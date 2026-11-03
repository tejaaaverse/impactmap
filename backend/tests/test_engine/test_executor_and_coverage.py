"""Tests for subprocess execution and coverage collection."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app.engine.test_selection.coverage_collector import (
    CoverageCollector,
    merge_coverage_data,
)
from app.engine.test_selection.executor import TestExecutor


class TestTestExecutor:
    def test_full_suite_runs(self, sample_repo_copy: Path):
        executor = TestExecutor(sample_repo_copy, timeout_seconds=120)
        result = executor.run(None)
        assert result.status == "completed"
        assert result.exit_code == 0
        assert result.total_tests == 20
        assert result.passed == 20
        assert result.failed == 0
        assert result.duration_ms > 0
        assert result.command[0] == sys.executable

    def test_selected_test_runs(self, sample_repo_copy: Path):
        executor = TestExecutor(sample_repo_copy, timeout_seconds=120)
        result = executor.run(["tests/test_math_helpers.py::test_add"])
        assert result.status == "completed"
        assert result.passed == 1
        assert result.total_tests == 1

    def test_empty_selection_does_not_execute(self, sample_repo_copy: Path):
        executor = TestExecutor(sample_repo_copy)
        result = executor.run([])
        assert result.status == "no_tests"
        assert result.total_tests == 0
        assert result.duration_ms == 0

    def test_rejects_path_traversal(self, sample_repo_copy: Path):
        executor = TestExecutor(sample_repo_copy)
        with pytest.raises(ValueError, match="outside the repository"):
            executor.run(["../outside.py::test_escape"])

    def test_rejects_option_injection(self, sample_repo_copy: Path):
        executor = TestExecutor(sample_repo_copy)
        with pytest.raises(ValueError, match="Invalid test ID"):
            executor.run(["-k anything"])

    def test_timeout_is_enforced(self, sample_repo_copy: Path):
        tests_dir = sample_repo_copy / "tests"
        (tests_dir / "test_slow.py").write_text(
            "import time\n\n\ndef test_slow():\n    time.sleep(5)\n"
        )
        executor = TestExecutor(sample_repo_copy, timeout_seconds=2)
        result = executor.run(["tests/test_slow.py::test_slow"])
        assert result.status == "timeout"
        assert result.timed_out is True
        assert result.duration_ms < 10_000


class TestCoverageCollector:
    def test_collects_per_test_contexts(self, sample_repo_copy: Path):
        collector = CoverageCollector(sample_repo_copy, timeout_seconds=120)
        result = collector.collect()
        assert result.status == "completed"
        assert result.error is None
        assert result.measured_tests == 20
        assert result.covered_files >= 3
        assert result.data["contexts_available"] is True
        assert "utils/math_helpers.py" in result.data["files"]
        assert "tests/test_math_helpers.py" not in result.data["files"]

    def test_selected_subset_coverage_can_be_merged(self, sample_repo_copy: Path):
        collector = CoverageCollector(sample_repo_copy, timeout_seconds=120)
        result = collector.collect(test_ids=["tests/test_math_helpers.py::test_add"])
        assert result.status == "completed"
        assert result.measured_tests == 1
        merged = merge_coverage_data(None, result.data)
        assert merged["tests"] == ["tests/test_math_helpers.py::test_add"]
        assert merged["files"]

    def test_coverage_data_contains_line_to_test_mapping(self, sample_repo_copy: Path):
        collector = CoverageCollector(sample_repo_copy, timeout_seconds=120)
        result = collector.collect()
        payload = result.data["files"]["utils/math_helpers.py"]
        assert payload["executed_lines"]
        assert payload["lines"]
        for indexes in payload["lines"].values():
            assert all(0 <= index < len(result.data["tests"]) for index in indexes)
