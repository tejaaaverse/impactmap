"""Tests for the dependency graph builder."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.engine.graph.code_graph import GraphBuilder, is_test_path, resolve_relative_module
from app.engine.parser.python_parser import ImportInfo
from app.engine.scanner.repository_scanner import RepositoryScanner


def build_graph(repo: Path):
    scan = RepositoryScanner().scan(repo)
    return scan, GraphBuilder().build(scan)


@pytest.fixture
def dependency_repo(tmp_path: Path) -> Path:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("from .engine import Engine\n")
    (pkg / "base.py").write_text(
        "class Base:\n"
        "    def base_method(self):\n"
        "        return 1\n"
    )
    (pkg / "engine.py").write_text(
        "from pkg.base import Base\n"
        "from pkg.helpers import compute\n\n"
        "class Engine(Base):\n"
        "    def run(self):\n"
        "        return compute(2)\n"
    )
    (pkg / "helpers.py").write_text(
        "def compute(value):\n"
        "    return value * 2\n"
    )
    (tmp_path / "app.py").write_text(
        "from pkg import Engine\n\n"
        "def main():\n"
        "    return Engine().run()\n"
    )
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_app.py").write_text(
        "from app import main\n\n"
        "def test_main():\n"
        "    assert main() == 4\n"
    )
    return tmp_path


class TestCodeGraph:
    def test_nodes_use_repository_relative_paths(self, dependency_repo):
        scan, graph = build_graph(dependency_repo)
        assert "file:pkg/helpers.py" in graph.graph
        assert all(not node_id.startswith("file:/") for node_id in graph.graph.nodes)

    def test_import_symbol_and_call_edges(self, dependency_repo):
        _, graph = build_graph(dependency_repo)
        engine_file = "file:pkg/engine.py"
        targets = {
            target
            for _, target, _ in graph.graph.out_edges(engine_file, data=True)
        }
        assert "func:pkg/helpers.py::pkg.helpers.compute" in targets
        assert "class:pkg/base.py::pkg.base.Base" in targets

        run_id = "method:pkg/engine.py::pkg.engine.Engine.run"
        call_targets = {
            target
            for _, target, _ in graph.graph.out_edges(run_id, data=True)
        }
        assert "func:pkg/helpers.py::pkg.helpers.compute" in call_targets

    def test_inheritance_edge(self, dependency_repo):
        _, graph = build_graph(dependency_repo)
        class_id = "class:pkg/engine.py::pkg.engine.Engine"
        inheritance = [
            (target, data)
            for _, target, data in graph.graph.out_edges(class_id, data=True)
            if data["type"] == "inherits"
        ]
        assert inheritance
        assert inheritance[0][0] == "class:pkg/base.py::pkg.base.Base"

    def test_relative_import_is_resolved(self, dependency_repo):
        _, graph = build_graph(dependency_repo)
        init_file = "file:pkg/__init__.py"
        targets = {
            target
            for _, target, data in graph.graph.out_edges(init_file, data=True)
            if data["type"] in ("import", "import_symbol")
        }
        assert "class:pkg/engine.py::pkg.engine.Engine" in targets

    def test_containment_edges(self, dependency_repo):
        _, graph = build_graph(dependency_repo)
        assert graph.graph.has_edge(
            "file:pkg/helpers.py", "func:pkg/helpers.py::pkg.helpers.compute"
        )
        assert graph.graph.has_edge(
            "class:pkg/engine.py::pkg.engine.Engine",
            "method:pkg/engine.py::pkg.engine.Engine.run",
        )

    def test_test_nodes_are_flagged(self, dependency_repo):
        _, graph = build_graph(dependency_repo)
        assert graph.graph.nodes["file:tests/test_app.py"]["is_test"] is True
        assert graph.graph.nodes["file:pkg/helpers.py"]["is_test"] is False

    def test_serialization_round_trip(self, dependency_repo):
        _, graph = build_graph(dependency_repo)
        payload = graph.to_dict(include_tests=False)
        node_ids = {node["id"] for node in payload["nodes"]}
        assert not any(node_id.startswith("file:tests/") for node_id in node_ids)
        assert all(edge["source"] in node_ids for edge in payload["edges"])
        # Stats describe the whole graph; nodes may be filtered for display.
        assert payload["stats"]["nodes"] >= len(payload["nodes"])

    def test_unresolved_imports_are_recorded(self, tmp_path):
        (tmp_path / "module.py").write_text("import requests\n")
        _, graph = build_graph(tmp_path)
        assert any(item["module"] == "requests" for item in graph.unresolved_imports)


class TestHelpers:
    def test_is_test_path(self):
        assert is_test_path("tests/test_a.py")
        assert is_test_path("pkg/test/test_b.py")
        assert is_test_path("module_test.py")
        assert not is_test_path("pkg/testing_helpers.py")

    def test_resolve_relative_imports(self):
        imp = ImportInfo(module="engine", is_from_import=True, level=1)
        assert resolve_relative_module("pkg", True, imp) == "pkg.engine"
        assert resolve_relative_module("pkg.sub", False, imp) == "pkg.engine"

        up_one = ImportInfo(module="helpers", is_from_import=True, level=2)
        assert resolve_relative_module("pkg.sub", False, up_one) == "helpers"

        bare = ImportInfo(module="", is_from_import=True, level=1)
        assert resolve_relative_module("pkg.sub", False, bare) == "pkg"
