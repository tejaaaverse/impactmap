"""Deterministic, evidence-cited answers used when no model is configured.

These answers are not a fallback stub: they report the same scan, graph, Git,
impact, selection and review evidence that would be sent to a language model.
Each claim points at an ``[E#]`` evidence item with an exact path and line span.
"""

from __future__ import annotations

from typing import Any, Iterable

from app.engine.copilot.context_builder import CopilotContext, Evidence


def answer_offline(context: CopilotContext) -> str:
    intent = context.intent.name
    if intent == "explain":
        return _explain(context)
    if intent == "architecture":
        return _architecture(context)
    if intent == "git":
        return _git(context)
    if intent == "impact":
        return _impact(context)
    if intent == "tests":
        return _tests(context)
    if intent == "code_review":
        return _review(context, security=False)
    if intent == "security_review":
        return _review(context, security=True)
    if intent == "debug":
        return _debug(context)
    return _general(context)


# ── citation helpers ──────────────────────────────────────────


def _cite(item: Evidence | None, *, location: bool = True) -> str:
    if item is None:
        return ""
    if location and item.location:
        return f"`{item.location}` [{item.id}]"
    return f"[{item.id}]"


def _find_evidence(
    context: CopilotContext,
    *,
    kind: str | None = None,
    file_path: str | None = None,
    contains: str | None = None,
    line: int | None = None,
) -> Evidence | None:
    for item in context.evidence:
        if kind and item.kind != kind:
            continue
        if file_path and item.file_path != file_path:
            continue
        if contains and contains.lower() not in (item.title + " " + item.content).lower():
            continue
        if line is not None and item.line_start and item.line_start != line:
            continue
        return item
    return None


def _cite_for_file(context: CopilotContext, path: str) -> str:
    item = _find_evidence(context, file_path=path) or _find_evidence(
        context, kind="file", contains=path
    )
    return _cite(item) if item else f"`{path}`"


def _selected_tests(context: CopilotContext, limit: int = 8) -> list[tuple[str, dict[str, Any]]]:
    selection = context.live_selection or {}
    rows: list[tuple[str, dict[str, Any]]] = []
    for mode in ("optimized", "safe"):
        for test in (selection.get(mode) or {}).get("selected_tests", [])[:limit]:
            rows.append((mode, test))
    return rows


def _top_file(context: CopilotContext) -> Evidence | None:
    for raw in context.intent.file_paths:
        for item in context.evidence:
            if item.file_path and (item.file_path.endswith(raw) or raw.endswith(item.file_path)):
                if item.kind in {"file", "traceback"}:
                    return item
    for item in context.evidence:
        if item.kind == "file" and item.file_path:
            return item
    return None


def _summary_lines(context: CopilotContext) -> list[str]:
    scan = context.scan_summary
    graph = context.graph_stats
    return [
        f"- Python files: **{scan.get('total_files', 0)}**",
        f"- Functions/classes/methods: **{scan.get('total_functions', 0)} / "
        f"{scan.get('total_classes', 0)} / {scan.get('total_methods', 0)}**",
        f"- Resolved dependency edges: **{scan.get('total_dependencies', 0)}**",
        f"- Graph nodes/edges: **{graph.get('nodes', 0)} / {graph.get('edges', 0)}**",
    ]


def _warning_lines(context: CopilotContext) -> list[str]:
    if not context.warnings:
        return []
    lines = ["", "**Evidence limitations**"]
    lines.extend(f"- {warning}" for warning in context.warnings[:6])
    return lines


# ── per-intent answers ────────────────────────────────────────


