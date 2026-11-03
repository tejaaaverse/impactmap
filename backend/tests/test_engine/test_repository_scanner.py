"""
Tests for the repository scanner module.
"""

import pytest
from pathlib import Path

from app.engine.scanner.repository_scanner import RepositoryScanner


@pytest.fixture
def scanner():
    return RepositoryScanner()


@pytest.fixture
def sample_repo(tmp_path):
    """Create a small repository structure."""
    # Main module
    (tmp_path / "main.py").write_text(
        'from helpers import greet\n\ndef main():\n    greet("World")\n'
    )

    # Helper module
    (tmp_path / "helpers.py").write_text(
        'def greet(name: str) -> str:\n    """Say hello."""\n    return f"Hello, {name}!"\n\n'
        'def farewell(name: str) -> str:\n    return f"Goodbye, {name}!"\n'
    )

    # Package
    pkg = tmp_path / "core"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("from .engine import Engine\n")
    (pkg / "engine.py").write_text(
        "class Engine:\n"
        '    """Core engine."""\n'
        "    def run(self):\n"
        "        pass\n"
        "    def stop(self):\n"
        "        pass\n"
    )

    # Ignored dirs
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "venv").mkdir()

    return tmp_path


class TestRepositoryScanner:
    def test_scan_produces_result(self, scanner, sample_repo):
        result = scanner.scan(sample_repo)
        assert result.repo_name == sample_repo.name
        assert result.repo_path == str(sample_repo)

    def test_scan_discovers_all_files(self, scanner, sample_repo):
        result = scanner.scan(sample_repo)
        # main.py, helpers.py, core/__init__.py, core/engine.py = 4
        assert result.summary.total_files == 4

    def test_scan_finds_functions(self, scanner, sample_repo):
        result = scanner.scan(sample_repo)
        # main(), greet(), farewell() = 3
        assert result.summary.total_functions == 3

    def test_scan_finds_classes(self, scanner, sample_repo):
        result = scanner.scan(sample_repo)
        # Engine = 1
        assert result.summary.total_classes == 1

    def test_scan_finds_methods(self, scanner, sample_repo):
        result = scanner.scan(sample_repo)
        # Engine.run(), Engine.stop() = 2
        assert result.summary.total_methods == 2

    def test_scan_finds_imports(self, scanner, sample_repo):
        result = scanner.scan(sample_repo)
        assert result.summary.total_imports > 0

    def test_scan_duration_recorded(self, scanner, sample_repo):
        result = scanner.scan(sample_repo)
        assert result.summary.scan_duration_ms > 0

    def test_scan_invalid_path(self, scanner):
        with pytest.raises(ValueError):
            scanner.scan("/totally/fake/path")

    def test_scan_empty_directory(self, scanner, tmp_path):
        result = scanner.scan(tmp_path)
        assert result.summary.total_files == 0
        assert result.summary.total_functions == 0
        assert result.summary.total_classes == 0

    def test_scan_with_syntax_errors(self, scanner, tmp_path):
        (tmp_path / "broken.py").write_text("def oops(\n")
        (tmp_path / "good.py").write_text("def fine():\n    pass\n")

        result = scanner.scan(tmp_path)
        # Should still scan the good file
        assert result.summary.total_files == 2
        assert result.summary.total_functions == 1  # Only from good.py
        assert len(result.warnings) > 0

    def test_scan_modules_contain_parse_results(self, scanner, sample_repo):
        result = scanner.scan(sample_repo)
        assert len(result.modules) == result.summary.total_files

        for module in result.modules:
            assert module.file_path != ""
            assert module.module_name is not None

    def test_scan_sample_calculator(self, scanner):
        """Test scanning the bundled sample calculator repository."""
        sample_path = Path(__file__).parent.parent.parent.parent / "sample_repositories" / "calculator"
        if not sample_path.exists():
            pytest.skip("Sample calculator repository not found")

        result = scanner.scan(sample_path)
        assert result.summary.total_files > 0
        assert result.summary.total_functions > 0
        assert result.summary.total_classes > 0
