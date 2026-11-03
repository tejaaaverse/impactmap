"""Isolated pytest execution with timeouts and output parsing."""

from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from app.core.config import settings
from app.core.logging import logger
from app.core.security import is_within, safe_subprocess_env

RESULT_STATUSES = ("PASSED", "FAILED", "ERROR", "SKIPPED", "XFAIL", "XPASS")
_RESULT_RE = re.compile(
    r"^(?P<test_id>.+?::.+?)\s+(?P<status>" + "|".join(RESULT_STATUSES) + r")(?:\s|$)"
)
_SUMMARY_RE = re.compile(r"(?P<count>\d+)\s+(?P<kind>passed|failed|error|errors|skipped|xfailed|xpassed)")


@dataclass
class TestExecutionResult:
    status: str  # completed | timeout | error | no_tests
    exit_code: int | None = None
    test_ids: list[str] = field(default_factory=list)
    total_tests: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    duration_ms: float = 0.0
    timed_out: bool = False
    results: list[dict[str, Any]] = field(default_factory=list)
    stdout_tail: str = ""
    stderr_tail: str = ""
    warnings: list[str] = field(default_factory=list)
    command: list[str] = field(default_factory=list)

    @property
    def failed_ids(self) -> list[str]:
        return [
            r["test_id"]
            for r in self.results
            if r["status"] in ("FAILED", "ERROR")
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "exit_code": self.exit_code,
            "test_ids": self.test_ids,
            "total_tests": self.total_tests,
            "passed": self.passed,
            "failed": self.failed,
            "errors": self.errors,
            "skipped": self.skipped,
            "duration_ms": round(self.duration_ms, 1),
            "timed_out": self.timed_out,
            "results": self.results,
            "stdout_tail": self.stdout_tail,
            "stderr_tail": self.stderr_tail,
            "warnings": self.warnings,
            "command": _redact_command(self.command),
        }


