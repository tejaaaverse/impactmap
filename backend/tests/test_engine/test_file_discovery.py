"""
Tests for the file discovery module.
"""

import pytest
from pathlib import Path
import tempfile
import os

from app.engine.scanner.file_discovery import FileDiscovery, DiscoveredFile


@pytest.fixture
def discovery():
    return FileDiscovery()


@pytest.fixture
def sample_repo(tmp_path):
    """Create a temporary repository structure for testing."""
    # Create Python files
    (tmp_path / "main.py").write_text("print('hello')\n")
    (tmp_path / "utils.py").write_text("def helper():\n    pass\n")

    # Create subdirectory with files
    pkg = tmp_path / "mypackage"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "module_a.py").write_text("class MyClass:\n    pass\n")

    # Create directories that should be ignored
    venv = tmp_path / "venv"
    venv.mkdir()
    (venv / "should_ignore.py").write_text("# ignored")

    pycache = tmp_path / "__pycache__"
    pycache.mkdir()
    (pycache / "cached.py").write_text("# ignored")

    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_text("# git config")

    # Non-Python file
    (tmp_path / "README.md").write_text("# Readme")
    (tmp_path / "data.json").write_text("{}")

    return tmp_path


class TestFileDiscovery:
    def test_discovers_python_files(self, discovery, sample_repo):
        result = discovery.discover(sample_repo)
        py_paths = {f.relative_path for f in result.files}

        assert "main.py" in py_paths
        assert "utils.py" in py_paths
        assert os.path.join("mypackage", "__init__.py") in py_paths
        assert os.path.join("mypackage", "module_a.py") in py_paths

    def test_ignores_venv(self, discovery, sample_repo):
        result = discovery.discover(sample_repo)
        py_paths = {f.relative_path for f in result.files}

        for path in py_paths:
            assert "venv" not in path

    def test_ignores_pycache(self, discovery, sample_repo):
        result = discovery.discover(sample_repo)
        py_paths = {f.relative_path for f in result.files}

        for path in py_paths:
            assert "__pycache__" not in path

    def test_ignores_git(self, discovery, sample_repo):
        result = discovery.discover(sample_repo)
        py_paths = {f.relative_path for f in result.files}

        for path in py_paths:
            assert ".git" not in path

    def test_ignores_non_python_files(self, discovery, sample_repo):
        result = discovery.discover(sample_repo)
        py_paths = {f.relative_path for f in result.files}

        assert "README.md" not in py_paths
        assert "data.json" not in py_paths

    def test_counts_file_sizes(self, discovery, sample_repo):
        result = discovery.discover(sample_repo)
        assert result.total_size_bytes > 0

    def test_counts_lines(self, discovery, sample_repo):
        result = discovery.discover(sample_repo)
        for f in result.files:
            if f.relative_path == "main.py":
                assert f.line_count >= 1

    def test_skipped_dirs_recorded(self, discovery, sample_repo):
        result = discovery.discover(sample_repo)
        assert len(result.skipped_dirs) > 0

    def test_invalid_path_raises(self, discovery):
        with pytest.raises(ValueError, match="does not exist"):
            discovery.discover(Path("/nonexistent/path/to/repo"))

    def test_file_path_raises(self, discovery, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("content")
        with pytest.raises(ValueError, match="not a directory"):
            discovery.discover(f)

    def test_empty_directory(self, discovery, tmp_path):
        result = discovery.discover(tmp_path)
        assert len(result.files) == 0
        assert len(result.errors) == 0

    def test_correct_file_count(self, discovery, sample_repo):
        result = discovery.discover(sample_repo)
        # main.py, utils.py, mypackage/__init__.py, mypackage/module_a.py = 4
        assert len(result.files) == 4
