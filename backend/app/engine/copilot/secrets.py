"""Redaction helpers for untrusted repository content.

Repository code is data, not instruction. The Copilot also refuses to send
obvious credential material to an external model. Redaction is best-effort: it
reduces accidental disclosure but is not a substitute for keeping secrets out of
source control.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

REDACTED = "«redacted»"

_SKIP_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    ".netrc",
    ".pypirc",
    "credentials",
    "credentials.json",
    "secrets.yaml",
    "secrets.yml",
}

_SKIP_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".keystore", ".jks"}

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
        "«redacted private key»",
    ),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "«redacted aws key»"),
    (re.compile(r"\bASIA[0-9A-Z]{16}\b"), "«redacted aws key»"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"), "«redacted github token»"),
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"), "«redacted slack token»"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"), "«redacted api key»"),
    (re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{16,}=*"), "Bearer «redacted»"),
    (
        re.compile(
            r"(?i)\b(api[_-]?key|api[_-]?secret|access[_-]?token|auth[_-]?token|"
            r"client[_-]?secret|password|passwd|secret)\b(\s*[:=]\s*)(['\"])([^'\"\n]{4,})\3"
        ),
        r"\1\2\3«redacted»\3",
    ),
    (
        re.compile(
            r"(?i)\b(api[_-]?key|api[_-]?secret|access[_-]?token|client[_-]?secret|"
            r"password|passwd|secret)\b(\s*[:=]\s*)([A-Za-z0-9_./+=-]{8,})"
        ),
        r"\1\2«redacted»",
    ),
]


def should_skip_file(path: str) -> bool:
    """Return True for files that should never be read into model context."""
    pure = PurePosixPath(path.replace("\\", "/"))
    name = pure.name.lower()
    if name in _SKIP_NAMES or name.startswith(".env."):
        return True
    if pure.suffix.lower() in _SKIP_SUFFIXES:
        return True
    if any(part.lower() in {".ssh", ".gnupg"} for part in pure.parts):
        return True
    return False


def redact_secrets(text: str) -> str:
    """Mask high-confidence secret patterns while preserving surrounding code."""
    if not text:
        return text
    redacted = text
    for pattern, replacement in _PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def contains_secret(text: str) -> bool:
    return redact_secrets(text) != text