def _explain(context: CopilotContext) -> str:
    file = _top_file(context)
    lines = ["## What this code does", ""]
    if not file:
        lines.append(
            "I could not identify a specific file or symbol from the question. "
            "Try naming a path (for example `app/services/repository_service.py`) "
            "or a symbol in backticks."
        )
        lines.extend(["", "Repository at a glance:"])
        lines.extend(_summary_lines(context))
        lines.extend(_warning_lines(context))
        return "\n".join(lines)

    path = file.file_path
    lines.append(
        f"The relevant file is {_cite(file)}. The answer below is derived from its "
        f"exact source, the static symbol graph and any current test-selection evidence."
    )
    lines.append("")
    lines.append("**Structure**")
    symbols = [
        item
        for item in context.evidence
        if item.kind == "symbol" and item.file_path == path
    ]
    if symbols:
        lines.extend(
            f"- `{item.title.split(' ', 1)[-1]}` (lines {item.line_start}-{item.line_end}) "
            f"[{item.id}]"
            for item in symbols[:10]
        )
    else:
        lines.append(
            f"- No function, class or method symbols were retained for this file; "
            f"the excerpt is cited at {_cite(file)}."
        )

    deps = _find_evidence(context, kind="dependency", file_path=path)
    if deps:
        lines.extend(["", "**Dependency position**", f"{deps.content}", f"[{deps.id}]"])

    lines.extend(["", "**Relevant tests**"])
    tests = _selected_tests(context, limit=4)
    if tests:
        for mode, test in tests[:5]:
            cite = _cite_for_file(context, str(test.get("file_path", "")))
            lines.append(
                f"- `{test.get('test_id')}` ({mode}, score {test.get('score')}) — "
                f"{'; '.join(test.get('reasons', [])[:2])} — {cite}"
            )
    else:
        selection = context.live_selection or {}
        lines.append(
            "- No live test-selection evidence is available for this question. "
            "Run an analysis or ask which tests cover this file."
            if not selection
            else "- No selected test specifically points at this file."
        )
    lines.extend(_warning_lines(context))
    return "\n".join(lines)


def _architecture(context: CopilotContext) -> str:
    lines = [
        "## Repository architecture",
        "",
        "This is a factual snapshot from the current scan and dependency graph.",
        "",
    ]
    lines.extend(_summary_lines(context))
    if context.coverage:
        lines.append(
            f"- Coverage contexts available: **{context.coverage.get('contexts_available')}** "
            f"({context.coverage.get('tests', 0)} measured tests, "
            f"{context.coverage.get('files', 0)} files)"
        )

    package = _find_evidence(context, kind="architecture", contains="Package layout")
    if package:
        lines.extend(["", "**Package layout**", f"{package.content}", f"[{package.id}]"])

    entries = [
        item
        for item in context.evidence
        if item.kind == "architecture" and "entry point" in item.title.lower()
    ]
    if entries:
        lines.extend(["", "**Likely entry points**"])
        lines.extend(
            f"- {_cite(item)} — {item.reason}" for item in entries[:5]
        )

    hotspots = _find_evidence(context, kind="architecture", contains="Most imported")
    if hotspots:
        lines.extend(["", "**Dependency hotspots**", hotspots.content, f"[{hotspots.id}]"])

    if context.live_changes:
        summary = context.live_changes.get("summary", {})
        lines.extend(
            [
                "",
                "**Current change surface**",
                f"- {summary.get('files', 0)} Python file(s) differ between "
                f"`{context.live_changes.get('base_ref')}` and "
                f"`{context.live_changes.get('head_ref')}`.",
            ]
        )

    lines.extend(["", "**How to read the graph**"])
    lines.append(
        "- Edges point from dependent to dependency (caller → callee, importer → "
        "imported module). Impact analysis walks incoming edges to find affected "
        "callers/importers. This is static coupling, not runtime tracing."
    )
    lines.extend(_warning_lines(context))
    return "\n".join(lines)


