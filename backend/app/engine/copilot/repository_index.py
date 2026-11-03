"""In-memory retrieval index for a scanned Python repository.

IMPACTMAP Copilot does not send a repository to the model. It builds a local
BM25 index over files, AST symbols and docstrings, then combines lexical hits
with graph expansion. This is a retrieval-augmented generation pipeline without
requiring an embedding service or an additional network dependency.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from app.core.logging import logger
from app.engine.copilot.secrets import redact_secrets, should_skip_file
from app.engine.parser.python_parser import ModuleParseResult
from app.engine.scanner.repository_scanner import RepositoryScanResult


_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\d+")
_SPLIT_RE = re.compile(r"[^A-Za-z0-9_]+")
_STOPWORDS = {
    "the", "and", "for", "that", "this", "with", "from", "into", "what",
    "which", "where", "when", "how", "why", "does", "do", "is", "are", "was",
    "were", "be", "been", "being", "a", "an", "of", "to", "in", "on", "at",
    "by", "as", "it", "its", "or", "if", "then", "than", "so", "can", "could",
    "should", "would", "will", "please", "explain", "show", "tell", "me", "my",
    "our", "your", "project", "code", "file", "function", "class", "module",
    "use", "used", "using", "about", "there", "their", "here", "have", "has",
}


def tokenize(text: str) -> list[str]:
    """Split identifiers into searchable terms (snake_case and CamelCase)."""
    if not text:
        return []
    raw: list[str] = []
    for token in _TOKEN_RE.findall(text):
        raw.append(token.lower())
        # snake_case -> parts
        for part in _SPLIT_RE.split(token):
            if part and part.lower() != token.lower():
                raw.append(part.lower())
        # CamelCase -> parts (only when the token has mixed case)
        if any(ch.isupper() for ch in token[1:]):
            for part in re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+", token):
                if part:
                    raw.append(part.lower())
    return [term for term in raw if term and term not in _STOPWORDS and len(term) > 1]


@dataclass
class IndexedSymbol:
    name: str
    qualified_name: str
    kind: str
    file_path: str
    line_start: int
    line_end: int
    docstring: str | None = None
    is_test: bool = False


@dataclass
class IndexedFile:
    path: str
    module_name: str
    content: str
    line_count: int
    symbols: list[IndexedSymbol] = field(default_factory=list)
    docstring: str | None = None
    is_test: bool = False


@dataclass
class RetrievalHit:
    kind: str  # file | symbol
    file_path: str
    name: str
    qualified_name: str = ""
    line_start: int = 0
    line_end: int = 0
    score: float = 0.0
    reason: str = ""
    snippet: str = ""
    is_test: bool = False

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "file_path": self.file_path,
            "name": self.name,
            "qualified_name": self.qualified_name,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "score": round(self.score, 3),
            "reason": self.reason,
            "snippet": self.snippet,
            "is_test": self.is_test,
        }


class _Document:
    __slots__ = ("key", "kind", "hit", "tokens", "length")

    def __init__(self, key: str, kind: str, hit: RetrievalHit, tokens: list[str]):
        self.key = key
        self.kind = kind
        self.hit = hit
        self.tokens = tokens
        self.length = max(1, len(tokens))


class RepositoryIndex:
    """BM25 index over files and symbols, with exact-name and path boosts."""

    def __init__(
        self,
        repo_path: str,
        files: dict[str, IndexedFile],
        k1: float = 1.4,
        b: float = 0.75,
    ):
        self.repo_path = repo_path
        self.files = files
        self.k1 = k1
        self.b = b
        self.documents: list[_Document] = []
        self._df: Counter[str] = Counter()
        self._build()

    # ── construction ─────────────────────────────────────────────

    @classmethod
    def from_scan(
        cls, repo_path: str | Path, scan: RepositoryScanResult
    ) -> "RepositoryIndex":
        root = Path(repo_path)
        files: dict[str, IndexedFile] = {}
        for module in scan.modules:
            path = module.file_path.replace("\\", "/")
            if should_skip_file(path):
                continue
            content = _read_file(root / path)
            if content is None:
                logger.debug("Copilot index skipped unreadable file %s", path)
                continue
            symbols = _symbols_for(module)
            files[path] = IndexedFile(
                path=path,
                module_name=module.module_name,
                content=redact_secrets(content),
                line_count=module.line_count or content.count("\n") + 1,
                symbols=symbols,
                is_test=_is_test_path(path),
            )
        logger.info("Copilot index built: %d files", len(files))
        return cls(str(root), files)

    def _build(self) -> None:
        for file in self.files.values():
            symbol_text = " ".join(
                f"{s.name} {s.qualified_name} {s.docstring or ''}"
                for s in file.symbols[:400]
            )
            doc_tokens = tokenize(
                f"{file.path} {file.module_name} {symbol_text} {file.content[:20000]}"
            )
            self.documents.append(
                _Document(
                    key=f"file:{file.path}",
                    kind="file",
                    hit=RetrievalHit(
                        kind="file",
                        file_path=file.path,
                        name=Path(file.path).name,
                        qualified_name=file.module_name,
                        line_start=1,
                        line_end=file.line_count,
                        reason="File content and symbol names",
                        is_test=file.is_test,
                    ),
                    tokens=doc_tokens,
                )
            )
            for symbol in file.symbols:
                span = _span(file.content, symbol.line_start, symbol.line_end)
                self.documents.append(
                    _Document(
                        key=f"symbol:{file.path}::{symbol.kind}:{symbol.qualified_name}",
                        kind="symbol",
                        hit=RetrievalHit(
                            kind="symbol",
                            file_path=file.path,
                            name=symbol.name,
                            qualified_name=symbol.qualified_name,
                            line_start=symbol.line_start,
                            line_end=symbol.line_end,
                            reason=f"{symbol.kind} definition",
                            snippet=redact_secrets(span),
                            is_test=symbol.is_test or file.is_test,
                        ),
                        tokens=tokenize(
                            f"{symbol.name} {symbol.qualified_name} "
                            f"{symbol.docstring or ''} {span[:6000]}"
                        ),
                    )
                )

        for document in self.documents:
            for term in set(document.tokens):
                self._df[term] += 1
        self._avgdl = (
            sum(document.length for document in self.documents) / len(self.documents)
            if self.documents
            else 1.0
        )
        self._n = max(1, len(self.documents))

    # ── search ───────────────────────────────────────────────────

    def search(
        self,
        query: str,
        *,
        top_k: int = 6,
        file_hint: str | None = None,
        symbol_hint: str | None = None,
        include_tests: bool = False,
    ) -> list[RetrievalHit]:
        terms = tokenize(query)
        if not terms:
            return []
        query_counts = Counter(terms)
        lowered_query = query.lower()
        scored: list[tuple[float, _Document]] = []

        for document in self.documents:
            if document.hit.is_test and not include_tests:
                continue
            counts = Counter(document.tokens)
            score = 0.0
            for term, qtf in query_counts.items():
                tf = counts.get(term, 0)
                if not tf:
                    continue
                df = self._df.get(term, 0)
                idf = math.log(1 + (self._n - df + 0.5) / (df + 0.5))
                denominator = tf + self.k1 * (
                    1 - self.b + self.b * document.length / self._avgdl
                )
                score += idf * (tf * (self.k1 + 1) / denominator) * min(qtf, 3)

            if score <= 0 and not file_hint and not symbol_hint:
                continue

            path_lower = document.hit.file_path.lower()
            name_lower = document.hit.name.lower()
            qname_lower = document.hit.qualified_name.lower()
            if document.hit.file_path in query or Path(document.hit.file_path).name in query:
                score += 12.0
            if name_lower and re.search(rf"\b{re.escape(name_lower)}\b", lowered_query):
                score += 7.0
            if qname_lower and qname_lower in lowered_query:
                score += 9.0
            if file_hint and file_hint.lower() in path_lower:
                score += 15.0
            if symbol_hint and (
                symbol_hint.lower() == name_lower
                or symbol_hint.lower() in qname_lower
            ):
                score += 14.0
            if path_lower.endswith("__init__.py"):
                score *= 0.85
            if document.kind == "symbol":
                score *= 1.08
            if score > 0:
                scored.append((score, document))

        scored.sort(key=lambda item: (-item[0], item[1].hit.file_path))
        hits: list[RetrievalHit] = []
        seen_keys: set[str] = set()
        seen_files: Counter[str] = Counter()
        for score, document in scored:
            hit = document.hit
            # At most two symbols per file keeps context diverse.
            if document.kind == "symbol" and seen_files[hit.file_path] >= 2:
                continue
            key = document.key
            if key in seen_keys:
                continue
            seen_keys.add(key)
            if document.kind == "symbol":
                seen_files[hit.file_path] += 1
            else:
                seen_files[hit.file_path] += 1
            hit = RetrievalHit(**{**hit.__dict__, "score": round(score, 3)})
            if hit.kind == "file" and not hit.snippet:
                file = self.files[hit.file_path]
                hit.snippet = redact_secrets(_file_snippet(file.content, query))
            hits.append(hit)
            if len(hits) >= top_k:
                break
        return hits

    # ── lookup ───────────────────────────────────────────────────

    def file(self, path: str) -> IndexedFile | None:
        normalized = path.replace("\\", "/").lstrip("./")
        if normalized in self.files:
            return self.files[normalized]
        for key, value in self.files.items():
            if key.endswith("/" + normalized) or Path(key).name == normalized:
                return value
        return None

    def symbol(self, name: str) -> IndexedFile | None:
        for file in self.files.values():
            for symbol in file.symbols:
                if symbol.name == name or symbol.qualified_name.endswith("." + name):
                    return file
        return None

    def snippet(self, path: str, start: int, end: int, limit: int = 160) -> str:
        file = self.file(path)
        if not file:
            return ""
        return redact_secrets(_span(file.content, start, min(end, start + limit - 1)))

    def architecture(self) -> dict:
        """Small, factual overview used for architecture questions."""
        packages: Counter[str] = Counter()
        symbols = 0
        for file in self.files.values():
            parent = str(Path(file.path).parent)
            packages[parent if parent != "." else "(root)"] += 1
            symbols += len(file.symbols)
        return {
            "files": len(self.files),
            "symbols": symbols,
            "packages": packages.most_common(20),
        }

    def documents_for(self, paths: Iterable[str]) -> list[IndexedFile]:
        return [self.files[path] for path in paths if path in self.files]


def _read_file(path: Path) -> str | None:
    try:
        if path.stat().st_size > 2_000_000:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _symbols_for(module: ModuleParseResult) -> list[IndexedSymbol]:
    symbols: list[IndexedSymbol] = []
    seen: set[str] = set()
    for func in module.functions:
        key = f"{func.qualified_name}:{func.line_start}"
        if key in seen:
            continue
        seen.add(key)
        symbols.append(
            IndexedSymbol(
                name=func.name,
                qualified_name=func.qualified_name,
                kind="method" if func.is_method else "function",
                file_path=module.file_path,
                line_start=func.line_start,
                line_end=func.line_end,
                docstring=func.docstring,
            )
        )
    for cls in module.classes:
        key = f"{cls.qualified_name}:{cls.line_start}"
        if key not in seen:
            seen.add(key)
            symbols.append(
                IndexedSymbol(
                    name=cls.name,
                    qualified_name=cls.qualified_name,
                    kind="class",
                    file_path=module.file_path,
                    line_start=cls.line_start,
                    line_end=cls.line_end,
                    docstring=cls.docstring,
                )
            )
        for method in cls.methods:
            method_key = f"{method.qualified_name}:{method.line_start}"
            if method_key in seen:
                continue
            seen.add(method_key)
            symbols.append(
                IndexedSymbol(
                    name=method.name,
                    qualified_name=method.qualified_name,
                    kind="method",
                    file_path=module.file_path,
                    line_start=method.line_start,
                    line_end=method.line_end,
                    docstring=method.docstring,
                )
            )
    return symbols


def _is_test_path(path: str) -> bool:
    parts = {part.lower() for part in Path(path).parts[:-1]}
    name = Path(path).name.lower()
    return (
        "tests" in parts
        or "test" in parts
        or name.startswith("test_")
        or name.endswith("_test.py")
    )


def _span(content: str, start: int, end: int) -> str:
    lines = content.splitlines()
    if not lines:
        return ""
    start = max(1, start)
    end = min(max(start, end), len(lines))
    return "\n".join(lines[start - 1 : end])


def _file_snippet(content: str, query: str, max_lines: int = 80) -> str:
    lines = content.splitlines()
    if not lines:
        return ""
    terms = set(tokenize(query))
    if terms:
        for index, line in enumerate(lines):
            line_terms = set(tokenize(line))
            if terms & line_terms:
                start = max(0, index - 12)
                end = min(len(lines), start + max_lines)
                return "\n".join(lines[start:end])
    header = []
    for line in lines[:max_lines]:
        header.append(line)
        if line.startswith('"""') or line.startswith("'''"):
            continue
    return "\n".join(header)
