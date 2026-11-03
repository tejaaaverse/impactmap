"""Git change detection.

Compares a base revision with either another commit or the working tree. The
detector deliberately uses argument-list subprocess calls (never a shell) and
parses unified diffs itself so it can map hunks to Python entity line spans.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from app.core.logging import logger
from app.core.security import is_within, safe_subprocess_env, validate_git_ref
from app.engine.parser.python_parser import (
    ClassInfo,
    FunctionInfo,
    ModuleParseResult,
    PythonASTParser,
    file_path_to_module_name,
)


WORKING_TREE_REFS = {"WORKING", "WORKTREE", "WORKING_TREE", "LOCAL", "INDEX", "STAGED"}

# Git's canonical empty tree object. Comparing against it represents "every
# file is new" and is the correct base for a repository with no commits.
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
EMPTY_TREE_REFS = {"EMPTY", "EMPTY_TREE", "ROOT", "NONE", "ZERO"}

# Refs users commonly use to mean "the previous commit". When a repository has
# fewer than two commits these cannot resolve, so the detector falls back to a
# documented comparison instead of failing with "Unknown Git revision".
PREVIOUS_COMMIT_REFS = {"HEAD~1", "HEAD^", "HEAD^1", "HEAD~01"}
DEFAULT_BASE_REF = "HEAD~1"

# Diff status letters
STATUS_NAMES = {
    "A": "added",
    "M": "modified",
    "D": "deleted",
    "R": "renamed",
    "C": "copied",
    "T": "modified",
    "U": "modified",
}


class GitDetectionError(ValueError):
    """Raised when a repository or revision cannot be inspected."""


@dataclass
class GitCommitInfo:
    sha: str
    short_sha: str
    author: str
    committed_at: str
    subject: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "sha": self.sha,
            "short_sha": self.short_sha,
            "author": self.author,
            "committed_at": self.committed_at,
            "subject": self.subject,
        }


@dataclass
class GitRepositoryInfo:
    """Repository state used to explain and default Git comparisons."""

    repo_path: str
    is_repository: bool
    commit_count: int = 0
    current_branch: str = ""
    commits: list[GitCommitInfo] = field(default_factory=list)
    branches: list[str] = field(default_factory=list)
    root_commit: str = ""
    head_commit: str = ""
    dirty: bool = False
    staged_files: int = 0
    unstaged_files: int = 0
    untracked_files: int = 0
    recommended_base: str = "HEAD~1"
    recommended_head: str = "WORKING"
    warnings: list[str] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo_path": self.repo_path,
            "is_repository": self.is_repository,
            "commit_count": self.commit_count,
            "current_branch": self.current_branch,
            "commits": [c.to_dict() for c in self.commits],
            "branches": self.branches,
            "root_commit": self.root_commit,
            "head_commit": self.head_commit,
            "dirty": self.dirty,
            "staged_files": self.staged_files,
            "unstaged_files": self.unstaged_files,
            "untracked_files": self.untracked_files,
            "recommended_base": self.recommended_base,
            "recommended_head": self.recommended_head,
            "warnings": self.warnings,
            "error": self.error,
        }


@dataclass
class DiffHunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    header: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "old_start": self.old_start,
            "old_count": self.old_count,
            "new_start": self.new_start,
            "new_count": self.new_count,
            "header": self.header,
        }


@dataclass
class FileChange:
    path: str
    old_path: str | None
    change_type: str
    hunks: list[DiffHunk] = field(default_factory=list)
    added_lines: set[int] = field(default_factory=set)
    deleted_lines: set[int] = field(default_factory=set)
    old_content: str | None = None
    new_content: str | None = None
    parse_errors: list[str] = field(default_factory=list)

    @property
    def added_line_count(self) -> int:
        return len(self.added_lines)

    @property
    def deleted_line_count(self) -> int:
        return len(self.deleted_lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "old_path": self.old_path,
            "change_type": self.change_type,
            "hunks": [h.to_dict() for h in self.hunks],
            "added_line_count": self.added_line_count,
            "deleted_line_count": self.deleted_line_count,
            "parse_errors": self.parse_errors,
        }


@dataclass
class ChangedEntity:
    key: str
    kind: str  # function | class | method
    name: str
    qualified_name: str
    file_path: str
    line_start: int
    line_end: int
    change_type: str  # added | modified | deleted

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "kind": self.kind,
            "name": self.name,
            "qualified_name": self.qualified_name,
            "file_path": self.file_path,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "change_type": self.change_type,
        }


@dataclass
class ChangeSet:
    repo_path: str
    base_ref: str
    head_ref: str
    is_working_tree: bool
    base_commit: str = ""
    head_commit: str = ""
    files: list[FileChange] = field(default_factory=list)
    entities: list[ChangedEntity] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def summary(self) -> dict[str, int]:
        types: dict[str, int] = {}
        for file in self.files:
            types[file.change_type] = types.get(file.change_type, 0) + 1
        return {
            "files": len(self.files),
            "entities": len(self.entities),
            "added_files": types.get("added", 0),
            "modified_files": types.get("modified", 0),
            "deleted_files": types.get("deleted", 0),
            "renamed_files": types.get("renamed", 0),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo_path": self.repo_path,
            "base_ref": self.base_ref,
            "head_ref": self.head_ref,
            "is_working_tree": self.is_working_tree,
            "base_commit": self.base_commit,
            "head_commit": self.head_commit,
            "summary": self.summary,
            "files": [f.to_dict() for f in self.files],
            "entities": [e.to_dict() for e in self.entities],
            "warnings": self.warnings,
        }


class GitChangeDetector:
    """Inspect repository changes between a base ref and a target ref."""

    def __init__(self, repo_path: str | Path):
        self.repo_path = Path(repo_path).resolve()
        self.parser = PythonASTParser()
        self._validated = False

    # ── git plumbing ────────────────────────────────────────────

    def _git(self, *args: str, check: bool = True) -> bytes:
        command = [
            "git",
            "-C",
            str(self.repo_path),
            "-c",
            "core.quotePath=false",
            "-c",
            "color.ui=false",
            *args,
        ]
        env = safe_subprocess_env(self.repo_path)
        env["GIT_TERMINAL_PROMPT"] = "0"
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                timeout=60,
                check=False,
                env=env,
            )
        except FileNotFoundError as exc:
            raise GitDetectionError("Git is not installed or not on PATH") from exc
        except subprocess.TimeoutExpired as exc:
            raise GitDetectionError("Git command timed out") from exc
        if check and result.returncode != 0:
            message = result.stderr.decode("utf-8", errors="replace").strip()
            raise GitDetectionError(message or "Git command failed")
        return result.stdout

    def _ensure_repository(self) -> None:
        if self._validated:
            return
        if not self.repo_path.exists() or not self.repo_path.is_dir():
            raise GitDetectionError(f"Repository path does not exist: {self.repo_path}")
        try:
            top = self._git("rev-parse", "--show-toplevel").decode().strip()
        except GitDetectionError as exc:
            raise GitDetectionError(
                f"Not a Git repository: {self.repo_path}. "
                "Change detection requires a Git working tree."
            ) from exc
        if Path(top).resolve() != self.repo_path:
            raise GitDetectionError(
                f"Path must be the repository root. Git root is: {top}"
            )
        self._validated = True

    def _resolve_commit(self, ref: str) -> str:
        validate_git_ref(ref)
        output = self._git("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", check=False)
        commit = output.decode().strip()
        if not commit:
            raise GitDetectionError(
                f"Unknown Git revision: {ref}. The ref may not exist in this "
                "repository or may have been deleted."
            )
        return commit

    def info(self) -> GitRepositoryInfo:
        """Return commit/branch/working-tree state without mutating anything."""
        info = GitRepositoryInfo(repo_path=str(self.repo_path), is_repository=False)
        try:
            self._ensure_repository()
        except GitDetectionError as exc:
            info.error = str(exc)
            return info
        info.is_repository = True

        count_text = self._git("rev-list", "--count", "--all", check=False).decode().strip()
        try:
            info.commit_count = int(count_text or "0")
        except ValueError:
            info.commit_count = 0

        branch = self._git("symbolic-ref", "--short", "-q", "HEAD", check=False)
        info.current_branch = branch.decode().strip() or "detached HEAD"

        log_output = self._git(
            "log", "--all", "-n", "25", "--format=%H%x00%h%x00%an%x00%aI%x00%s", check=False
        ).decode("utf-8", errors="replace")
        for line in log_output.splitlines():
            parts = line.split("\0")
            if len(parts) != 5:
                continue
            info.commits.append(
                GitCommitInfo(
                    sha=parts[0],
                    short_sha=parts[1],
                    author=parts[2],
                    committed_at=parts[3],
                    subject=parts[4],
                )
            )
        if info.commits:
            info.head_commit = info.commits[0].sha

        branch_output = self._git(
            "for-each-ref", "--format=%(refname:short)", "refs/heads", "refs/remotes", check=False
        ).decode("utf-8", errors="replace")
        info.branches = sorted(
            {
                name.strip()
                for name in branch_output.splitlines()
                if name.strip() and not name.strip().endswith("/HEAD")
            }
        )

        root = self._git("rev-list", "--max-parents=0", "HEAD", check=False).decode().strip()
        if root:
            info.root_commit = root.splitlines()[0]

        status = self._git("status", "--porcelain=v1", "-z", check=False).decode(
            "utf-8", errors="replace"
        )
        entries = [entry for entry in status.split("\0") if entry]
        for entry in entries:
            code = entry[:2]
            if code == "??":
                info.untracked_files += 1
            elif code[0] not in (" ", "?"):
                info.staged_files += 1
            else:
                info.unstaged_files += 1
        info.dirty = bool(entries)

        if info.commit_count == 0:
            info.recommended_base = "EMPTY"
            info.recommended_head = "WORKING"
            info.warnings.append(
                "This repository has no commits. Scan and analysis can still run "
                "by comparing the empty tree with the working tree."
            )
        elif info.commit_count == 1:
            info.recommended_base = "HEAD"
            info.recommended_head = "WORKING"
            info.warnings.append(
                "This repository has only one commit. Compare HEAD with the "
                "working tree; HEAD~1 does not exist."
            )
        else:
            info.recommended_base = "HEAD~1"
            info.recommended_head = "WORKING"
        return info

    # ── public API ──────────────────────────────────────────────

    def detect(self, base_ref: str = DEFAULT_BASE_REF, head_ref: str = "WORKING") -> ChangeSet:
        """Detect changed files and Python entities.

        Args:
            base_ref: Revision to compare from. ``EMPTY`` compares against the
                empty tree (all files appear added).
            head_ref: Revision to compare to, or ``WORKING`` for the working tree.

        The default ``HEAD~1`` is resolved defensively: a repository with one
        commit compares ``HEAD`` to the target, and a repository with no commits
        compares the empty tree to the working tree. Both fallbacks are recorded
        as explicit warnings so the comparison is never silently changed.
        """
        self._ensure_repository()
        head_is_working = head_ref.upper() in WORKING_TREE_REFS
        if head_is_working:
            # Normalise aliases such as WORKTREE/INDEX to a single label.
            head_ref = "WORKING"
        else:
            validate_git_ref(head_ref)

        warnings: list[str] = []
        base_is_empty = base_ref.upper() in EMPTY_TREE_REFS
        if base_is_empty:
            base_ref = "EMPTY"
            base_commit = EMPTY_TREE
            warnings.append(
                "Comparing against the empty tree: every tracked file appears added."
            )
        else:
            validate_git_ref(base_ref)
            try:
                base_commit = self._resolve_commit(base_ref)
            except GitDetectionError:
                info = self.info()
                if info.commit_count == 0:
                    base_ref = "EMPTY"
                    base_commit = EMPTY_TREE
                    warnings.append(
                        "Repository has no commits yet; comparing the empty tree "
                        "with the working tree."
                    )
                elif info.commit_count == 1 and base_ref in PREVIOUS_COMMIT_REFS:
                    base_ref = "HEAD"
                    base_commit = self._resolve_commit("HEAD")
                    warnings.append(
                        "Repository has only one commit, so HEAD~1 does not exist. "
                        "Comparing the latest commit (HEAD) with the target instead."
                    )
                else:
                    raise

        if head_is_working:
            head_commit = ""
        else:
            if base_ref == "EMPTY" and self.info().commit_count == 0:
                raise GitDetectionError(
                    "This Git repository has no commits, so a commit-to-commit "
                    "comparison is not possible. Use head_ref=WORKING."
                )
            head_commit = self._resolve_commit(head_ref)

        changeset = ChangeSet(
            repo_path=str(self.repo_path),
            base_ref=base_ref,
            head_ref=head_ref,
            is_working_tree=head_is_working,
            base_commit="" if base_commit == EMPTY_TREE else base_commit,
            head_commit=head_commit,
            warnings=warnings,
        )

        statuses = self._name_status(base_commit, head_commit, head_is_working)
        hunks_by_path = self._parse_diff(base_commit, head_commit, head_is_working)

        handled: set[str] = set()
        for status, old_path, new_path in statuses:
            change_type = STATUS_NAMES.get(status[0], "modified")
            if status[0] in ("R", "C"):
                change_type = "renamed" if status[0] == "R" else "modified"
            target_path = new_path if status[0] != "D" else old_path
            if not target_path or not target_path.endswith(".py"):
                continue
            handled.add(target_path)
            change = FileChange(
                path=target_path,
                old_path=old_path if old_path != target_path else None,
                change_type=change_type,
            )
            patch_key = new_path if new_path in hunks_by_path else old_path
            change.hunks = hunks_by_path.get(patch_key or "", [])
            for hunk in change.hunks:
                if hunk.new_count:
                    change.added_lines.update(
                        range(hunk.new_start, hunk.new_start + hunk.new_count)
                    )
                if hunk.old_count:
                    change.deleted_lines.update(
                        range(hunk.old_start, hunk.old_start + hunk.old_count)
                    )

            if head_is_working and change_type in ("added", "modified", "renamed"):
                change.new_content = self._read_working_file(target_path, changeset)
            elif change_type not in ("deleted",) and head_commit:
                change.new_content = self._git_show(head_commit, target_path, changeset)
            if base_commit != EMPTY_TREE and (
                change_type in ("deleted", "modified", "renamed") or change.old_path
            ):
                old_target = change.old_path or target_path
                change.old_content = self._git_show(base_commit, old_target, changeset)

            if change_type == "added" and change.new_content is not None:
                line_count = max(1, len(change.new_content.splitlines()))
                change.added_lines = set(range(1, line_count + 1))
            changeset.files.append(change)

        # Untracked files are not part of `git diff <commit>`.
        if head_is_working:
            for path in self._untracked_files():
                if not path.endswith(".py") or path in handled:
                    continue
                content = self._read_working_file(path, changeset)
                if content is None:
                    continue
                change = FileChange(
                    path=path,
                    old_path=None,
                    change_type="added",
                    new_content=content,
                    added_lines=set(range(1, max(1, len(content.splitlines())) + 1)),
                )
                changeset.files.append(change)
                handled.add(path)

        changeset.entities = self._detect_entities(changeset)
        if not changeset.files:
            changeset.warnings.append("No Python file changes detected for this range.")
        logger.info(
            "Change detection: %d files, %d entities (%s..%s)",
            len(changeset.files),
            len(changeset.entities),
            base_ref,
            head_ref,
        )
        return changeset

    # ── file inspection ─────────────────────────────────────────

    def _name_status(
        self, base_commit: str, head_commit: str, head_is_working: bool
    ) -> list[tuple[str, str, str]]:
        args = ["diff", "--name-status", "-z", "-M", base_commit]
        if head_commit:
            args.append(head_commit)
        output = self._git(*args)
        tokens = [t for t in output.split(b"\0") if t]
        result: list[tuple[str, str, str]] = []
        i = 0
        while i < len(tokens):
            status = tokens[i].decode("utf-8", errors="replace")
            i += 1
            if i >= len(tokens):
                break
            first = tokens[i].decode("utf-8", errors="replace")
            i += 1
            if status.startswith(("R", "C")):
                if i >= len(tokens):
                    break
                second = tokens[i].decode("utf-8", errors="replace")
                i += 1
                result.append((status, first, second))
            else:
                result.append((status, first, first))
        return result

    def _untracked_files(self) -> list[str]:
        output = self._git("ls-files", "--others", "--exclude-standard", "-z")
        return [
            t.decode("utf-8", errors="replace")
            for t in output.split(b"\0")
            if t
        ]

    def _parse_diff(
        self, base_commit: str, head_commit: str, head_is_working: bool
    ) -> dict[str, list[DiffHunk]]:
        args = [
            "diff",
            "--unified=0",
            "--no-color",
            "--no-ext-diff",
            "--src-prefix=a/",
            "--dst-prefix=b/",
            base_commit,
        ]
        if head_commit:
            args.append(head_commit)
        output = self._git(*args).decode("utf-8", errors="replace")
        return parse_unified_diff(output)

    def _git_show(self, commit: str, path: str, changeset: ChangeSet) -> str | None:
        if not self._safe_repo_path(path, changeset):
            return None
        try:
            return self._git("show", f"{commit}:{path}").decode("utf-8", errors="replace")
        except GitDetectionError:
            changeset.warnings.append(f"Could not read {path} at {commit}")
            return None

    def _read_working_file(self, path: str, changeset: ChangeSet) -> str | None:
        if not self._safe_repo_path(path, changeset):
            return None
        absolute = (self.repo_path / path).resolve()
        try:
            return absolute.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            changeset.warnings.append(f"Could not read {path}: {exc}")
            return None

    def _safe_repo_path(self, path: str, changeset: ChangeSet) -> bool:
        if PurePosixPath(path).is_absolute():
            changeset.warnings.append(f"Ignored absolute path from Git: {path}")
            return False
        absolute = (self.repo_path / path).resolve()
        if not is_within(absolute, self.repo_path):
            changeset.warnings.append(f"Ignored path outside repository: {path}")
            return False
        return True

    # ── entity mapping ──────────────────────────────────────────

    def _detect_entities(self, changeset: ChangeSet) -> list[ChangedEntity]:
        changed: dict[str, ChangedEntity] = {}
        for file in changeset.files:
            base_entities = self._entities_for(file.old_path or file.path, file.old_content, changeset)
            head_entities = self._entities_for(file.path, file.new_content, changeset)

            if file.change_type == "added":
                for key, entity in head_entities.items():
                    item = self._to_changed(entity, file.path, "added")
                    changed[item.key] = item
                continue
            if file.change_type == "deleted":
                for key, entity in base_entities.items():
                    item = self._to_changed(entity, file.old_path or file.path, "deleted")
                    changed[item.key] = item
                continue

            for key, entity in head_entities.items():
                if key not in base_entities:
                    changed[key] = self._to_changed(entity, file.path, "added")
                    continue
                if self._entity_intersects(entity, file.added_lines, head_entities):
                    changed[key] = self._to_changed(entity, file.path, "modified")
            for key, entity in base_entities.items():
                if key not in head_entities:
                    changed[key] = self._to_changed(
                        entity, file.old_path or file.path, "deleted"
                    )
                    continue
                if key not in changed and self._entity_intersects(
                    entity, file.deleted_lines, base_entities
                ):
                    changed[key] = self._to_changed(entity, file.path, "modified")

        return sorted(
            changed.values(),
            key=lambda e: (e.file_path, e.line_start, e.kind, e.qualified_name),
        )

    def _entities_for(
        self, path: str, content: str | None, changeset: ChangeSet
    ) -> dict[str, Any]:
        if content is None:
            return {}
        module_name = file_path_to_module_name(path, "")
        parsed: ModuleParseResult = self.parser.parse_source(content, path, module_name)
        changeset.warnings.extend(
            f"{path}: {error}" for error in parsed.parse_errors
        )
        result: dict[str, Any] = {}
        for func in parsed.functions:
            key = f"function:{func.qualified_name}"
            result[key] = ParsedEntity("function", func, path, module_name)
        for cls in parsed.classes:
            key = f"class:{cls.qualified_name}"
            result[key] = ParsedEntity("class", cls, path, module_name)
            for method in cls.methods:
                method_key = f"method:{method.qualified_name}"
                result[method_key] = ParsedEntity("method", method, path, module_name)
                result[method_key].class_info = cls
        return result

    def _entity_intersects(
        self,
        entity: Any,
        line_numbers: set[int],
        siblings: dict[str, Any],
    ) -> bool:
        if not line_numbers:
            return False
        if entity.kind == "class":
            own = set(range(entity.line_start, entity.line_end + 1))
            for other in siblings.values():
                if other.kind == "method" and other.class_info is entity.info:
                    own.difference_update(
                        range(other.line_start, other.line_end + 1)
                    )
            # A changed base/class header line is part of the class itself.
            return bool(own & line_numbers)
        return bool(
            set(range(entity.line_start, entity.line_end + 1)) & line_numbers
        )

    @staticmethod
    def _to_changed(entity: Any, path: str, change_type: str) -> ChangedEntity:
        return ChangedEntity(
            key=entity.key,
            kind=entity.kind,
            name=entity.info.name,
            qualified_name=entity.info.qualified_name,
            file_path=path,
            line_start=entity.line_start,
            line_end=entity.line_end,
            change_type=change_type,
        )


@dataclass
class ParsedEntity:
    """Adapter around parser info used during change matching."""

    kind: str
    info: FunctionInfo | ClassInfo
    file_path: str
    module_name: str
    class_info: ClassInfo | None = None

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.info.qualified_name}"

    @property
    def line_start(self) -> int:
        return self.info.line_start

    @property
    def line_end(self) -> int:
        return self.info.line_end


def parse_unified_diff(text: str) -> dict[str, list[DiffHunk]]:
    """Parse a unified diff into hunks keyed by the new (or old) path."""
    hunks: dict[str, list[DiffHunk]] = {}
    current_path: str | None = None
    old_path: str | None = None
    new_path: str | None = None

    for line in text.splitlines():
        if line.startswith("diff --git "):
            old_path = None
            new_path = None
            current_path = None
        elif line.startswith("--- "):
            raw = line[4:].strip()
            old_path = None if raw == "/dev/null" else raw[2:] if raw.startswith("a/") else raw
        elif line.startswith("+++ "):
            raw = line[4:].strip()
            new_path = None if raw == "/dev/null" else raw[2:] if raw.startswith("b/") else raw
            current_path = new_path or old_path
            if current_path:
                hunks.setdefault(current_path, [])
            if old_path and old_path != current_path:
                hunks.setdefault(old_path, [])
        elif line.startswith("rename from "):
            old_path = line[len("rename from "):]
            if old_path:
                hunks.setdefault(old_path, [])
        elif line.startswith("rename to "):
            new_path = line[len("rename to "):]
            current_path = new_path or old_path
            if current_path:
                hunks.setdefault(current_path, [])
        elif line.startswith("@@ ") and current_path:
            header = line
            try:
                ranges = line.split("@@", 2)[1].strip().split()
                old = ranges[0][1:].split(",")
                new = ranges[1][1:].split(",")
                hunk = DiffHunk(
                    old_start=int(old[0]),
                    old_count=int(old[1]) if len(old) > 1 else 1,
                    new_start=int(new[0]),
                    new_count=int(new[1]) if len(new) > 1 else 1,
                    header=header,
                )
                hunks[current_path].append(hunk)
            except (IndexError, ValueError):
                continue
    return hunks


def is_git_repository(path: str | Path) -> bool:
    try:
        detector = GitChangeDetector(path)
        detector._ensure_repository()
        return True
    except (GitDetectionError, OSError):
        return False


def get_git_info(path: str | Path) -> GitRepositoryInfo:
    """Best-effort repository metadata for the Git status UI and Copilot."""
    try:
        return GitChangeDetector(path).info()
    except (GitDetectionError, OSError) as exc:
        return GitRepositoryInfo(
            repo_path=str(Path(path).resolve()),
            is_repository=False,
            error=str(exc),
        )