def _git(context: CopilotContext) -> str:
    info = context.git_info
    lines = ["## Git state"]
    if not info.get("is_repository"):
        lines.extend(
            [
                "",
                "This directory is **not a Git repository**, so commit-to-commit and "
                "working-tree diff analysis are unavailable. Scanning, symbol graphs and "
                "static review still work. Initialize Git or point IMPACTMAP at a Git "
                "worktree to use change impact and test selection.",
            ]
        )
        if info.get("error"):
            lines.extend(["", f"Git reported: `{info['error']}`"])
        return "\n".join(lines)

    lines.extend(
        [
            "",
            f"- Branch: **{info.get('current_branch') or 'detached HEAD'}**",
            f"- Commits visible: **{info.get('commit_count', 0)}**",
            f"- Working tree dirty: **{info.get('dirty')}** "
            f"(staged {info.get('staged_files', 0)}, unstaged "
            f"{info.get('unstaged_files', 0)}, untracked {info.get('untracked_files', 0)})",
            f"- Recommended comparison: `{info.get('recommended_base')}.."
            f"{info.get('recommended_head')}`",
        ]
    )

    commits = info.get("commits") or []
    if commits:
        lines.extend(["", "**Recent commits**"])
        for commit in commits[:5]:
            lines.append(
                f"- `{commit.get('short_sha')}` {commit.get('subject')} "
                f"— {commit.get('author')}, {commit.get('committed_at')}"
            )
    else:
        lines.extend(["", "No commits exist yet."])

    changes = context.live_changes
    if changes:
        summary = changes.get("summary", {})
        lines.extend(
            [
                "",
                f"**Live diff `{changes.get('base_ref')}..{changes.get('head_ref')}`**",
                f"- {summary.get('files', 0)} file(s), {summary.get('entities', 0)} "
                f"changed entities",
                f"- Added {summary.get('added_files', 0)}, modified "
                f"{summary.get('modified_files', 0)}, deleted "
                f"{summary.get('deleted_files', 0)}, renamed "
                f"{summary.get('renamed_files', 0)}",
            ]
        )
        files = changes.get("files", [])
        for item in files[:10]:
            path = item.get("path")
            if not path:
                continue
            lines.append(
                f"- `{path}` — {item.get('change_type')}, "
                f"+{item.get('added_line_count', 0)}/-{item.get('deleted_line_count', 0)} "
                f"— {_cite_for_file(context, path)}"
            )
        if not files:
            lines.append("- No Python file differences were detected for this range.")

        impact = context.live_impact
        if impact:
            summary = impact.get("summary", {})
            lines.extend(
                [
                    "",
                    "**Impact of this diff**",
                    f"- Direct: {summary.get('direct_count', 0)}; indirect: "
                    f"{summary.get('indirect_count', 0)}; affected files: "
                    f"{summary.get('affected_file_count', 0)}; max depth: "
                    f"{summary.get('max_depth', 0)}.",
                ]
            )
    else:
        lines.extend(
            ["", "A live Git diff could not be computed. See the warnings below."]
        )

    lines.extend(_warning_lines(context))
    return "\n".join(lines)


def _impact(context: CopilotContext) -> str:
    hypothetical = context.hypothetical_impact
    data = hypothetical or context.live_impact
    heading = "## Hypothetical impact" if hypothetical else "## Impact of the current change"
    lines = [heading, ""]

    if not data:
        stored = context.stored_analysis
        if stored:
            summary = (stored.get("impact") or {}).get("summary", {})
            lines.extend(
                [
                    "No live Git diff is available, but a previous analysis exists.",
                    "",
                    f"- Analysis `{stored.get('id')}` compared "
                    f"`{stored.get('base_ref')}..{stored.get('head_ref')}`.",
                    f"- Affected entities: **{summary.get('total_affected', 0)}** "
                    f"(direct {summary.get('direct_count', 0)}, indirect "
                    f"{summary.get('indirect_count', 0)}).",
                    "- Open that analysis to inspect individual dependency paths.",
                ]
            )
        else:
            lines.append(
                "I have no diff or impact result to explain. Name a changed file for a "
                "hypothetical estimate, or run an analysis from the repository page."
            )
        lines.extend(_warning_lines(context))
        return "\n".join(lines)

    summary = data.get("summary", {})
    if hypothetical:
        lines.append(
            "This is a **static estimate for a proposed change**, not an observed Git "
            "diff. Scores are coupling-risk signals, not probabilities that code breaks."
        )
        lines.append("")
        lines.append(f"Proposed change: `{data.get('proposed_change', '')}`.")
    else:
        changed = context.live_changes or {}
        lines.append(
            f"Comparing `{changed.get('base_ref')}` with `{changed.get('head_ref')}` "
            f"({summary.get('changed_file_count', 0)} changed file(s), "
            f"{summary.get('changed_entity_count', 0)} changed entities)."
        )
    lines.extend(
        [
            "",
            f"- Direct impacts: **{summary.get('direct_count', 0)}**",
            f"- Indirect impacts: **{summary.get('indirect_count', 0)}**",
            f"- Affected files: **{summary.get('affected_file_count', 0)}**",
            f"- Maximum traversal depth: **{summary.get('max_depth', 0)}**",
        ]
    )
    if summary.get("truncated"):
        lines.append("- Traversal was **truncated** by the configured node limit; results are partial.")
    if summary.get("excluded_test_nodes"):
        lines.append(
            f"- {summary['excluded_test_nodes']} test-node encounter(s) were excluded "
            "because test nodes are not part of impact traversal by default."
        )

    for label, entries in (
        ("Direct", data.get("direct_impacts", [])),
        ("Indirect", data.get("indirect_impacts", [])),
    ):
        if not entries:
            continue
        lines.extend(["", f"**{label} impacts (highest score first)**"])
        for entry in entries[:8]:
            cite = _impact_cite(context, entry)
            lines.append(
                f"- `{entry.get('qualified_name')}` — {entry.get('type')} in "
                f"`{entry.get('file_path')}`"
                + (f":{entry.get('line_start')}" if entry.get("line_start") else "")
                + f" — score {entry.get('score')}, depth {entry.get('depth')} {cite}"
            )
            reason = entry.get("reason")
            if reason:
                lines.append(f"  - {reason}")
        if len(entries) > 8:
            lines.append(f"  - …and {len(entries) - 8} more in the impact evidence.")

    lines.extend(["", "**Method**"])
    lines.append(
        "Reverse traversal over incoming call/import/inheritance/containment edges. "
        "Each hop is weighted by edge type and confidence and decays with depth."
    )
    lines.extend(_warning_lines(context))
    return "\n".join(lines)


