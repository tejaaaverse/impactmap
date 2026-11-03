"""
Path and process safety helpers.

IMPACTMAP is a local developer tool. These helpers do not make it a sandbox;
they only reduce accidental exposure and command-injection risk.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from app.core.config import settings


# Directories that should never be scanned implicitly. A user can opt in with
# ALLOWED_SCAN_ROOTS if they really want to analyse one of these locations.
_FORBIDDEN_ROOTS = {
    Path("/"),
    Path("/etc"),
    Path("/private/etc"),
    Path("/usr"),
    Path("/private/usr"),
    Path("/bin"),
    Path("/private/bin"),
    Path("/sbin"),
    Path("/private/sbin"),
    Path("/proc"),
    Path("/sys"),
    Path("/dev"),
    Path("/System"),
    Path("/Library"),
    Path("/private/Library"),
}

_REF_RE = re.compile(r"^[A-Za-z0-9_@{}^~./:-]+$")


class PathValidationError(ValueError):
    """Raised when a repository path is not safe to analyse."""


def validate_repository_path(raw_path: str | Path) -> Path:
    """Resolve and validate a repository path.

    Checks performed:
    - path exists and is a directory
    - path is not the filesystem root or a system directory
    - optional ALLOWED_SCAN_ROOTS allow-list is respected
    - resolved path is readable

    Symlinks are resolved before the boundary checks so a symlink cannot be
    used to escape an allow-listed root.
    """

    try:
        path = Path(raw_path).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise PathValidationError(f"Repository path is not accessible: {raw_path}") from exc

    if not path.is_dir():
        raise PathValidationError(f"Repository path is not a directory: {path}")

    if path in _FORBIDDEN_ROOTS:
        raise PathValidationError(
            "Refusing to scan a filesystem root or system directory. "
            "Choose a project directory."
        )

    for forbidden in _FORBIDDEN_ROOTS:
        if forbidden == Path("/"):
            continue
        try:
            path.relative_to(forbidden)
        except ValueError:
            continue
        raise PathValidationError(
            f"Refusing to scan a system directory: {forbidden}. "
            "Configure ALLOWED_SCAN_ROOTS to override this check."
        )

    if settings.ALLOWED_SCAN_ROOTS:
        allowed = [Path(p).expanduser().resolve() for p in settings.ALLOWED_SCAN_ROOTS]
        if not any(_is_relative_to(path, root) for root in allowed):
            raise PathValidationError(
                "Repository path is outside the configured ALLOWED_SCAN_ROOTS."
            )

    try:
        next(path.iterdir(), None)
    except PermissionError as exc:
        raise PathValidationError(f"Repository path is not readable: {path}") from exc

    return path


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def is_within(path: Path, root: Path) -> bool:
    """Return True when path resolves to a location inside root."""
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
        return True
    except (ValueError, OSError):
        return False


def validate_git_ref(ref: str) -> str:
    """Reject refs that could be interpreted as command-line options."""
    ref = ref.strip()
    if not ref or ref.startswith("-") or not _REF_RE.match(ref):
        raise ValueError(f"Invalid git ref: {ref!r}")
    return ref


def safe_subprocess_env(repo_path: Path | None = None) -> dict[str, str]:
    """Build a minimal environment for test execution.

    Secret-like variables are deliberately excluded. The resulting environment
    is not a security boundary, but it avoids leaking the parent process's
    credentials to repository test code.
    """
    allowed = {
        "PATH",
        "HOME",
        "TMPDIR",
        "TEMP",
        "TMP",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "SYSTEMROOT",
        "WINDIR",
        "USERPROFILE",
    }
    env = {key: value for key, value in os.environ.items() if key in allowed}
    env.setdefault("PYTHONUNBUFFERED", "1")
    env.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    env.setdefault("MPLBACKEND", "Agg")
    if repo_path is not None:
        env["IMPACTMAP_REPO"] = str(repo_path)
    # Ensure temp files stay outside the scanned tree.
    env.setdefault("TMPDIR", tempfile.gettempdir())
    return env
