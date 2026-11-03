"""Tests for explainable impact traversal and scoring."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.engine.git.change_detector import GitChangeDetector
from app.engine.graph.code_graph import GraphBuilder
from app.engine.impact.impact_analyzer import ImpactAnalyzer
from app.engine.scanner.repository_scanner import RepositoryScanner
from tests.conftest import commit_all, init_git_repo


@pytest.fixture
def chain_repo(tmp_path: Path) -> Path:
    (tmp_path / "core.py").write_text(
        "def compute(value):\n    return value * 2\n"
    )
    (tmp_path / "service.py").write_text(
        "from core import compute\n\n\ndef run(value):\n    return compute(value) + 1\n"
    )
    (tmp_path / "app.py").write_text(
        "from service import run\n\n\ndef main():\n    return run(3)\n"
    )
    return init_git_repo(tmp_path)


def graph_for(repo: Path):
    return GraphBuilder().build(RepositoryScanner().scan(repo))


def analyze(repo: Path, base="HEAD~1", head="HEAD", max_depth=None, include_tests=False):
    graph = graph_for(repo)
    changeset = GitChangeDetector(repo).detect(base, head)
    return ImpactAnalyzer(graph, max_depth=max_depth, include_tests=include_tests).analyze(
        changeset
    )


class TestImpactAnalyzer:
    def test_direct_and_indirect_impacts(self, chain_repo: Path):
        core = chain_repo / "core.py"
        core.write_text(core.read_text().replace("value * 2", "value * 3"))
        commit_all(chain_repo, "change core")

        result = analyze(chain_repo).to_dict()
        direct = {entry["qualified_name"] for entry in result["direct_impacts"]}
        indirect = {entry["qualified_name"] for entry in result["indirect_impacts"]}
        assert "core.compute" in direct
        assert "service.run" in indirect
        assert "app.main" in indirect
        assert result["summary"]["total_affected"] >= 5

    def test_paths_and_reasons_are_explainable(self, chain_repo: Path):
        (chain_repo / "core.py").write_text(
            "def compute(value):\n    return value + 5\n"
        )
        commit_all(chain_repo, "change core")

        result = analyze(chain_repo)
        by_name = {
            entry.qualified_name: entry
            for entry in result.direct + result.indirect
        }
        service = by_name["service.run"]
        assert service.depth == 1
        assert service.path
        assert "calls" in service.reason or "imports" in service.reason
        assert service.confidence > 0
        assert 0 < service.score <= 100

    def test_max_depth_limits_traversal(self, chain_repo: Path):
        (chain_repo / "core.py").write_text(
            "def compute(value):\n    return value * 10\n"
        )
        commit_all(chain_repo, "change core")

        result = analyze(chain_repo, max_depth=1)
        indirect_names = {entry.qualified_name for entry in result.indirect}
        assert "service.run" in indirect_names
        assert "app.main" not in indirect_names

    def test_deleted_function_marks_callers(self, chain_repo: Path):
        (chain_repo / "core.py").write_text("def unrelated():\n    return 0\n")
        commit_all(chain_repo, "remove compute")

        result = analyze(chain_repo)
        direct_names = {entry.qualified_name for entry in result.direct}
        assert "core.compute" in direct_names
        assert "service.run" in direct_names
        deleted = [e for e in result.direct if e.is_deleted]
        assert deleted and deleted[0].node_id.startswith("deleted:")

    def test_deleted_file_marks_importers(self, chain_repo: Path):
        (chain_repo / "core.py").unlink()
        commit_all(chain_repo, "remove core")

        result = analyze(chain_repo)
        reasons = " ".join(entry.reason for entry in result.direct)
        assert "Imports deleted module" in reasons or "deleted" in reasons

    def test_no_changes_returns_empty_impact(self, chain_repo: Path):
        result = analyze(chain_repo, "HEAD", "HEAD")
        assert result.direct == []
        assert result.indirect == []
        assert result.warnings

    def test_tests_are_excluded_by_default(self, tmp_path: Path):
        (tmp_path / "core.py").write_text("def compute():\n    return 1\n")
        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "test_core.py").write_text(
            "from core import compute\n\n\ndef test_compute():\n    assert compute() == 1\n"
        )
        init_git_repo(tmp_path)
        (tmp_path / "core.py").write_text("def compute():\n    return 2\n")
        commit_all(tmp_path, "change")

        excluded = analyze(tmp_path)
        included = analyze(tmp_path, include_tests=True)
        assert not any(e.is_test for e in excluded.direct + excluded.indirect)
        assert excluded.excluded_test_nodes > 0
        assert any(
            "test_compute" in e.qualified_name
            for e in included.direct + included.indirect
        ) or included.excluded_test_nodes == 0