def _impact_cite(context: CopilotContext, entry: dict[str, Any]) -> str:
    for item in context.evidence:
        if item.kind != "impact":
            continue
        if item.file_path and item.file_path == entry.get("file_path"):
            if not entry.get("line_start") or item.line_start == entry.get("line_start"):
                return f"[{item.id}]"
    return ""


def _tests(context: CopilotContext) -> str:
    selection = context.live_selection
    lines = ["## Test selection", ""]
    if not selection:
        stored = context.stored_analysis
        if stored and stored.get("selection"):
            info = stored["selection"]
            lines.extend(
                [
                    "No live selection was computed for this question. The latest stored "
                    "analysis reports:",
                    "",
                    f"- Coverage available: **{info.get('coverage_available')}**",
                    f"- Measured tests: **{info.get('measured_tests', 0)}**",
                    f"- Discovered tests: **{info.get('total_tests_discovered', 0)}**",
                    "",
                    "Ask again in the context of a changed file, or run an analysis to get "
                    "a current safe/optimized recommendation.",
                ]
            )
        else:
            lines.append(
                "No test-selection result is available. Analyse a Git diff or name a "
                "changed file so selection can compute candidates."
            )
        lines.extend(_warning_lines(context))
        return "\n".join(lines)

    lines.extend(
        [
            f"- Coverage available: **{selection.get('coverage_available')}**",
            f"- Tests discovered: **{selection.get('total_tests_discovered', 0)}**",
            f"- Tests measured by coverage: **{selection.get('measured_tests', 0)}**",
        ]
    )
    if context.coverage:
        lines.append(
            f"- Coverage snapshot: **{context.coverage.get('collected_at') or 'metadata unavailable'}**"
        )
    if not selection.get("coverage_available"):
        lines.append(
            "- Without per-test coverage, selection is based on static reachability and "
            "explicitly falls back where it cannot justify exclusion."
        )

    for mode in ("safe", "optimized"):
        payload = selection.get(mode) or {}
        lines.extend(
            [
                "",
                f"**{mode.capitalize()} mode** — {payload.get('selected_count', 0)} of "
                f"{payload.get('total_tests', 0)} tests selected "
                f"({payload.get('reduction_percent', 0)}% reduction).",
            ]
        )
        if payload.get("fallback_used"):
            lines.append("- Fallback was used; see the warnings.")
        for warning in payload.get("warnings", [])[:3]:
            lines.append(f"- {warning}")
        tests = payload.get("selected_tests", [])
        for test in tests[:8]:
            cite = _cite_for_file(context, str(test.get("file_path", "")))
            lines.append(
                f"- `{test.get('test_id')}` — score {test.get('score')}, source "
                f"`{test.get('source')}` — {'; '.join(test.get('reasons', [])[:2])} — {cite}"
            )
        if len(tests) > 8:
            lines.append(f"- …and {len(tests) - 8} more selected test(s).")
        if not tests:
            lines.append("- No tests were selected in this mode.")

    lines.extend(["", "**Why these tests**"])
    lines.append(
        "Scores combine coverage of changed/affected entities, coverage of affected "
        "files, static reachability, changed test files and recent failures. Scores rank "
        "relevance; they are not failure probabilities."
    )
    lines.extend(_warning_lines(context))
    return "\n".join(lines)


