"""Pytest test discovery (static, no test execution)."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from app.engine.parser.python_parser import file_path_to_module_name
from app.engine.scanner.file_discovery import FileDiscovery
from app.core.logging import logger


@dataclass
class TestCase:
    node_id: str
    file_path: str
    name: str
    class_name: str | None = None
    line_start: int = 0
    line_end: int = 0
    module_name: str = ""

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "file_path": self.file_path,
            "name": self.name,
            "class_name": self.class_name,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "module_name": self.module_name,
        }

    @property
    def normalized_id(self) -> str:
        """Strip pytest parameterization suffix for matching."""
        return self.node_id.split("[", 1)[0]


class TestDiscovery:
    """Not a pytest test class; disables accidental collection."""

    __test__ = False

    """Discover pytest-style test functions without importing test modules."""

    def __init__(self):
        self.file_discovery = FileDiscovery()

    def discover(self, repo_path: str | Path) -> list[TestCase]:
        repo_path = Path(repo_path).resolve()
        discovery = self.file_discovery.discover(repo_path)
        tests: list[TestCase] = []

        for discovered in discovery.files:
            if not _is_test_file(discovered.relative_path):
                continue
            try:
                source = discovered.absolute_path.read_text(encoding="utf-8", errors="replace")
                tree = ast.parse(source, filename=str(discovered.absolute_path))
            except (OSError, SyntaxError) as exc:
                logger.warning(f"Could not parse test file {discovered.relative_path}: {exc}")
                continue
            module_name = file_path_to_module_name(discovered.relative_path, str(repo_path))
            rel = PurePosixPath(discovered.relative_path.replace("\\", "/")).as_posix()
            tests.extend(_tests_from_ast(tree, rel, module_name))

        tests.sort(key=lambda t: t.node_id)
        logger.info(f"Discovered {len(tests)} pytest tests in {repo_path}")
        return tests


def _tests_from_ast(tree: ast.Module, rel_path: str, module_name: str) -> list[TestCase]:
    tests: list[TestCase] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if _is_test_name(node.name):
                tests.append(
                    TestCase(
                        node_id=f"{rel_path}::{node.name}",
                        file_path=rel_path,
                        name=node.name,
                        line_start=node.lineno,
                        line_end=node.end_lineno or node.lineno,
                        module_name=module_name,
                    )
                )
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_test_name(
                    child.name
                ):
                    tests.append(
                        TestCase(
                            node_id=f"{rel_path}::{node.name}::{child.name}",
                            file_path=rel_path,
                            name=child.name,
                            class_name=node.name,
                            line_start=child.lineno,
                            line_end=child.end_lineno or child.lineno,
                            module_name=module_name,
                        )
                    )
    return tests


def _is_test_name(name: str) -> bool:
    return name.startswith("test")


def _is_test_file(relative_path: str) -> bool:
    path = PurePosixPath(relative_path.replace("\\", "/"))
    parts = {p.lower() for p in path.parts[:-1]}
    name = path.name.lower()
    return name.startswith("test_") or name.endswith("_test.py") or "tests" in parts or "test" in parts
