"""Evidence-based static review used by IMPACTMAP Copilot.

These checks are deterministic AST/text inspections. They report the presence of
a pattern, not proof that it is exploitable: every finding carries a confidence
label so the UI can distinguish confirmed patterns from items needing review.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

from app.engine.copilot.repository_index import IndexedFile
from app.engine.copilot.secrets import redact_secrets

_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}
_SECRET_NAME_RE = re.compile(
    r"(?i)(password|passwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret)"
)
_COMMENT_RE = re.compile(r"#\s*(TODO|FIXME|XXX|HACK)\b", re.IGNORECASE)


@dataclass
class ReviewFinding:
    file_path: str
    line: int
    severity: str  # high | medium | low
    category: str  # security | logic | maintainability | dependency
    title: str
    explanation: str
    suggestion: str
    confidence: str  # confirmed-pattern | potential
    symbol: str = ""

    def to_dict(self) -> dict:
        return {
            "file_path": self.file_path,
            "line": self.line,
            "severity": self.severity,
            "category": self.category,
            "title": self.title,
            "explanation": self.explanation,
            "suggestion": self.suggestion,
            "confidence": self.confidence,
            "symbol": self.symbol,
        }


def review_file(file: IndexedFile, security_only: bool = False) -> list[ReviewFinding]:
    findings: list[ReviewFinding] = []
    try:
        tree = ast.parse(file.content, filename=file.path)
    except SyntaxError as exc:
        return [
            ReviewFinding(
                file_path=file.path,
                line=exc.lineno or 1,
                severity="high",
                category="logic",
                title="Syntax error prevents analysis",
                explanation=f"Python could not parse this file: {exc.msg}.",
                suggestion="Fix the syntax error; downstream dependency and impact analysis cannot see its symbols.",
                confidence="confirmed-pattern",
            )
        ]

    parent: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parent[child] = node

    def enclosing_symbol(node: ast.AST) -> str:
        current = node
        parts: list[str] = []
        while current in parent:
            current = parent[current]
            if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                parts.append(current.name)
        return ".".join(reversed(parts))

    # ── security patterns ───────────────────────────────────────
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _call_name(node.func)
            short = name.split(".")[-1]
            if short in {"eval", "exec"}:
                findings.append(
                    _finding(
                        file, node, "high", "security",
                        f"Use of {short}()",
                        f"{short}() executes dynamically supplied code. This is a confirmed dangerous "
                        "pattern; exploitability depends on whether the input can be influenced externally.",
                        "Replace dynamic execution with an explicit parser, dispatch table or validated data structure.",
                        "confirmed-pattern", enclosing_symbol(node),
                    )
                )
            if short in {"system", "popen"} and name.startswith(("os.", "subprocess.")):
                findings.append(
                    _finding(
                        file, node, "high", "security",
                        f"Shell execution via {name}()",
                        "Starting a shell process can permit command injection if arguments include "
                        "untrusted input. Confirm whether the arguments are externally controlled.",
                        "Use an argument list with shell=False and validate every path/argument.",
                        "confirmed-pattern", enclosing_symbol(node),
                    )
                )
            if name in {"subprocess.call", "subprocess.run", "subprocess.Popen", "subprocess.check_output"}:
                if any(
                    keyword.arg == "shell"
                    and isinstance(keyword.value, ast.Constant)
                    and keyword.value.value is True
                    for keyword in node.keywords
                ):
                    findings.append(
                        _finding(
                            file, node, "high", "security",
                            "subprocess call with shell=True",
                            "shell=True makes command strings interpret shell metacharacters. "
                            "If any part is user-controlled, command injection is possible.",
                            "Pass an argument list and remove shell=True, or strictly validate each argument.",
                            "confirmed-pattern", enclosing_symbol(node),
                        )
                    )
            if name in {"pickle.load", "pickle.loads", "marshal.loads"}:
                findings.append(
                    _finding(
                        file, node, "medium", "security",
                        f"Unsafe deserialization with {name}()",
                        "Deserializing untrusted data with pickle/marshal can execute arbitrary code.",
                        "Use JSON or another data-only format for untrusted input. Only unpickle data from a trusted source.",
                        "potential", enclosing_symbol(node),
                    )
                )
            if name in {"yaml.load", "yaml.unsafe_load"} and not _safe_yaml(node):
                findings.append(
                    _finding(
                        file, node, "medium", "security",
                        f"Potentially unsafe YAML load ({name})",
                        "yaml.load without SafeLoader can instantiate arbitrary Python objects.",
                        "Use yaml.safe_load() or pass Loader=yaml.SafeLoader.",
                        "potential", enclosing_symbol(node),
                    )
                )

    # ── logic / maintainability ─────────────────────────────────
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            findings.append(
                _finding(
                    file, node, "medium", "logic",
                    "Bare except clause",
                    "A bare except catches BaseException, including KeyboardInterrupt and SystemExit, "
                    "and hides the original failure.",
                    "Catch the specific exception types you can handle, and log or re-raise the rest.",
                    "confirmed-pattern", enclosing_symbol(node),
                )
            )
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not security_only:
                mutable = _mutable_defaults(node)
                if mutable:
                    findings.append(
                        _finding(
                            file, node, "medium", "logic",
                            "Mutable default argument",
                            "Default values are evaluated once. Mutating "
                            + ", ".join(mutable)
                            + " will leak state between calls.",
                            "Use None as the default and create a fresh container inside the function.",
                            "confirmed-pattern", enclosing_symbol(node),
                        )
                    )
                branches = _branch_count(node)
                if branches > 15:
                    findings.append(
                        _finding(
                            file, node, "low", "maintainability",
                            "High branch complexity",
                            f"Approximately {branches} branch points were found in this function.",
                            "Split independent decisions into smaller functions and add tests for each branch.",
                            "confirmed-pattern", enclosing_symbol(node),
                        )
                    )
            for arg, default in _secret_defaults(node):
                value = getattr(default, "value", "")
                if isinstance(value, str) and len(value) >= 8:
                    findings.append(
                        _finding(
                            file, default, "high", "security",
                            f"Hardcoded credential-like value in parameter '{arg}'",
                            "The source contains a literal value assigned to a secret-looking name: "
                            + redact_secrets(value),
                            "Load the value from an environment variable or secret manager; rotate it if it was real.",
                            "potential", enclosing_symbol(node),
                        )
                    )
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            target = node.targets[0] if isinstance(node, ast.Assign) else node.target
            value = node.value
            if isinstance(target, ast.Name) and _SECRET_NAME_RE.search(target.id):
                if isinstance(value, ast.Constant) and isinstance(value.value, str) and len(value.value) >= 8:
                    findings.append(
                        _finding(
                            file, node, "high", "security",
                            f"Hardcoded credential-like assignment to '{target.id}'",
                            "A literal string is assigned to a secret-looking variable: "
                            + redact_secrets(value.value),
                            "Move the value to an environment variable or secret manager and rotate it if it was ever committed.",
                            "potential", enclosing_symbol(node),
                        )
                    )

    if not security_only:
        findings.extend(_unused_imports(file, tree))
        findings.extend(_duplicate_functions(file, tree))
        for line_number, line in enumerate(file.content.splitlines(), start=1):
            match = _COMMENT_RE.search(line)
            if match:
                findings.append(
                    ReviewFinding(
                        file_path=file.path,
                        line=line_number,
                        severity="low",
                        category="maintainability",
                        title=f"{match.group(1)} comment",
                        explanation="A tracked follow-up marker exists in this file.",
                        suggestion="Resolve the item or link it to an issue so it is not forgotten.",
                        confidence="confirmed-pattern",
                    )
                )

    unique: dict[tuple[str, int, str], ReviewFinding] = {}
    for finding in findings:
        unique[(finding.file_path, finding.line, finding.title)] = finding
    return list(unique.values())


def review_repository(
    files: list[IndexedFile],
    *,
    security_only: bool = False,
    limit: int = 40,
) -> list[ReviewFinding]:
    findings: list[ReviewFinding] = []
    for file in files:
        if file.is_test:
            continue
        findings.extend(review_file(file, security_only=security_only))
    findings.sort(key=lambda f: (_SEVERITY_ORDER.get(f.severity, 3), f.file_path, f.line))
    return findings[:limit]


def summarized_findings(findings: list[ReviewFinding]) -> list[dict]:
    return [finding.to_dict() for finding in findings]


def _finding(
    file: IndexedFile,
    node: ast.AST,
    severity: str,
    category: str,
    title: str,
    explanation: str,
    suggestion: str,
    confidence: str,
    symbol: str = "",
) -> ReviewFinding:
    return ReviewFinding(
        file_path=file.path,
        line=getattr(node, "lineno", 1),
        severity=severity,
        category=category,
        title=title,
        explanation=explanation,
        suggestion=suggestion,
        confidence=confidence,
        symbol=symbol,
    )


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parts: list[str] = []
        current: ast.AST = node
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
        return ".".join(reversed(parts))
    return ""


def _safe_yaml(node: ast.Call) -> bool:
    for keyword in node.keywords:
        if keyword.arg == "Loader":
            return "Safe" in _call_name(keyword.value)
    return False


def _mutable_defaults(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    args = [*node.args.args, *node.args.kwonlyargs, *node.args.posonlyargs]
    defaults = [*node.args.defaults, *node.args.kw_defaults]
    names: list[str] = []
    for arg, default in zip(args[-len(defaults):], defaults):
        if isinstance(default, (ast.List, ast.Dict, ast.Set)):
            names.append(arg.arg)
    return names


def _secret_defaults(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[tuple[str, ast.AST]]:
    args = [*node.args.args, *node.args.kwonlyargs, *node.args.posonlyargs]
    defaults = [*node.args.defaults, *node.args.kw_defaults]
    matches: list[tuple[str, ast.AST]] = []
    for arg, default in zip(args[-len(defaults):], defaults):
        if default is not None and _SECRET_NAME_RE.search(arg.arg):
            matches.append((arg.arg, default))
    return matches


def _branch_count(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    count = 0
    for child in ast.walk(node):
        if isinstance(child, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try)):
            count += 1
        elif isinstance(child, ast.BoolOp):
            count += len(child.values) - 1
        elif isinstance(child, ast.IfExp):
            count += 1
        elif type(child).__name__ == "Match":
            count += len(getattr(child, "cases", []))
    return count


def _unused_imports(file: IndexedFile, tree: ast.Module) -> list[ReviewFinding]:
    if Path(file.path).name == "__init__.py":
        return []
    imported: dict[str, tuple[str, int]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                local = alias.asname or alias.name.split(".")[0]
                imported[local] = (alias.name, node.lineno)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "*":
                    continue
                local = alias.asname or alias.name
                imported[local] = (f"{node.module or ''}.{alias.name}", node.lineno)

    used: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            used.add(node.id)
        elif isinstance(node, ast.Attribute):
            current: ast.AST = node
            while isinstance(current, ast.Attribute):
                current = current.value
            if isinstance(current, ast.Name):
                used.add(current.id)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            used.update(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", node.value))
    for value in _all_exports(tree):
        used.add(value)

    findings: list[ReviewFinding] = []
    for local, (source, line) in imported.items():
        if local in used or local == "_":
            continue
        if local.endswith("_"):  # deliberately unused re-export convention
            continue
        findings.append(
            ReviewFinding(
                file_path=file.path,
                line=line,
                severity="low",
                category="maintainability",
                title=f"Unused import '{local}'",
                explanation=f"'{local}' was imported from '{source}' but is not referenced in this module.",
                suggestion="Remove the import, or add it to __all__ if it is a deliberate re-export.",
                confidence="confirmed-pattern",
            )
        )
    return findings


def _all_exports(tree: ast.Module) -> set[str]:
    exports: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets):
                if isinstance(node.value, (ast.List, ast.Tuple)):
                    for element in node.value.elts:
                        if isinstance(element, ast.Constant) and isinstance(element.value, str):
                            exports.add(element.value)
    return exports


def _duplicate_functions(file: IndexedFile, tree: ast.Module) -> list[ReviewFinding]:
    signatures: dict[str, tuple[str, int, int]] = {}
    findings: list[ReviewFinding] = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if len(node.body) < 2:
            continue
        normalized = ast.dump(ast.Module(body=node.body, type_ignores=[]), annotate_fields=False)
        if normalized in signatures:
            other_name, other_line, other_end = signatures[normalized]
            findings.append(
                ReviewFinding(
                    file_path=file.path,
                    line=node.lineno,
                    severity="low",
                    category="maintainability",
                    title=f"Possible duplicated logic: {node.name}() matches {other_name}()",
                    explanation=(
                        f"The bodies of {node.name}() (line {node.lineno}) and "
                        f"{other_name}() (line {other_line}) are structurally identical."
                    ),
                    suggestion="Extract the shared body into one helper to avoid divergent fixes.",
                    confidence="potential",
                    symbol=node.name,
                )
            )
        else:
            signatures[normalized] = (node.name, node.lineno, node.end_lineno or node.lineno)
    return findings