def _review(context: CopilotContext, *, security: bool) -> str:
    title = "Security review" if security else "Code review"
    lines = [f"## {title}", ""]
    findings = context.findings
    if not findings:
        lines.append(
            "The deterministic checks found **no matching patterns** in the reviewed "
            "files. This is not proof that the code is correct or secure; it only means "
            "none of the configured AST/text rules fired."
        )
        lines.extend(_warning_lines(context))
        return "\n".join(lines)

    counts = {"high": 0, "medium": 0, "low": 0}
    confirmed = 0
    for finding in findings:
        counts[finding.get("severity", "low")] = counts.get(finding.get("severity", "low"), 0) + 1
        if finding.get("confidence") == "confirmed-pattern":
            confirmed += 1
    lines.extend(
        [
            f"Reviewed **{len({f.get('file_path') for f in findings})}** file(s) with "
            f"findings. Severity: **{counts.get('high', 0)} high**, "
            f"**{counts.get('medium', 0)} medium**, **{counts.get('low', 0)} low**. "
            f"{confirmed} finding(s) match a confirmed code pattern; the rest are "
            "potential risks requiring context.",
            "",
        ]
    )

    for severity, label in (("high", "High"), ("medium", "Medium"), ("low", "Low")):
        group = [f for f in findings if f.get("severity") == severity]
        if not group:
            continue
        lines.append(f"### {label} severity")
        for finding in group[:8]:
            cite = _finding_cite(context, finding)
            lines.append(
                f"- **{finding.get('title')}** — `{finding.get('file_path')}:"
                f"{finding.get('line')}` [{finding.get('confidence')}] {cite}"
            )
            lines.append(f"  - {finding.get('explanation')}")
            lines.append(f"  - Suggestion: {finding.get('suggestion')}")
        if len(group) > 8:
            lines.append(f"- …and {len(group) - 8} more {severity} finding(s).")
        lines.append("")

    lines.append(
        "These are deterministic pattern checks, not a full security audit. No code was "
        "modified and no exploit was attempted."
    )
    lines.extend(_warning_lines(context))
    return "\n".join(lines)


def _finding_cite(context: CopilotContext, finding: dict[str, Any]) -> str:
    for item in context.evidence:
        if item.kind != "finding":
            continue
        if (
            item.file_path == finding.get("file_path")
            and item.line_start == finding.get("line")
            and finding.get("title", "").lower() in item.title.lower()
        ):
            return f"[{item.id}]"
    item = _find_evidence(
        context, kind="finding", file_path=finding.get("file_path"), line=finding.get("line")
    )
    return f"[{item.id}]" if item else ""