class TestExecutor:
    """Not a pytest test class; disables accidental collection."""

    __test__ = False

    """Run pytest in a subprocess. Never uses a shell, always has a timeout."""

    def __init__(
        self,
        repo_path: str | Path,
        python_executable: str | None = None,
        timeout_seconds: int | None = None,
    ):
        self.repo_path = Path(repo_path).resolve()
        self.python = python_executable or self._choose_python()
        self.timeout_seconds = timeout_seconds or settings.TEST_EXECUTION_TIMEOUT_SECONDS

    def _choose_python(self) -> str:
        for candidate in (
            self.repo_path / ".venv" / "bin" / "python",
            self.repo_path / "venv" / "bin" / "python",
        ):
            if candidate.exists() and os.access(candidate, os.X_OK):
                return str(candidate)
        return sys.executable

    def validate_test_ids(self, test_ids: list[str]) -> list[str]:
        cleaned: list[str] = []
        for test_id in test_ids:
            if not isinstance(test_id, str):
                raise ValueError("Test IDs must be strings")
            test_id = test_id.strip()
            if not test_id or test_id.startswith("-") or "\x00" in test_id or "\n" in test_id:
                raise ValueError(f"Invalid test ID: {test_id!r}")
            if len(test_id) > 1000:
                raise ValueError("Test ID is too long")
            file_part = test_id.split("::", 1)[0]
            path = PurePosixPath(file_part.replace("\\", "/"))
            if path.is_absolute() or ".." in path.parts:
                raise ValueError(f"Test ID points outside the repository: {test_id!r}")
            resolved = (self.repo_path / file_part).resolve()
            if not is_within(resolved, self.repo_path):
                raise ValueError(f"Test ID points outside the repository: {test_id!r}")
            cleaned.append(test_id)
        return cleaned

    def run(
        self,
        test_ids: list[str] | None = None,
        *,
        coverage_data_file: Path | None = None,
        context_plugin_dir: Path | None = None,
        timeout_seconds: int | None = None,
    ) -> TestExecutionResult:
        """Execute tests.

        Args:
            test_ids: ``None`` means the complete pytest suite. An empty list
                means no tests should be run.
            coverage_data_file: When provided, wrap pytest in ``coverage run``.
            context_plugin_dir: Directory containing the context plugin module.
        """
        if test_ids is not None:
            test_ids = self.validate_test_ids(test_ids)
            if not test_ids:
                return TestExecutionResult(
                    status="no_tests",
                    test_ids=[],
                    warnings=["No tests selected; nothing was executed."],
                )

        command = [self.python]
        env = safe_subprocess_env(self.repo_path)
        if coverage_data_file is not None:
            command.extend(
                [
                    "-m",
                    "coverage",
                    "run",
                    "--branch",
                    f"--data-file={coverage_data_file}",
                    f"--source={self.repo_path}",
                    "-m",
                    "pytest",
                ]
            )
        else:
            command.extend(["-m", "pytest"])

        command.extend(
            [
                "-v",
                "--tb=short",
                "--color=no",
                "-p",
                "no:cacheprovider",
            ]
        )
        if context_plugin_dir is not None:
            command.extend(["-p", "impactmap_coverage_plugin"])
            env["PYTHONPATH"] = str(context_plugin_dir)
        if test_ids:
            command.extend(test_ids)

        timeout = timeout_seconds or self.timeout_seconds
        start = time.monotonic()
        try:
            process = subprocess.Popen(
                command,
                cwd=str(self.repo_path),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                errors="replace",
                env=env,
                start_new_session=True,
            )
            try:
                stdout, stderr = process.communicate(timeout=timeout)
                timed_out = False
            except subprocess.TimeoutExpired:
                timed_out = True
                _terminate_process_group(process)
                stdout, stderr = process.communicate()
        except OSError as exc:
            logger.error(f"Could not execute tests in {self.repo_path}: {exc}")
            return TestExecutionResult(
                status="error",
                test_ids=test_ids or [],
                duration_ms=(time.monotonic() - start) * 1000,
                stderr_tail=str(exc),
                warnings=[f"Failed to start test process: {exc}"],
                command=command,
            )

        duration_ms = (time.monotonic() - start) * 1000
        results, counts = _parse_pytest_output(stdout)
        exit_code = process.returncode

        status = "timeout" if timed_out else "completed"
        warnings: list[str] = []
        if timed_out:
            warnings.append(
                f"Test execution exceeded the {timeout}s timeout and was terminated."
            )
        if coverage_data_file is not None and not coverage_data_file.exists():
            warnings.append("Coverage data file was not produced.")

        total = len(results)
        if total and not any(counts.values()):
            counts = _count_results(results)
        if not total:
            total = sum(counts.values())
            results = [
                {
                    "test_id": test_id,
                    "status": "UNKNOWN",
                    "duration_ms": None,
                }
                for test_id in (test_ids or [])
            ]

        return TestExecutionResult(
            status=status,
            exit_code=exit_code,
            test_ids=test_ids or [],
            total_tests=total,
            passed=counts.get("passed", 0),
            failed=counts.get("failed", 0),
            errors=counts.get("error", 0) + counts.get("errors", 0),
            skipped=counts.get("skipped", 0),
            duration_ms=duration_ms,
            timed_out=timed_out,
            results=results,
            stdout_tail=_tail(stdout),
            stderr_tail=_tail(stderr),
            warnings=warnings,
            command=command,
        )


def _terminate_process_group(process: subprocess.Popen) -> None:
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            process.terminate()
        except OSError:
            return
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            process.kill()


def _parse_pytest_output(stdout: str) -> tuple[list[dict[str, Any]], dict[str, int]]:
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line in stdout.splitlines():
        match = _RESULT_RE.match(line.strip())
        if not match:
            continue
        test_id = match.group("test_id").strip()
        if test_id in seen:
            continue
        seen.add(test_id)
        results.append(
            {
                "test_id": test_id,
                "status": match.group("status"),
                "duration_ms": None,
            }
        )

    counts: dict[str, int] = {}
    for line in stdout.splitlines():
        if not line.lstrip().startswith("=") and " passed" not in line and " failed" not in line:
            continue
        for match in _SUMMARY_RE.finditer(line):
            kind = match.group("kind")
            counts[kind] = counts.get(kind, 0) + int(match.group("count"))
    return results, counts


def _count_results(results: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for result in results:
        key = result["status"].lower()
        counts[key] = counts.get(key, 0) + 1
    return counts


def _tail(text: str) -> str:
    limit = settings.MAX_TEST_OUTPUT_BYTES
    if len(text) <= limit:
        return text
    return "...[output truncated]...\n" + text[-limit:]


def _redact_command(command: list[str]) -> list[str]:
    # No secrets are passed through argv today; this hook keeps the response
    # shape stable if that changes.
    return [part if "TOKEN" not in part.upper() else "<redacted>" for part in command]
