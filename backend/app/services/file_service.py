"""Safe, read-only access to files inside an analysed repository.

The Copilot UI uses this to open a cited file. Access is deliberately narrow:
paths must be repository-relative, must resolve inside the repository (including
after symlink resolution), and must be a text/source file below the size limit.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from app.core.config import settings
from app.core.security import is_within, validate_repository_path


TEXT_SUFFIXES = {
    ".py",
    ".pyi",
    ".md",
    ".rst",
    ".txt",
    ".toml",
    ".cfg",
    ".ini",
    ".json",
    ".yaml",
    ".yml",
    ".sql",
    ".sh",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".css",
    ".html",
    ".env",
    ".gitignore",
}


class FileAccessError(ValueError):
    """Raised when a requested file is not safe or readable."""


@dataclass
class FileContent:
    path: str
    absolute_path: str
    content: str
    line_count: int
    size_bytes: int
    truncated: bool
    language: str
    start_line: int | None = None
    end_line: int | None = None

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "content": self.content,
            "line_count": self.line_count,
            "size_bytes": self.size_bytes,
            "truncated": self.truncated,
            "language": self.language,
            "start_line": self.start_line,
            "end_line": self.end_line,
        }


def _language_for(path: Path) -> str:
    suffix = path.suffix.lower()
    return {
        ".py": "python",
        ".pyi": "python",
        ".ts": "typescript",
        ".tsx": "tsx",
        ".js": "javascript",
        ".jsx": "jsx",
        ".json": "json",
        ".md": "markdown",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".toml": "toml",
        ".sh": "bash",
        ".sql": "sql",
        ".html": "html",
        ".css": "css",
    }.get(suffix, "text")


def read_repository_file(
    repo_path: str | Path,
    relative_path: str,
    *,
    start_line: int | None = None,
    end_line: int | None = None,
    max_bytes: int | None = None,
) -> FileContent:
    """Read a text file inside ``repo_path`` with traversal protection."""
    root = validate_repository_path(repo_path)
    raw = (relative_path or "").strip().replace("\\", "/")
    if not raw:
        raise FileAccessError("A file path is required")
    pure = PurePosixPath(raw)
    if pure.is_absolute() or ".." in pure.parts:
        raise FileAccessError("File path must be relative to the repository root")

    candidate = (root / pure).resolve()
    if not is_within(candidate, root):
        raise FileAccessError("File path resolves outside the repository")
    if not candidate.exists():
        raise FileAccessError(f"File not found: {raw}")
    if not candidate.is_file():
        raise FileAccessError(f"Not a file: {raw}")

    limit = max_bytes or settings.COPILOT_MAX_FILE_BYTES
    size = candidate.stat().st_size
    if size > limit:
        raise FileAccessError(
            f"File is too large to display ({size} bytes, limit {limit})"
        )

    suffix = candidate.suffix.lower()
    if suffix and suffix not in TEXT_SUFFIXES and candidate.name not in {
        ".gitignore",
        ".env.example",
    }:
        raise FileAccessError(f"Unsupported file type for the viewer: {suffix}")

    try:
        raw_bytes = candidate.read_bytes()
    except OSError as exc:
        raise FileAccessError(f"Could not read {raw}: {exc}") from exc
    if b"\x00" in raw_bytes[:4096]:
        raise FileAccessError("Binary files cannot be displayed")

    content = raw_bytes.decode("utf-8", errors="replace")
    lines = content.splitlines()
    line_count = len(lines)

    selected = content
    if start_line is not None or end_line is not None:
        start = max(1, int(start_line or 1))
        end = int(end_line or line_count)
        if end < start:
            raise FileAccessError("end_line must be greater than or equal to start_line")
        end = min(end, max(line_count, 1))
        selected = "\n".join(lines[start - 1 : end])
        return FileContent(
            path=pure.as_posix(),
            absolute_path=str(candidate),
            content=selected,
            line_count=line_count,
            size_bytes=size,
            truncated=start > 1 or end < line_count,
            language=_language_for(candidate),
            start_line=start,
            end_line=end,
        )

    return FileContent(
        path=pure.as_posix(),
        absolute_path=str(candidate),
        content=selected,
        line_count=line_count,
        size_bytes=size,
        truncated=False,
        language=_language_for(candidate),
    )