def _debug(context: CopilotContext) -> str:
    lines = ["## Debug analysis", ""]
    traceback_items = [item for item in context.evidence if item.kind == "traceback"]
    if traceback_items:
        lines.append(
            "I mapped the supplied traceback to repository files and lines. This is a "
            "static inspection; it does not prove the root cause."
        )
        for item in traceback_items[:4]:
            lines.extend(
                [
                    "",
                    f"**Frame: {_cite(item)}**",
                    "```",
                    item.content,
                    "```",
                ]
            )
            dependency = _find_evidence(
                context, kind="dependency", file_path=item.file_path
            )
            if dependency:
                lines.append(f"Dependency context: [{dependency.id}]")
                lines.append(dependency.content)
            tests = [
                (mode, test)
                for mode, test in _selected_tests(context, limit=6)
                if test.get("file_path") == item.file_path
                or item.file_path in test.get("matched_files", [])
            ]
            if tests:
                lines.extend(["", "**Tests touching this file**"])
                for mode, test in tests[:5]:
                    lines.append(
                        f"- `{test.get('test_id')}` ({mode}) — "
                        f"{'; '.join(test.get('reasons', [])[:2])} — "
                        f"{_cite_for_file(context, str(test.get('file_path', '')))}"
                    )
        lines.extend(
            [
                "",
                "**Next steps**",
                "1. Confirm the failing frame and the values entering it; the traceback only "
                "shows where execution stopped.",
                "2. Inspect the cited dependency neighbourhood for callers/importers that "
                "may pass unexpected inputs.",
                "3. Run the tests cited above, then add a regression test that reproduces the "
                "reported failure.",
            ]
        )
    else:
        lines.append(
            "No parsable traceback frame was found in the question. Paste the full "
            "traceback (including `File \"...\", line N`) for a precise mapping."
        )
        file = _top_file(context)
        if file:
            lines.extend(
                [
                    "",
                    f"The most relevant retrieved file is {_cite(file)}. Its structure and "
                    "dependency context are included as evidence, but without an error line "
                    "I will not guess at a root cause.",
                ]
            )
        high = [item for item in context.evidence if item.kind == "finding" and item.title.startswith("HIGH")]
        if high:
            lines.extend(["", "**High-severity patterns in reviewed files**"])
            lines.extend(
                f"- {item.title} — {_cite(item)}" for item in high[:5]
            )

    tests = _selected_tests(context, limit=5)
    if tests:
        lines.extend(["", "**Tests to start with**"])
        for mode, test in tests[:5]:
            lines.append(
                f"- `{test.get('test_id')}` ({mode}) — "
                f"{'; '.join(test.get('reasons', [])[:2])}"
            )
    lines.extend(_warning_lines(context))
    return "\n".join(lines)


def _general(context: CopilotContext) -> str:
    lines = [
        "## Repository evidence",
        "",
        "I answered from the current scan and graph using deterministic retrieval and "
        "static analysis.",
        "",
    ]
    lines.extend(_summary_lines(context))
    if context.git_info.get("is_repository"):
        lines.append(
            f"- Git: **{context.git_info.get('commit_count', 0)}** commit(s), branch "
            f"`{context.git_info.get('current_branch')}`, dirty: "
            f"**{context.git_info.get('dirty')}**"
        )

    relevant = [
        item
        for item in context.evidence
        if item.kind in {"file", "symbol", "finding", "dependency"} and item.file_path
    ]
    if relevant:
        lines.extend(["", "**Most relevant evidence**"])
        for item in relevant[:8]:
            lines.append(f"- {item.title} — {_cite(item)}")
    else:
        lines.append(
            "\nI did not find a strong lexical match. Try naming a file, symbol, error "
            "message or Git ref."
        )

    lines.extend(
        [
            "",
            "**Questions with direct evidence paths**",
            "- `Explain app/services/analysis_service.py`",
            "- `What changed in the latest Git diff and what is affected?`",
            "- `Which tests should I run for this change?`",
            "- `Review this repository for security risks`",
        ]
    )
    lines.extend(_warning_lines(context))
    return "\n".join(lines)


# ── citation validation ────────────────────────────────────────


def strip_unknown_citations(answer: str, valid_ids: Iterable[str]) -> tuple[str, list[str]]:
    """Remove model citations that do not exist in the evidence bundle."""
    valid = set(valid_ids)
    warnings: list[str] = []
    seen_unknown: set[str] = set()
    import re

    def replace(match: re.Match[str]) -> str:
        identifier = match.group(1)
        if identifier in valid:
            return match.group(0)
        if identifier not in seen_unknown:
            seen_unknown.add(identifier)
            warnings.append(f"Removed citation to nonexistent evidence {identifier}.")
        return ""

    cleaned = re.sub(r"\[(E\d+)\]", replace, answer)
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    return cleaned.strip(), warnings
