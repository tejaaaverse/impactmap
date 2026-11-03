"""
Application configuration using Pydantic settings.
Centralizes all configuration values with environment variable support.
"""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    APP_NAME: str = "IMPACTMAP"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = True

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./impactmap.db"

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Analysis
    MAX_REPO_SIZE_MB: int = 500
    MAX_FILE_SIZE_BYTES: int = 2_000_000
    SCAN_TIMEOUT_SECONDS: int = 300
    TEST_EXECUTION_TIMEOUT_SECONDS: int = 600
    ANALYSIS_MAX_DEPTH: int = 8
    ANALYSIS_MAX_NODES: int = 2500

    # Execution safety
    ALLOWED_SCAN_ROOTS: list[str] = []
    MAX_TEST_OUTPUT_BYTES: int = 200_000
    COVERAGE_CONTEXT_PLUGIN: bool = True

    # CORS
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    # Directories to always ignore during scanning
    IGNORE_DIRS: list[str] = [
        ".git",
        ".hg",
        ".svn",
        "__pycache__",
        ".venv",
        "venv",
        "env",
        ".env",
        "site-packages",
        "dist-packages",
        "node_modules",
        ".tox",
        ".nox",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        ".cache",
        "build",
        "dist",
        ".eggs",
        "*.egg-info",
        ".idea",
        ".vscode",
    ]

    # File patterns to scan
    PYTHON_EXTENSIONS: list[str] = [".py"]

    # Copilot / LLM (OpenAI-compatible chat completions API).
    # Keys are read from the environment (or backend/.env); never from the UI
    # or database, and never echoed back by the API.
    LLM_PROVIDER: str = "openai-compatible"
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.openai.com/v1"
    LLM_MODEL: str = "gpt-4o-mini"
    LLM_TIMEOUT_SECONDS: int = 60
    LLM_MAX_OUTPUT_TOKENS: int = 1200
    LLM_MAX_CONTEXT_CHARS: int = 24_000
    COPILOT_RETRIEVAL_TOP_K: int = 6
    COPILOT_MAX_FILE_BYTES: int = 600_000
    COPILOT_MAX_HISTORY_MESSAGES: int = 12

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
