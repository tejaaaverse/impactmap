"""
File Discovery Module.

Recursively discovers Python files in a repository while respecting
ignore patterns (venvs, __pycache__, .git, build dirs, etc.).
"""

import fnmatch
from pathlib import Path
from dataclasses import dataclass, field

from app.core.config import settings
from app.core.logging import logger


@dataclass
class DiscoveredFile:
    """Represents a discovered Python source file."""

    absolute_path: Path
    relative_path: str  # Relative to repository root
    size_bytes: int
    line_count: int = 0


@dataclass
class DiscoveryResult:
    """Result of a file discovery scan."""

    files: list[DiscoveredFile] = field(default_factory=list)
    skipped_dirs: list[str] = field(default_factory=list)
    files_skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    total_size_bytes: int = 0
    directories_explored: int = 0


class FileDiscovery:
    """
    Recursively discovers Python files in a repository.

    Respects configurable ignore patterns to skip virtual environments,
    cache directories, build artifacts, and version control directories.
    """

    def __init__(self, ignore_patterns: list[str] | None = None):
        self.ignore_patterns = ignore_patterns or settings.IGNORE_DIRS
        self.extensions = settings.PYTHON_EXTENSIONS

    def should_ignore_dir(self, dir_name: str, dir_path: Path) -> bool:
        """Check if a directory should be skipped during traversal."""
        for pattern in self.ignore_patterns:
            if fnmatch.fnmatch(dir_name, pattern):
                return True
        # Also skip hidden directories (starting with .)
        if dir_name.startswith(".") and dir_name not in (".",):
            return True
        return False

    def is_python_file(self, file_path: Path) -> bool:
        """Check if a file is a Python source file."""
        return file_path.suffix in self.extensions

    def count_lines(self, file_path: Path) -> int:
        """Count lines in a file, handling encoding errors gracefully."""
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                return sum(1 for _ in f)
        except (OSError, IOError) as e:
            logger.warning(f"Could not count lines in {file_path}: {e}")
            return 0

    def discover(self, repo_path: Path) -> DiscoveryResult:
        """
        Discover all Python files in the given repository path.

        Args:
            repo_path: Absolute path to the repository root.

        Returns:
            DiscoveryResult containing discovered files and metadata.

        Raises:
            ValueError: If the path is invalid or inaccessible.
        """
        repo_path = Path(repo_path).resolve()

        if not repo_path.exists():
            raise ValueError(f"Repository path does not exist: {repo_path}")
        if not repo_path.is_dir():
            raise ValueError(f"Repository path is not a directory: {repo_path}")

        result = DiscoveryResult()
        self._visited: set[tuple[int, int]] = set()
        logger.info(f"Starting file discovery in: {repo_path}")

        self._walk_directory(repo_path, repo_path, result)

        result.total_size_bytes = sum(f.size_bytes for f in result.files)
        logger.info(
            f"Discovery complete: {len(result.files)} Python files found, "
            f"{result.directories_explored} directories explored, "
            f"{len(result.skipped_dirs)} directories skipped, "
            f"{len(result.files_skipped)} files skipped, "
            f"{len(result.errors)} errors"
        )

        return result

    def _walk_directory(
        self, current_path: Path, repo_root: Path, result: DiscoveryResult
    ) -> None:
        """Recursively walk a directory tree discovering Python files.

        Symbolic links are not followed: this avoids cycles and prevents a
        repository from pulling files from outside its own tree into analysis.
        """
        try:
            stat = current_path.stat(follow_symlinks=False)
            identity = (stat.st_dev, stat.st_ino)
            if identity in self._visited:
                result.errors.append(f"Skipped directory loop: {current_path}")
                return
            self._visited.add(identity)
        except OSError as exc:
            result.errors.append(f"Cannot stat directory {current_path}: {exc}")
            return

        try:
            entries = sorted(current_path.iterdir())
        except PermissionError:
            error_msg = f"Permission denied: {current_path}"
            logger.warning(error_msg)
            result.errors.append(error_msg)
            return

        result.directories_explored += 1

        dirs = []
        files = []

        for entry in entries:
            try:
                if entry.is_symlink():
                    result.errors.append(
                        f"Skipped symbolic link: {entry.relative_to(repo_root)}"
                    )
                    if entry.suffix in self.extensions:
                        result.files_skipped.append(
                            str(entry.relative_to(repo_root))
                        )
                    continue
                if entry.is_dir():
                    dirs.append(entry)
                elif entry.is_file():
                    files.append(entry)
            except OSError as exc:
                result.errors.append(f"Cannot inspect {entry}: {exc}")

        # Process files
        for file_path in files:
            if self.is_python_file(file_path):
                try:
                    size = file_path.stat().st_size
                    if size > settings.MAX_FILE_SIZE_BYTES:
                        relative = str(file_path.relative_to(repo_root))
                        result.files_skipped.append(relative)
                        result.errors.append(
                            f"Skipped oversized Python file "
                            f"({size} bytes): {relative}"
                        )
                        continue
                    relative = str(file_path.relative_to(repo_root))
                    line_count = self.count_lines(file_path)

                    discovered = DiscoveredFile(
                        absolute_path=file_path,
                        relative_path=relative,
                        size_bytes=size,
                        line_count=line_count,
                    )
                    result.files.append(discovered)
                except Exception as e:
                    error_msg = f"Error processing {file_path}: {e}"
                    logger.warning(error_msg)
                    result.errors.append(error_msg)
                    try:
                        result.files_skipped.append(
                            str(file_path.relative_to(repo_root))
                        )
                    except ValueError:
                        result.files_skipped.append(str(file_path))

        # Recurse into subdirectories
        for dir_path in dirs:
            if self.should_ignore_dir(dir_path.name, dir_path):
                result.skipped_dirs.append(str(dir_path.relative_to(repo_root)))
                logger.debug(f"Skipping directory: {dir_path.name}")
                continue
            self._walk_directory(dir_path, repo_root, result)
