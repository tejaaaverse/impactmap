"""Deterministic intent detection and query entity extraction.

The LLM receives an explicit intent and retrieved evidence, so the model is not
asked to decide what kind of repository data to look at. This keeps retrieval
predictable and testable when no model key is configured.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_FILE_RE = re.compile(r"[\w./\\-]+\.py\b")
_SYMBOL_RE = re.compile(r"`([A-Za-z_][\w.]*)`")
_CALL_RE = re.compile(r"\b([A-Za-z_][\w.]*)\(\)")
_TRACEBACK_RE = re.compile(
    r'(?:Traceback \(most recent call last\)|File\s+"([^"]+)",\s+line\s+(\d+))',
    re.IGNORECASE,
)
# Accept both "engine.py line 6" and "engine.py:6" outside a full traceback.
_FILE_LINE_RE = re.compile(
    r"([A-Za-z0-9_./\\-]+\.py)(?::(\d+)|[\s,]+(?:on\s+)?line\s+(\d+))",
    re.IGNORECASE,
)
_IMPACT_CHANGE_RE = re.compile(
    r"\b(?:if|when)\s+(?:i|we|you)\s+(?:change|modify|edit|remove|delete|refactor)\s+"
    r"(?:the\s+)?([A-Za-z_]\w*)",
    re.IGNORECASE,
)
_SYMBOL_NOUN_RE = re.compile(
    r"\b(?:the\s+)?([A-Za-z_]\w*)\s+(?:function|method|class)\b",
    re.IGNORECASE,
)
_SYMBOL_STOPWORDS = {
    "a", "an", "the", "this", "that", "these", "those", "my", "our", "your",
    "function", "method", "class", "code", "file", "module",
}


@dataclass
class Intent:
    name: str
    query: str
    file_paths: list[str] = field(default_factory=list)
    symbols: list[str] = field(default_factory=list)
    is_traceback: bool = False
    traceback_files: list[tuple[str, int]] = field(default_factory=list)
    review_security: bool = False
    wants_tests: bool = False

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "file_paths": self.file_paths,
            "symbols": self.symbols,
            "is_traceback": self.is_traceback,
            "review_security": self.review_security,
            "wants_tests": self.wants_tests,
        }


def _has(text: str, *needles: str) -> bool:
    return any(needle in text for needle in needles)


def detect_intent(query: str) -> Intent:
    text = (query or "").strip()
    lowered = text.lower()

    file_paths = [
        match.replace("\\", "/").lstrip("./")
        for match in _FILE_RE.findall(text)
    ]
    traceback_files = [
        (path.replace("\\", "/"), int(line))
        for path, line in _TRACEBACK_RE.findall(text)
        if path
    ]
    for path, colon_line, word_line in _FILE_LINE_RE.findall(text):
        line = int(colon_line or word_line)
        entry = (path.replace("\\", "/"), line)
        if entry not in traceback_files:
            traceback_files.append(entry)
    is_traceback = bool(
        "traceback (most recent call last)" in lowered
        or "stack trace" in lowered
        or "file \"" in lowered and "line " in lowered
        or "exception" in lowered and "line" in lowered
        or ("traceback" in lowered and traceback_files)
    )
    symbols = _SYMBOL_RE.findall(text) or _CALL_RE.findall(text)
    for match in _IMPACT_CHANGE_RE.findall(text) + _SYMBOL_NOUN_RE.findall(text):
        name = match.strip("`'\"")
        if name.lower() not in _SYMBOL_STOPWORDS and name not in symbols:
            symbols.append(name)

    security_terms = (
        "security", "vulnerab", "unsafe", "exploit", "injection", "xss",
        "csrf", "secret", "credential", "sanitiz", "sql injection",
    )
    review_terms = (
        "review", "code smell", "refactor", "duplicated", "duplication",
        "unused import", "lint", "maintainab", "suspicious pattern",
        "potential bug", "find bugs", "find potential bugs", "improve",
    )
    debug_terms = (
        "traceback", "error", "exception", "failing", "failed", "fail", "why does",
        "why is", "bug", "crash", "debug", "root cause", "not working",
        "breaks", "broken",
    )
    test_terms = (
        "test", "coverage", "pytest", "which tests", "tests should",
        "test selection", "untested",
    )
    impact_terms = (
        "impact", "what will break", "what breaks", "what could break",
        "what happens if", "if i change", "if we change", "if i modify",
        "if we modify", "change the", "modify the", "affect", "affected",
        "high risk", "risk score", "safe to merge", "remove this function",
        "removing this function", "depend on", "dependencies", "depends",
        "blast radius",
    )
    git_terms = (
        "git", "commit", "diff", "changed", "change", "branch", "working tree",
        "latest change", "recent change", "merge",
    )
    architecture_terms = (
        "architecture", "folder structure", "directory structure", "data flow",
        "entry point", "entrypoint", "overall", "where is", "where are",
        "how does data", "which files", "purpose of this folder",
        "project structure", "module does",
    )

    review_security = _has(lowered, *security_terms)
    wants_tests = _has(lowered, *test_terms)

    if is_traceback:
        name = "debug"
    elif review_security:
        name = "security_review"
    elif _has(lowered, *review_terms):
        name = "code_review"
    elif _has(lowered, *debug_terms):
        name = "debug"
    elif wants_tests:
        name = "tests"
    elif _has(lowered, *impact_terms):
        name = "impact"
    elif _has(lowered, *git_terms) and not _has(lowered, "explain"):
        name = "git"
    elif _has(lowered, *architecture_terms):
        name = "architecture"
    elif _has(lowered, "explain", "what does", "line by line", "how does", "what is this"):
        name = "explain"
    elif file_paths:
        name = "explain"
    else:
        name = "general"

    # "Which tests should I run for utils/validators.py?" is still a test
    # question; keep the file hint so retrieval can focus.
    return Intent(
        name=name,
        query=text,
        file_paths=list(dict.fromkeys(file_paths)),
        symbols=list(dict.fromkeys(symbols)),
        is_traceback=is_traceback,
        traceback_files=traceback_files,
        review_security=review_security and name in ("security_review", "code_review"),
        wants_tests=wants_tests,
    )


def follow_up_suggestions(intent: Intent, cited_files: list[str]) -> list[str]:
    """Three contextual next questions shown under an assistant answer."""
    first_file = cited_files[0] if cited_files else "the main module"
    if intent.name == "explain":
        return [
            f"Which files depend on {first_file}?",
            f"What tests cover {first_file}?",
            f"What could break if I modify {first_file}?",
        ]
    if intent.name == "architecture":
        return [
            "Explain the main entry point.",
            "Which modules have the most dependents?",
            "Explain the latest Git changes.",
        ]
    if intent.name == "debug":
        return [
            "Which tests should I run to verify the fix?",
            "Show the dependency chain around the failing code.",
            "Review the suspect file for potential bugs.",
        ]
    if intent.name in ("code_review", "security_review"):
        return [
            "Which findings are confirmed versus potential?",
            "Suggest a minimal safe fix for the highest-severity finding.",
            "Which tests cover the files with findings?",
        ]
    if intent.name == "impact":
        return [
            "Why were these tests recommended?",
            "Which affected files have no coverage?",
            "Is this change safe to merge?",
        ]
    if intent.name == "tests":
        return [
            "Which tests are coverage-backed versus heuristic?",
            "Which changed files have no test coverage?",
            "What will break if I modify the highest-risk file?",
        ]
    if intent.name == "git":
        return [
            "Explain the impact of these changes.",
            "Which tests should I run for this diff?",
            "Which changed entities belong to functions?",
        ]
    return [
        "Explain my project architecture.",
        "Find potential bugs in my project.",
        "Which parts of my project are most risky?",
    ]
