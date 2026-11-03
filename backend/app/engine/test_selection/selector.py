"""Intelligent test selection with coverage-first and static fallbacks."""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field
from typing import Any, Iterable

from app.core.logging import logger
from app.engine.git.change_detector import ChangeSet
from app.engine.graph.code_graph import CodeGraph, is_test_path
from app.engine.impact.impact_analyzer import ImpactEntry, ImpactResult
from app.engine.test_selection.discovery import TestCase


@dataclass
class SelectedTest:
    test_id: str
    file_path: str
    name: str
    class_name: str | None
    score: float
    reasons: list[str] = field(default_factory=list)
    matched_direct: list[str] = field(default_factory=list)
    matched_indirect: list[str] = field(default_factory=list)
    matched_files: list[str] = field(default_factory=list)
    source: str = "coverage"  # coverage | static | changed_test | conservative | historical
    previously_failed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "test_id": self.test_id,
            "file_path": self.file_path,
            "name": self.name,
            "class_name": self.class_name,
            "score": round(self.score, 1),
            "reasons": self.reasons,
            "matched_direct": self.matched_direct,
            "matched_indirect": self.matched_indirect,
            "matched_files": self.matched_files,
            "source": self.source,
            "previously_failed": self.previously_failed,
        }


@dataclass
class ModeSelection:
    mode: str
    selected: list[SelectedTest]
    total_tests: int
    reduction_percent: float
    fallback_used: bool
    warnings: list[str] = field(default_factory=list)
    rationale: str = ""

    @property
    def selected_count(self) -> int:
        return len(self.selected)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "selected_tests": [t.to_dict() for t in self.selected],
            "selected_count": len(self.selected),
            "total_tests": self.total_tests,
            "reduction_percent": round(self.reduction_percent, 1),
            "fallback_used": self.fallback_used,
            "warnings": self.warnings,
            "rationale": self.rationale,
        }


@dataclass
class SelectionResult:
    coverage_available: bool
    total_tests_discovered: int
    measured_tests: int = 0
    coverage_collected_at: str | None = None
    safe: ModeSelection | None = None
    optimized: ModeSelection | None = None
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "coverage_available": self.coverage_available,
            "total_tests_discovered": self.total_tests_discovered,
            "measured_tests": self.measured_tests,
            "coverage_collected_at": self.coverage_collected_at,
            "safe": self.safe.to_dict() if self.safe else None,
            "optimized": self.optimized.to_dict() if self.optimized else None,
            "warnings": self.warnings,
            "notes": self.notes,
        }


