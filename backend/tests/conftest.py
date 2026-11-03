"""Shared fixtures for engine and API tests."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

SAMPLE_REPO = Path(__file__).resolve().parents[2] / "sample_repositories" / "calculator"


def git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def init_git_repo(repo: Path) -> Path:
    assert git(repo, "init", "-q").returncode == 0
    git(repo, "config", "user.email", "impactmap-tests@example.com")
    git(repo, "config", "user.name", "IMPACTMAP Tests")
    git(repo, "config", "commit.gpgsign", "false")
    assert git(repo, "add", "-A").returncode == 0
    assert git(repo, "commit", "-qm", "base").returncode == 0
    return repo


def commit_all(repo: Path, message: str) -> None:
    assert git(repo, "add", "-A").returncode == 0
    assert git(repo, "commit", "-qm", message).returncode == 0


@pytest.fixture(autouse=True)
def isolate_copilot_llm(monkeypatch):
    """Never call a real model provider from the test suite.

    Tests that need a provider replace the client with a fake explicitly.
    """
    from app.api import copilot as copilot_api
    from app.engine.copilot.llm import LLMClient

    monkeypatch.setattr(
        copilot_api._service,
        "llm",
        LLMClient(provider="none", api_key="", base_url="", model=""),
    )


@pytest.fixture
def sample_repo_copy(tmp_path: Path) -> Path:
    """A writable copy of the bundled calculator sample."""
    destination = tmp_path / "calculator"
    shutil.copytree(
        SAMPLE_REPO,
        destination,
        ignore=shutil.ignore_patterns("__pycache__", ".git", ".venv", ".coverage"),
    )
    return destination


@pytest.fixture
def git_repo(sample_repo_copy: Path) -> Path:
    """Sample repository with one baseline commit."""
    return init_git_repo(sample_repo_copy)
