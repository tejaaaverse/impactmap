"""Explainable impact analysis over the code dependency graph.

The engine starts from changed files/entities and walks *incoming* edges
(dependent -> dependency) to find code that depends on the change. Each hop is
scored with a transparent, multiplicative model, and every result carries the
shortest/highest-scoring dependency path and a human-readable reason.

These are risk estimates derived from static analysis, not predictions that a
test will fail.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings
from app.core.logging import logger
from app.engine.git.change_detector import ChangeSet, ChangedEntity
from app.engine.graph.code_graph import (
    CONTAINMENT_EDGE_TYPES,
    DEPENDENCY_EDGE_TYPES,
    EDGE_WEIGHTS,
    TYPE_IMPACT_FACTOR,
    CodeGraph,
)
from app.engine.parser.python_parser import file_path_to_module_name


@dataclass
class ImpactEntry:
    node_id: str
    name: str
    qualified_name: str
    type: str
    file_path: str
    line_start: int = 0
    line_end: int = 0
    impact_type: str = "indirect"  # direct | indirect
    score: float = 0.0
    depth: int = 0
    reason: str = ""
    path: list[dict[str, Any]] = field(default_factory=list)
    edge_types: list[str] = field(default_factory=list)
    confidence: float = 1.0
    is_deleted: bool = False
    is_test: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "name": self.name,
            "qualified_name": self.qualified_name,
            "type": self.type,
            "file_path": self.file_path,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "impact_type": self.impact_type,
            "score": round(self.score, 1),
            "depth": self.depth,
            "reason": self.reason,
            "path": self.path,
            "edge_types": self.edge_types,
            "confidence": round(self.confidence, 2),
            "is_deleted": self.is_deleted,
            "is_test": self.is_test,
        }


@dataclass
class ImpactResult:
    repo_path: str
    changed_files: list[dict[str, Any]] = field(default_factory=list)
    changed_entities: list[dict[str, Any]] = field(default_factory=list)
    direct: list[ImpactEntry] = field(default_factory=list)
    indirect: list[ImpactEntry] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    truncated: bool = False
    excluded_test_nodes: int = 0
    max_depth_reached: int = 0

    def to_dict(self) -> dict[str, Any]:
        affected_files = {
            entry.file_path for entry in self.direct + self.indirect if entry.file_path
        }
        by_type: dict[str, int] = {}
        for entry in self.direct + self.indirect:
            by_type[entry.type] = by_type.get(entry.type, 0) + 1
        return {
            "repo_path": self.repo_path,
            "changed_files": self.changed_files,
            "changed_entities": self.changed_entities,
            "direct_impacts": [e.to_dict() for e in self.direct],
            "indirect_impacts": [e.to_dict() for e in self.indirect],
            "summary": {
                "changed_file_count": len(self.changed_files),
                "changed_entity_count": len(self.changed_entities),
                "direct_count": len(self.direct),
                "indirect_count": len(self.indirect),
                "total_affected": len(self.direct) + len(self.indirect),
                "affected_file_count": len(affected_files),
                "max_depth": self.max_depth_reached,
                "by_type": by_type,
                "truncated": self.truncated,
                "excluded_test_nodes": self.excluded_test_nodes,
            },
            "warnings": self.warnings,
            "methodology": (
                "Reverse dependency traversal over statically resolved call, import, "
                "inheritance and containment edges. Scores decay per hop and are "
                "weighted by edge confidence. This is a risk signal, not a failure prediction."
            ),
        }


class ImpactAnalyzer:
    """Compute direct and transitive impact for a :class:`ChangeSet`."""

    def __init__(
        self,
        graph: CodeGraph,
        max_depth: int | None = None,
        max_nodes: int | None = None,
        include_tests: bool = False,
    ):
        self.graph = graph
        self.max_depth = max_depth or settings.ANALYSIS_MAX_DEPTH
        self.max_nodes = max_nodes or settings.ANALYSIS_MAX_NODES
        self.include_tests = include_tests
        self._truncated = False
        self._excluded_tests = 0

    def analyze(self, changeset: ChangeSet) -> ImpactResult:
        self._truncated = False
        self._excluded_tests = 0
        result = ImpactResult(
            repo_path=changeset.repo_path,
            changed_files=[f.to_dict() for f in changeset.files],
            changed_entities=[e.to_dict() for e in changeset.entities],
            warnings=list(changeset.warnings),
        )

        direct: dict[str, ImpactEntry] = {}
        seed_scores: dict[str, float] = {}

        # 1. File-level seeds.
        for file in changeset.files:
            node_id = f"file:{file.path}"
            if node_id in self.graph.graph:
                data = self.graph.graph.nodes[node_id]
                if data.get("is_test") and not self.include_tests:
                    continue
                direct[node_id] = self._direct_entry(
                    node_id,
                    data,
                    f"File was {file.change_type}; "
                    f"{file.added_line_count} line(s) added, "
                    f"{file.deleted_line_count} line(s) deleted.",
                )
                seed_scores[node_id] = 100.0
            else:
                direct[f"deleted:file:{file.path}"] = ImpactEntry(
                    node_id=f"deleted:file:{file.path}",
                    name=file.path,
                    qualified_name=file.path,
                    type="file",
                    file_path=file.path,
                    impact_type="direct",
                    score=100.0,
                    reason="File was deleted or renamed away.",
                    path=[
                        {
                            "id": f"deleted:file:{file.path}",
                            "name": file.path,
                            "type": "file",
                            "file_path": file.path,
                        }
                    ],
                    is_deleted=True,
                )

        # 2. Entity-level seeds.
        for entity in changeset.entities:
            node_id = self.graph.node_for_key(entity.key)
            if node_id and node_id in self.graph.graph:
                data = self.graph.graph.nodes[node_id]
                if data.get("is_test") and not self.include_tests:
                    continue
                direct[node_id] = self._direct_entry(
                    node_id,
                    data,
                    self._entity_reason(entity),
                )
                seed_scores[node_id] = 100.0
            else:
                entry = ImpactEntry(
                    node_id=f"deleted:{entity.key}",
                    name=entity.name,
                    qualified_name=entity.qualified_name,
                    type=entity.kind,
                    file_path=entity.file_path,
                    line_start=entity.line_start,
                    line_end=entity.line_end,
                    impact_type="direct",
                    score=100.0,
                    reason=(
                        f"Entity was {entity.change_type} and no longer exists in the "
                        "current graph."
                    ),
                    path=[
                        {
                            "id": f"deleted:{entity.key}",
                            "name": entity.name,
                            "type": entity.kind,
                            "file_path": entity.file_path,
                        }
                    ],
                    is_deleted=True,
                )
                direct[entry.node_id] = entry
                self._mark_callers_of_deleted(entry, direct)
                self._mark_importers_of_deleted_file(entity.file_path, direct)

        # 3. Deleted file importers.
        for file in changeset.files:
            if file.change_type == "deleted":
                self._mark_importers_of_deleted_file(file.path, direct)

        # 4. Reverse traversal from seeds.
        indirect = self._traverse(seed_scores, direct)

        result.direct = sorted(direct.values(), key=lambda e: (-e.score, e.file_path, e.name))
        result.indirect = sorted(
            indirect.values(), key=lambda e: (-e.score, e.depth, e.file_path, e.name)
        )
        result.max_depth_reached = max(
            [e.depth for e in result.direct + result.indirect] or [0]
        )
        result.truncated = self._truncated
        result.excluded_test_nodes = self._excluded_tests
        if result.truncated:
            result.warnings.append(
                f"Traversal stopped after {self.max_nodes} nodes; results are partial."
            )
        logger.info(
            "Impact analysis: %d direct, %d indirect, depth %d",
            len(result.direct),
            len(result.indirect),
            result.max_depth_reached,
        )
        return result

    # ── traversal ───────────────────────────────────────────────

    def _traverse(
        self, seed_scores: dict[str, float], direct: dict[str, ImpactEntry]
    ) -> dict[str, ImpactEntry]:
        affected: dict[str, ImpactEntry] = {}
        best: dict[str, float] = dict(seed_scores)
        # Max-priority queue via negative score.
        heap: list[tuple[float, int, str]] = [
            (-score, 0, node_id) for node_id, score in seed_scores.items()
        ]
        heapq.heapify(heap)
        expanded = 0

        while heap:
            neg_score, distance, node_id = heapq.heappop(heap)
            score = -neg_score
            if score < best.get(node_id, 0) - 1e-9:
                continue
            if distance >= self.max_depth:
                continue
            if expanded >= self.max_nodes:
                # Marking happens in the caller via property access below.
                self._truncated = True
                break
            if node_id not in self.graph.graph:
                continue
            expanded += 1
            current = self.graph.graph.nodes[node_id]

            for pred_id, _, edge in self.graph.graph.in_edges(node_id, data=True):
                pred = self.graph.graph.nodes[pred_id]
                if pred.get("type") == "module":
                    continue
                if pred.get("is_test") and not self.include_tests:
                    self._excluded_tests += 1
                    continue
                edge_type = edge.get("type", "import")
                if edge_type not in DEPENDENCY_EDGE_TYPES | CONTAINMENT_EDGE_TYPES:
                    continue

                confidence = float(edge.get("confidence", 0.85))
                base_weight = EDGE_WEIGHTS.get(edge_type, 0.5)
                confidence_factor = 0.65 + 0.35 * confidence
                hop_factor = 0.9
                fan_in = self.graph.graph.in_degree(pred_id)
                fan_in_factor = 1.0 + min(0.3, 0.1 * math.log1p(max(0, fan_in - 1)))
                type_factor = TYPE_IMPACT_FACTOR.get(pred.get("type"), 0.9)
                new_score = (
                    score
                    * base_weight
                    * confidence_factor
                    * hop_factor
                    * fan_in_factor
                    * type_factor
                )
                new_score = max(1.0, min(100.0, new_score))

                if new_score <= best.get(pred_id, 0) + 0.5:
                    continue
                best[pred_id] = new_score
                base_path = (
                    affected[node_id].path
                    if node_id in affected
                    else direct.get(node_id, ImpactEntry("", "", "", "", "")).path
                )
                if not base_path:
                    base_path = [self._node_ref(node_id)]
                path = base_path + [self._node_ref(pred_id)]
                reason = self._edge_reason(pred, current, edge_type, distance + 1)
                if edge_type == "contains":
                    reason = (
                        f"{pred['name']} contains {current['name']}, which is affected."
                    )
                entry = ImpactEntry(
                    node_id=pred_id,
                    name=pred.get("name", pred_id),
                    qualified_name=pred.get("qualified_name", pred_id),
                    type=pred.get("type", "unknown"),
                    file_path=pred.get("file_path", ""),
                    line_start=pred.get("line_start", 0),
                    line_end=pred.get("line_end", 0),
                    impact_type="indirect",
                    score=new_score,
                    depth=distance + 1,
                    reason=reason,
                    path=path,
                    edge_types=(affected[node_id].edge_types if node_id in affected else [])
                    + [edge_type],
                    confidence=confidence,
                    is_test=bool(pred.get("is_test")),
                )
                affected[pred_id] = entry
                heapq.heappush(heap, (-new_score, distance + 1, pred_id))

        return {
            node_id: entry
            for node_id, entry in affected.items()
            if node_id not in direct
        }

    def _node_ref(self, node_id: str) -> dict[str, Any]:
        data = self.graph.graph.nodes.get(node_id, {})
        return {
            "id": node_id,
            "name": data.get("name", node_id),
            "type": data.get("type", "unknown"),
            "file_path": data.get("file_path", ""),
            "is_test": bool(data.get("is_test")),
        }

    def _edge_reason(
        self, dependent: dict[str, Any], dependency: dict[str, Any], edge_type: str, depth: int
    ) -> str:
        dep_name = dependent.get("name", "component")
        target_name = dependency.get("name", "component")
        if edge_type == "call":
            return f"{dep_name} calls {target_name}, which is affected by the change."
        if edge_type in ("import", "import_symbol"):
            return f"{dep_name} imports {target_name}, which is affected by the change."
        if edge_type == "inherits":
            return f"{dep_name} inherits from {target_name}, which is affected."
        if edge_type == "contains":
            return f"{dep_name} contains {target_name}, which is affected."
        return (
            f"{dep_name} depends on {target_name}, which is {depth} hop(s) "
            "from the changed code."
        )

    # ── deleted-code fallbacks ──────────────────────────────────

    def _mark_callers_of_deleted(self, deleted: ImpactEntry, direct: dict[str, ImpactEntry]) -> None:
        short_name = deleted.name
        for node_id, data in self.graph.graph.nodes(data=True):
            if data.get("type") not in ("function", "method"):
                continue
            if data.get("is_test") and not self.include_tests:
                continue
            calls = data.get("metadata", {}).get("calls", [])
            if any(call.split(".")[-1] == short_name for call in calls):
                direct.setdefault(
                    node_id,
                    ImpactEntry(
                        node_id=node_id,
                        name=data.get("name", node_id),
                        qualified_name=data.get("qualified_name", node_id),
                        type=data.get("type", "function"),
                        file_path=data.get("file_path", ""),
                        line_start=data.get("line_start", 0),
                        line_end=data.get("line_end", 0),
                        impact_type="direct",
                        score=90.0,
                        reason=(
                            f"Calls deleted entity {deleted.qualified_name}; "
                            "the call site may now be broken."
                        ),
                        path=deleted.path + [self._node_ref(node_id)],
                        confidence=0.6,
                    ),
                )

    def _mark_importers_of_deleted_file(
        self, file_path: str, direct: dict[str, ImpactEntry]
    ) -> None:
        module_name = file_path_to_module_name(file_path, "")
        if not module_name:
            return
        for node_id, data in self.graph.graph.nodes(data=True):
            if data.get("type") != "file":
                continue
            if data.get("is_test") and not self.include_tests:
                continue
            imports = data.get("metadata", {}).get("imports", [])
            for imp in imports:
                target = imp.get("module", "")
                matches = (
                    target == module_name
                    or target.startswith(module_name + ".")
                    or module_name.endswith("." + target)
                )
                if not matches:
                    continue
                direct.setdefault(
                    node_id,
                    ImpactEntry(
                        node_id=node_id,
                        name=data.get("name", node_id),
                        qualified_name=data.get("qualified_name", node_id),
                        type="file",
                        file_path=data.get("file_path", ""),
                        line_start=data.get("line_start", 0),
                        line_end=data.get("line_end", 0),
                        impact_type="direct",
                        score=95.0,
                        reason=(
                            f"Imports deleted module {module_name}; "
                            "the import may now fail."
                        ),
                        path=[
                            {
                                "id": f"deleted:file:{file_path}",
                                "name": file_path,
                                "type": "file",
                                "file_path": file_path,
                            },
                            self._node_ref(node_id),
                        ],
                        confidence=0.9,
                    ),
                )

    def _direct_entry(
        self, node_id: str, data: dict[str, Any], reason: str
    ) -> ImpactEntry:
        return ImpactEntry(
            node_id=node_id,
            name=data.get("name", node_id),
            qualified_name=data.get("qualified_name", node_id),
            type=data.get("type", "unknown"),
            file_path=data.get("file_path", ""),
            line_start=data.get("line_start", 0),
            line_end=data.get("line_end", 0),
            impact_type="direct",
            score=100.0,
            depth=0,
            reason=reason,
            path=[self._node_ref(node_id)],
            confidence=1.0,
            is_test=bool(data.get("is_test")),
        )

    @staticmethod
    def _entity_reason(entity: ChangedEntity) -> str:
        verb = {
            "added": "was added",
            "modified": "was modified",
            "deleted": "was deleted",
        }.get(entity.change_type, "changed")
        return (
            f"{entity.kind.capitalize()} {entity.qualified_name} {verb} "
            f"(lines {entity.line_start}-{entity.line_end})."
        )