class TestSelector:
    """Not a pytest test class; disables accidental collection."""

    __test__ = False

    """Rank tests using coverage contexts, dependency paths and history."""

    def __init__(
        self,
        graph: CodeGraph,
        changeset: ChangeSet,
        impact: ImpactResult,
        tests: list[TestCase],
        coverage_data: dict[str, Any] | None,
        historical_failures: Iterable[str] | None = None,
    ):
        self.graph = graph
        self.changeset = changeset
        self.impact = impact
        self.tests = tests
        self.coverage = coverage_data
        self.historical = {self._normalize(t) for t in (historical_failures or [])}

        self.changed_files = {f.path for f in changeset.files}
        self.affected_files = {
            e.file_path for e in impact.direct + impact.indirect if e.file_path
        } | self.changed_files
        self.direct_ids = {e.node_id for e in impact.direct}
        self.indirect_ids = {e.node_id for e in impact.indirect}
        self.affected_ids = self.direct_ids | self.indirect_ids

        self._build_entity_index()
        self._build_coverage_maps()
        self._build_candidates()
        self._build_static_matches()

    # ── indexes ─────────────────────────────────────────────────

    def _build_entity_index(self) -> None:
        self.entities_by_file: dict[str, list[dict[str, Any]]] = {}
        for node_id, data in self.graph.graph.nodes(data=True):
            if data.get("type") not in ("function", "method") or data.get("is_test"):
                continue
            self.entities_by_file.setdefault(data["file_path"], []).append(
                {
                    "id": node_id,
                    "name": data.get("name", node_id),
                    "qualified_name": data.get("qualified_name", node_id),
                    "line_start": data.get("line_start", 0),
                    "line_end": data.get("line_end", 0),
                }
            )
        for entries in self.entities_by_file.values():
            entries.sort(key=lambda e: e["line_start"])
        self._starts = {
            file: [e["line_start"] for e in entries]
            for file, entries in self.entities_by_file.items()
        }
        self._names = {
            node_id: data.get("qualified_name", node_id)
            for node_id, data in self.graph.graph.nodes(data=True)
        }

    def _entity_for_line(self, file_path: str, line: int) -> dict[str, Any] | None:
        entries = self.entities_by_file.get(file_path)
        if not entries:
            return None
        starts = self._starts[file_path]
        index = bisect_right(starts, line) - 1
        # Entities can have decorators above line_start, but non-overlapping
        # function spans mean the nearest preceding span is sufficient.
        if index >= 0:
            entity = entries[index]
            if entity["line_start"] <= line <= entity["line_end"]:
                return entity
        return None

    def _build_coverage_maps(self) -> None:
        self.test_to_entities: dict[str, set[str]] = {}
        self.test_to_files: dict[str, set[str]] = {}
        self.file_entities: dict[str, set[str]] = {}
        self.coverage_tests: list[str] = []
        if not self.coverage or not self.coverage.get("contexts_available"):
            return
        tests = self.coverage.get("tests", [])
        self.coverage_tests = list(tests)
        for file_path, payload in (self.coverage.get("files") or {}).items():
            file_entities: set[str] = set()
            for line_str, indexes in (payload.get("lines") or {}).items():
                try:
                    line = int(line_str)
                except ValueError:
                    continue
                entity = self._entity_for_line(file_path, line)
                if not entity:
                    continue
                file_entities.add(entity["id"])
                for idx in indexes:
                    if 0 <= idx < len(tests):
                        test_id = tests[idx]
                        self.test_to_entities.setdefault(test_id, set()).add(entity["id"])
                        self.test_to_files.setdefault(test_id, set()).add(file_path)
            if file_entities:
                self.file_entities[file_path] = file_entities
            # Executed files without entity context still matter for file-level
            # coverage signals (module top-level code).
            for idx in payload.get("test_indexes", []):
                if 0 <= idx < len(tests):
                    self.test_to_files.setdefault(tests[idx], set()).add(file_path)

    def _build_candidates(self) -> None:
        discovered = {case.node_id: case for case in self.tests}
        normalized_discovered = {case.normalized_id: case for case in self.tests}
        candidates: dict[str, TestCase] = {}

        if self.coverage_tests:
            for raw_id in self.coverage_tests:
                base = normalized_discovered.get(self._normalize(raw_id))
                if base:
                    candidates[raw_id] = TestCase(
                        node_id=raw_id,
                        file_path=base.file_path,
                        name=base.name,
                        class_name=base.class_name,
                        line_start=base.line_start,
                        line_end=base.line_end,
                        module_name=base.module_name,
                    )
                else:
                    candidates[raw_id] = self._derive_case(raw_id)
            # Include discovered tests that coverage did not execute (skipped,
            # for example) so broad modes can still consider them.
            covered_norm = {self._normalize(t) for t in self.coverage_tests}
            for node_id, case in discovered.items():
                if case.normalized_id not in covered_norm:
                    candidates[node_id] = case
        else:
            candidates.update(discovered)

        self.candidates = candidates
        self.total_tests = len(candidates)

    def _derive_case(self, test_id: str) -> TestCase:
        parts = test_id.split("::")
        file_path = parts[0].replace("\\", "/")
        name = self._normalize(test_id).split("::")[-1]
        class_name = parts[1] if len(parts) >= 3 else None
        return TestCase(
            node_id=test_id,
            file_path=file_path,
            name=name,
            class_name=class_name,
        )

    def _build_static_matches(self) -> None:
        self.static_matches: dict[str, list[str]] = {}
        if not self.affected_ids:
            return
        for test_id, case in self.candidates.items():
            nodes = []
            qname = f"{case.module_name}.{case.name}" if case.module_name else case.name
            if case.class_name:
                full = (
                    f"{case.module_name}.{case.class_name}.{case.name}"
                    if case.module_name
                    else f"{case.class_name}.{case.name}"
                )
                nodes.append(f"method:{case.file_path}::{full}")
            else:
                # Graph function node IDs use the ``func:`` prefix (see
                # GraphBuilder); using ``function:`` here silently misses the
                # start node and falls back to file-level import edges.
                nodes.append(f"func:{case.file_path}::{qname}")
            file_node = f"file:{case.file_path}"
            matched = self._reachable_affected(nodes, file_node)
            if matched:
                self.static_matches[test_id] = matched

    def _reachable_affected(self, start_nodes: list[str], file_node: str) -> list[str]:
        matched: set[str] = set()
        queue: list[tuple[str, int]] = []
        seen: set[str] = set()
        for node in start_nodes:
            if node in self.graph.graph:
                queue.append((node, 0))
        if not queue and file_node in self.graph.graph:
            queue.append((file_node, 0))
        while queue:
            node_id, depth = queue.pop(0)
            if node_id in seen or depth > 4:
                continue
            seen.add(node_id)
            if node_id in self.affected_ids:
                matched.add(self._names.get(node_id, node_id))
            for _, target in self.graph.graph.out_edges(node_id):
                if target not in seen:
                    queue.append((target, depth + 1))
        return sorted(matched)

    # ── scoring / selection ─────────────────────────────────────

    def select(self) -> SelectionResult:
        coverage_available = bool(
            self.coverage
            and self.coverage.get("contexts_available")
            and self.coverage.get("files")
            and self.coverage_tests
        )
        warnings: list[str] = []
        if not coverage_available:
            warnings.append(
                "Per-test coverage is unavailable. Selection relies on static "
                "dependency evidence and is explicitly incomplete."
            )
        if not self.total_tests:
            warnings.append("No pytest tests were discovered in this repository.")

        scored = {
            test_id: self._score_test(test_id, case)
            for test_id, case in self.candidates.items()
        }

        safe = self._select_mode("safe", scored, coverage_available)
        optimized = self._select_mode("optimized", scored, coverage_available)

        result = SelectionResult(
            coverage_available=coverage_available,
            total_tests_discovered=self.total_tests,
            measured_tests=len(self.coverage_tests),
            coverage_collected_at=(self.coverage or {}).get("collected_at"),
            safe=safe,
            optimized=optimized,
            warnings=warnings,
            notes=[
                "Safe mode favours recall and includes static or conservative "
                "fallbacks when coverage evidence is missing.",
                "Optimized mode keeps tests with direct coverage or strong "
                "dependency evidence and may miss regressions not represented "
                "in the coverage snapshot.",
                "Scores are ranking heuristics; they are not failure probabilities.",
            ],
        )
        logger.info(
            "Test selection: %d tests, safe=%d, optimized=%d, coverage=%s",
            self.total_tests,
            len(safe.selected),
            len(optimized.selected),
            coverage_available,
        )
        return result

    def _score_test(self, test_id: str, case: TestCase) -> SelectedTest:
        covered = self.test_to_entities.get(test_id, set())
        covered_files = self.test_to_files.get(test_id, set())
        direct_matches = sorted(
            self._names.get(e, e) for e in covered if e in self.direct_ids
        )
        indirect_matches = sorted(
            self._names.get(e, e) for e in covered if e in self.indirect_ids
        )
        file_matches = sorted(
            f for f in covered_files if f in self.affected_files
        )
        direct_file_matches = sorted(
            f for f in covered_files if f in self.changed_files
        )
        static_matches = self.static_matches.get(test_id, [])
        changed_test = case.file_path in self.changed_files and is_test_path(case.file_path)
        previously_failed = self._normalize(test_id) in self.historical

        score = 0.0
        reasons: list[str] = []
        sources: list[str] = []
        if direct_matches:
            score += min(36.0, 12.0 * len(direct_matches))
            reasons.append(
                "Covers changed code: " + ", ".join(direct_matches[:3])
                + ("…" if len(direct_matches) > 3 else "")
            )
            sources.append("coverage")
        if indirect_matches:
            score += min(25.0, 5.0 * len(indirect_matches))
            reasons.append(
                "Covers affected dependency: " + ", ".join(indirect_matches[:3])
                + ("…" if len(indirect_matches) > 3 else "")
            )
            sources.append("coverage")
        if direct_file_matches:
            score += min(10.0, 2.0 * len(direct_file_matches))
            reasons.append(
                "Executes code in changed file: " + ", ".join(direct_file_matches[:3])
            )
            sources.append("coverage")
        elif file_matches:
            score += min(4.0, 1.0 * len(file_matches))
            reasons.append(
                "Executes code in an affected file: " + ", ".join(file_matches[:3])
            )
            sources.append("coverage")
        if static_matches:
            score += min(8.0, 2.0 * len(static_matches))
            reasons.append(
                "Statically reaches affected code: " + ", ".join(static_matches[:3])
                + ("…" if len(static_matches) > 3 else "")
            )
            sources.append("static")
        if changed_test:
            score += 6.0
            reasons.append("The test file itself changed.")
            sources.append("changed_test")
        if previously_failed:
            score += 8.0
            reasons.append("Failed in the most recent recorded test run.")
            sources.append("historical")

        if not reasons:
            reasons.append(
                "Selected by conservative fallback; no specific coverage or "
                "dependency link was found."
            )
            sources.append("conservative")

        return SelectedTest(
            test_id=test_id,
            file_path=case.file_path,
            name=case.name,
            class_name=case.class_name,
            score=score,
            reasons=reasons,
            matched_direct=direct_matches,
            matched_indirect=indirect_matches,
            matched_files=file_matches,
            source=sources[0] if sources else "conservative",
            previously_failed=previously_failed,
        )

    def _select_mode(
        self,
        mode: str,
        scored: dict[str, SelectedTest],
        coverage_available: bool,
    ) -> ModeSelection:
        mode_warnings: list[str] = []
        selected: list[SelectedTest] = []
        fallback_used = False

        if not scored:
            return ModeSelection(
                mode=mode,
                selected=[],
                total_tests=0,
                reduction_percent=0.0,
                fallback_used=False,
                warnings=["No tests available for selection."],
                rationale="No tests discovered.",
            )

        if not coverage_available:
            if mode == "safe":
                selected = list(scored.values())
                fallback_used = True
                mode_warnings.append(
                    "Safe mode selected the complete discovered suite because "
                    "per-test coverage is unavailable."
                )
                rationale = (
                    "Conservative full-suite fallback: without coverage evidence "
                    "no test can be safely excluded."
                )
            else:
                selected = [
                    test
                    for test in scored.values()
                    if test.source in ("static", "changed_test") or test.previously_failed
                ]
                if not selected:
                    selected = list(scored.values())
                    fallback_used = True
                    mode_warnings.append(
                        "No static dependency evidence linked tests to the change; "
                        "optimized mode fell back to the complete suite."
                    )
                else:
                    mode_warnings.append(
                        "Optimized mode used static dependency evidence only; "
                        "this can miss dynamic behaviour."
                    )
                rationale = (
                    "Static dependency fallback: tests that reach affected code "
                    "through resolvable imports/calls, plus changed or previously "
                    "failing tests."
                )
            return self._mode_result(mode, selected, fallback_used, mode_warnings, rationale)

        # Coverage-backed selection.
        if mode == "safe":
            selected = [
                test
                for test in scored.values()
                if test.matched_direct
                or test.matched_indirect
                or test.matched_files
                or test.source in ("static", "changed_test")
                or test.previously_failed
            ]
            if not selected and self.changed_files:
                selected = list(scored.values())
                fallback_used = True
                mode_warnings.append(
                    "No coverage or static link was found for the changed code; "
                    "safe mode fell back to the complete suite."
                )
            rationale = (
                "Coverage-backed safe selection: every test covering changed or "
                "affected code, plus statically reachable, changed, or previously "
                "failing tests."
            )
        else:
            selected = [
                test
                for test in scored.values()
                if test.matched_direct
                or test.source == "changed_test"
                or (
                    test.matched_direct
                    and test.matched_files
                )
                or (
                    test.matched_indirect
                    and (test.score >= 10 or test.previously_failed)
                )
                or (
                    test.previously_failed
                    and (test.matched_files or test.matched_indirect)
                )
            ]
            if not selected and self.changed_files:
                # Do not silently return an empty suite. Prefer static evidence,
                # then a full-suite fallback with an explicit warning.
                static = [
                    test
                    for test in scored.values()
                    if test.source in ("static", "changed_test")
                ]
                if static:
                    selected = static
                    mode_warnings.append(
                        "Coverage did not map to affected entities; optimized mode "
                        "used static dependency evidence."
                    )
                else:
                    selected = list(scored.values())
                    fallback_used = True
                    mode_warnings.append(
                        "No coverage or static evidence linked tests to the change; "
                        "optimized mode fell back to the complete suite."
                    )
            rationale = (
                "Coverage-backed optimized selection: tests covering changed "
                "entities or strong affected-dependency coverage, plus changed "
                "or historically failing tests."
            )

        return self._mode_result(mode, selected, fallback_used, mode_warnings, rationale)

    def _mode_result(
        self,
        mode: str,
        selected: list[SelectedTest],
        fallback_used: bool,
        warnings: list[str],
        rationale: str,
    ) -> ModeSelection:
        # Deduplicate by test id, rank by score then id.
        unique = {test.test_id: test for test in selected}
        ordered = sorted(unique.values(), key=lambda t: (-t.score, t.test_id))
        total = max(self.total_tests, len(ordered))
        reduction = (1 - len(ordered) / total) * 100 if total else 0.0
        return ModeSelection(
            mode=mode,
            selected=ordered,
            total_tests=total,
            reduction_percent=max(0.0, reduction),
            fallback_used=fallback_used,
            warnings=warnings,
            rationale=rationale,
        )

    @staticmethod
    def _normalize(test_id: str) -> str:
        return test_id.split("[", 1)[0]

    # ── benchmark helper ────────────────────────────────────────

    def coverage_precision_recall(
        self, selected_test_ids: list[str]
    ) -> tuple[float | None, float | None]:
        """Measure selection precision/recall against full-suite coverage.

        Recall is the fraction of affected entities covered by the complete
        suite that the selected tests also cover. Precision is the fraction of
        selected tests that cover at least one affected entity. This is a
        coverage-based measurement, not a fault-detection score.
        """
        if not self.coverage_tests:
            return None, None
        affected_entities = {
            entity_id
            for entity_ids in self.file_entities.values()
            for entity_id in entity_ids
        } & (self.direct_ids | self.indirect_ids)
        covered_by_full: set[str] = set()
        for test_id in self.coverage_tests:
            covered_by_full.update(self.test_to_entities.get(test_id, set()))
        covered_by_full &= affected_entities

        covered_by_selected: set[str] = set()
        relevant_selected = 0
        for test_id in selected_test_ids:
            covered = self.test_to_entities.get(test_id, set())
            if covered & affected_entities:
                relevant_selected += 1
            covered_by_selected.update(covered)
        covered_by_selected &= affected_entities

        recall = (
            len(covered_by_selected) / len(covered_by_full)
            if covered_by_full
            else None
        )
        precision = (
            relevant_selected / len(selected_test_ids)
            if selected_test_ids
            else None
        )
        return precision, recall


def test_ids_for_mode(result: SelectionResult, mode: str) -> list[str]:
    selection = result.safe if mode == "safe" else result.optimized
    return [t.test_id for t in selection.selected] if selection else []
