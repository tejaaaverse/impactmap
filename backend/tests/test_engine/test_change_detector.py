"""Tests for Git change detection."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.engine.git.change_detector import (
    GitChangeDetector,
    GitDetectionError,
    parse_unified_diff,
)
from tests.conftest import commit_all, init_git_repo


def detector(repo: Path) -> GitChangeDetector:
    return GitChangeDetector(repo)


class TestGitChangeDetector:
    def test_modified_function_is_detected(self, git_repo: Path):
        helper = git_repo / "utils" / "math_helpers.py"
        helper.write_text(helper.read_text().replace("return a + b", "return a + b + 0"))
        commit_all(git_repo, "change add")

        changeset = detector(git_repo).detect("HEAD~1", "HEAD")
        assert changeset.summary["files"] == 1
        assert changeset.files[0].path == "utils/math_helpers.py"
        assert changeset.files[0].change_type == "modified"
        assert any(
            entity.kind == "function"
            and entity.qualified_name == "utils.math_helpers.add"
            and entity.change_type == "modified"
            for entity in changeset.entities
        )

    def test_added_file_is_fully_changed(self, git_repo: Path):
        (git_repo / "extra.py").write_text(
            "def brand_new(value):\n    return value + 1\n"
        )
        commit_all(git_repo, "add module")

        changeset = detector(git_repo).detect("HEAD~1", "HEAD")
        added = [f for f in changeset.files if f.path == "extra.py"]
        assert added and added[0].change_type == "added"
        assert added[0].added_line_count == 2
        assert any(
            entity.qualified_name == "extra.brand_new" for entity in changeset.entities
        )

    def test_deleted_file_reports_deleted_entities(self, git_repo: Path):
        (git_repo / "utils" / "math_helpers.py").unlink()
        commit_all(git_repo, "delete helpers")

        changeset = detector(git_repo).detect("HEAD~1", "HEAD")
        deleted = [f for f in changeset.files if f.path == "utils/math_helpers.py"]
        assert deleted and deleted[0].change_type == "deleted"
        assert any(
            entity.qualified_name == "utils.math_helpers.add"
            and entity.change_type == "deleted"
            for entity in changeset.entities
        )

    def test_working_tree_changes(self, git_repo: Path):
        validator = git_repo / "utils" / "validators.py"
        validator.write_text(
            validator.read_text()
            + "\n\ndef validate_text(value: str) -> None:\n    if not value:\n        raise ValueError\n"
        )
        (git_repo / "untracked.py").write_text("def untracked():\n    pass\n")

        changeset = detector(git_repo).detect("HEAD", "WORKING")
        paths = {f.path for f in changeset.files}
        assert "utils/validators.py" in paths
        assert "untracked.py" in paths
        assert changeset.is_working_tree is True
        assert any(e.qualified_name == "untracked.untracked" for e in changeset.entities)

    def test_invalid_ref_is_rejected(self, git_repo: Path):
        with pytest.raises((GitDetectionError, ValueError)):
            detector(git_repo).detect("--help", "HEAD")

        with pytest.raises(GitDetectionError):
            detector(git_repo).detect("definitely-not-a-ref", "HEAD")

    def test_non_git_directory_is_rejected(self, tmp_path: Path):
        (tmp_path / "module.py").write_text("x = 1\n")
        with pytest.raises(GitDetectionError, match="Not a Git repository"):
            detector(tmp_path).detect("HEAD", "WORKING")

    def test_unchanged_tree_has_no_files(self, git_repo: Path):
        changeset = detector(git_repo).detect("HEAD", "HEAD")
        assert changeset.files == []
        assert changeset.warnings


class TestUnifiedDiffParser:
    def test_parses_multiple_hunks(self):
        diff = (
            "diff --git a/mod.py b/mod.py\n"
            "--- a/mod.py\n"
            "+++ b/mod.py\n"
            "@@ -1,2 +1,3 @@ def alpha():\n"
            "@@ -10 +11,2 @@\n"
        )
        hunks = parse_unified_diff(diff)["mod.py"]
        assert len(hunks) == 2
        assert hunks[0].old_start == 1 and hunks[0].old_count == 2
        assert hunks[0].new_start == 1 and hunks[0].new_count == 3
        assert hunks[1].old_count == 1 and hunks[1].new_count == 2

    def test_deleted_file_uses_old_path(self):
        diff = (
            "diff --git a/gone.py b/gone.py\n"
            "--- a/gone.py\n"
            "+++ /dev/null\n"
            "@@ -1,2 +0,0 @@\n"
        )
        assert "gone.py" in parse_unified_diff(diff)
