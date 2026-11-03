"""In-memory directed code graph.

Nodes are files/packages and the Python entities they define. Edges point in
the direction of the dependency (dependent -> dependency), e.g. a caller has a
``call`` edge to the function it invokes. Reverse traversal therefore answers
"what depends on this changed code?".

Static analysis is deliberately conservative. Dynamic imports, reflection,
metaclasses, and dynamic dispatch are not resolved; any resolved edge carries a
confidence value so consumers can distinguish direct evidence from inference.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any, Iterable

import networkx as nx

from app.engine.parser.python_parser import (
    ClassInfo,
    ImportInfo,
    ModuleParseResult,
    file_path_to_module_name,
)
from app.engine.scanner.repository_scanner import RepositoryScanResult
from app.core.logging import logger


DEPENDENCY_EDGE_TYPES = {"import", "import_symbol", "call", "inherits"}
CONTAINMENT_EDGE_TYPES = {"contains"}

EDGE_WEIGHTS = {
    "call": 1.0,
    "inherits": 0.9,
    "import_symbol": 0.7,
    "import": 0.55,
    "contains": 0.35,
}

TYPE_IMPACT_FACTOR = {
    "function": 1.0,
    "method": 1.0,
    "class": 0.95,
    "file": 0.88,
    "module": 0.6,
}


@dataclass
class GraphNode:
    """A typed node in the code dependency graph."""

    id: str
    name: str
    qualified_name: str
    type: str
    file_path: str
    line_start: int = 0
    line_end: int = 0
    module_name: str = ""
    is_test: bool = False
    parent_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> str:
        """Stable cross-revision identity used for change matching."""
        return f"{self.type}:{self.qualified_name}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "qualified_name": self.qualified_name,
            "type": self.type,
            "file_path": self.file_path,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "module_name": self.module_name,
            "is_test": self.is_test,
            "parent_id": self.parent_id,
            "key": self.key,
            "metadata": self.metadata,
        }


@dataclass
class GraphEdge:
    """A directed dependency edge."""

    source: str
    target: str
    type: str
    line: int = 0
    confidence: float = 0.9
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "type": self.type,
            "line": self.line,
            "confidence": self.confidence,
            "reason": self.reason,
        }


class CodeGraph:
    """Wrapper around a NetworkX directed graph with lookup helpers."""

    def __init__(self, repo_path: str):
        self.repo_path = repo_path
        self.graph: nx.DiGraph = nx.DiGraph()
        self.by_key: dict[str, str] = {}
        self.module_files: dict[str, str] = {}
        self.warnings: list[str] = []
        self.unresolved_imports: list[dict[str, Any]] = []

    # ── construction ─────────────────────────────────────────────

    def add_node(self, node: GraphNode) -> None:
        if node.id in self.graph:
            return
        self.graph.add_node(node.id, **node.to_dict())
        self.by_key.setdefault(node.key, node.id)

    def add_edge(self, edge: GraphEdge) -> None:
        if edge.source not in self.graph or edge.target not in self.graph:
            return
        if edge.source == edge.target:
            return
        if self.graph.has_edge(edge.source, edge.target):
            existing = self.graph[edge.source][edge.target]
            types = existing.setdefault("types", [existing["type"]])
            if edge.type not in types:
                types.append(edge.type)
            if EDGE_WEIGHTS.get(edge.type, 0) > EDGE_WEIGHTS.get(existing["type"], 0):
                existing["type"] = edge.type
                existing["reason"] = edge.reason
                existing["line"] = edge.line or existing.get("line", 0)
            existing["confidence"] = max(existing.get("confidence", 0), edge.confidence)
            return
        self.graph.add_edge(
            edge.source,
            edge.target,
            source=edge.source,
            target=edge.target,
            type=edge.type,
            types=[edge.type],
            line=edge.line,
            confidence=edge.confidence,
            reason=edge.reason,
        )

    # ── query helpers ────────────────────────────────────────────

    def node(self, node_id: str) -> dict[str, Any] | None:
        return self.graph.nodes.get(node_id)

    def node_for_key(self, key: str) -> str | None:
        return self.by_key.get(key)

    def dependencies(self, node_id: str) -> list[dict[str, Any]]:
        """Nodes that this node directly depends on (outgoing edges)."""
        return [
            {**data, "source": node_id, "target": target}
            for _, target, data in self.graph.out_edges(node_id, data=True)
        ]

    def dependents(self, node_id: str) -> list[dict[str, Any]]:
        """Nodes that directly depend on this node (incoming edges)."""
        return [
            {**data, "source": source, "target": node_id}
            for source, _, data in self.graph.in_edges(node_id, data=True)
        ]

    def dependency_edges(self) -> Iterable[tuple[str, str, dict[str, Any]]]:
        for source, target, data in self.graph.edges(data=True):
            if data.get("type") in DEPENDENCY_EDGE_TYPES:
                yield source, target, data

    def stats(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        test_nodes = 0
        for _, data in self.graph.nodes(data=True):
            counts[data["type"]] = counts.get(data["type"], 0) + 1
            test_nodes += int(bool(data.get("is_test")))
        edge_counts: dict[str, int] = {}
        for _, _, data in self.graph.edges(data=True):
            for edge_type in data.get("types", [data.get("type")]):
                edge_counts[edge_type] = edge_counts.get(edge_type, 0) + 1
        return {
            "nodes": self.graph.number_of_nodes(),
            "edges": self.graph.number_of_edges(),
            "node_types": counts,
            "edge_types": edge_counts,
            "test_nodes": test_nodes,
            "unresolved_imports": len(self.unresolved_imports),
        }

    def to_dict(self, include_tests: bool = True, include_modules: bool = True) -> dict[str, Any]:
        def visible(node_id: str, data: dict[str, Any]) -> bool:
            if not include_tests and data.get("is_test"):
                return False
            if not include_modules and data.get("type") == "module":
                return False
            return True

        nodes = [
            data
            for node_id, data in self.graph.nodes(data=True)
            if visible(node_id, data)
        ]
        node_ids = {n["id"] for n in nodes}
        edges = [
            data
            for _, _, data in self.graph.edges(data=True)
            if data["source"] in node_ids and data["target"] in node_ids
        ]
        return {
            "repo_path": self.repo_path,
            "nodes": sorted(nodes, key=lambda n: (n["type"], n["file_path"], n["name"])),
            "edges": sorted(edges, key=lambda e: (e["source"], e["target"], e["type"])),
            "stats": self.stats(),
            "warnings": self.warnings,
            "unresolved_imports": self.unresolved_imports[:100],
        }


class GraphBuilder:
    """Build a :class:`CodeGraph` from a repository scan."""

    def build(self, scan: RepositoryScanResult) -> CodeGraph:
        graph = CodeGraph(scan.repo_path)
        # Keep files that failed to parse as file nodes. Hiding them made a
        # syntax-broken module silently disappear from the graph, which made
        # impact analysis look incomplete with no explanation.
        modules = list(scan.modules)
        module_by_name: dict[str, ModuleParseResult] = {}
        file_is_init: dict[str, bool] = {}

        for module in modules:
            if module.parse_errors:
                graph.warnings.append(
                    f"{module.file_path} could not be fully parsed: "
                    + "; ".join(module.parse_errors)
                )
            module_by_name[module.module_name] = module
            file_is_init[module.file_path] = PurePosixPath(
                module.file_path.replace("\\", "/")
            ).name == "__init__.py"

        # ── packages (module nodes) ─────────────────────────────
        package_dirs: set[str] = set()
        for module in modules:
            rel = PurePosixPath(module.file_path.replace("\\", "/"))
            for parent in rel.parents:
                if str(parent) in ("", "."):
                    continue
                package_dirs.add(str(parent))

        for package in sorted(package_dirs):
            module_name = package.replace("/", ".")
            graph.add_node(
                GraphNode(
                    id=f"module:{package}",
                    name=package.split("/")[-1],
                    qualified_name=module_name,
                    type="module",
                    file_path=package,
                    module_name=module_name,
                    metadata={"package": True},
                )
            )

        # ── files + defined entities ────────────────────────────
        entity_ids_by_module_name: dict[str, dict[str, str]] = {}
        methods_by_class: dict[str, dict[str, str]] = {}
        class_bases: list[tuple[str, str, int, list[str]]] = []

        for module in modules:
            file_id = f"file:{module.file_path}"
            is_test = is_test_path(module.file_path)
            graph.add_node(
                GraphNode(
                    id=file_id,
                    name=PurePosixPath(module.file_path).name,
                    qualified_name=module.module_name or module.file_path,
                    type="file",
                    file_path=module.file_path,
                    line_start=1,
                    line_end=module.line_count,
                    module_name=module.module_name,
                    is_test=is_test,
                    metadata={
                        "imports": [self._import_dict(i) for i in module.imports],
                        "parse_errors": module.parse_errors,
                        "relative_path": module.file_path,
                    },
                )
            )
            if module.module_name:
                graph.module_files.setdefault(module.module_name, file_id)
            entity_ids_by_module_name.setdefault(module.module_name, {})

            package_id = self._package_for(module.file_path, package_dirs)
            if package_id:
                graph.add_edge(
                    GraphEdge(package_id, file_id, "contains", line=1, confidence=1.0,
                              reason="Package contains module")
                )

            for func in module.functions:
                node_id = f"func:{module.file_path}::{func.qualified_name}"
                graph.add_node(
                    GraphNode(
                        id=node_id,
                        name=func.name,
                        qualified_name=func.qualified_name,
                        type="function",
                        file_path=module.file_path,
                        line_start=func.line_start,
                        line_end=func.line_end,
                        module_name=module.module_name,
                        is_test=is_test,
                        parent_id=file_id,
                        metadata={
                            "calls": func.calls,
                            "decorators": func.decorators,
                            "args": func.args,
                            "is_async": func.is_async,
                            "docstring": func.docstring,
                        },
                    )
                )
                entity_ids_by_module_name[module.module_name][func.name] = node_id
                graph.add_edge(
                    GraphEdge(file_id, node_id, "contains", line=func.line_start,
                              confidence=1.0, reason="File defines function")
                )

            for cls in module.classes:
                class_id = f"class:{module.file_path}::{cls.qualified_name}"
                graph.add_node(
                    GraphNode(
                        id=class_id,
                        name=cls.name,
                        qualified_name=cls.qualified_name,
                        type="class",
                        file_path=module.file_path,
                        line_start=cls.line_start,
                        line_end=cls.line_end,
                        module_name=module.module_name,
                        is_test=is_test,
                        parent_id=file_id,
                        metadata={
                            "bases": cls.bases,
                            "decorators": cls.decorators,
                            "docstring": cls.docstring,
                        },
                    )
                )
                entity_ids_by_module_name[module.module_name][cls.name] = class_id
                graph.add_edge(
                    GraphEdge(file_id, class_id, "contains", line=cls.line_start,
                              confidence=1.0, reason="File defines class")
                )
                class_bases.append((class_id, module.module_name, cls.line_start, cls.bases))
                methods_by_class[class_id] = {}

                for method in cls.methods:
                    method_id = f"method:{module.file_path}::{method.qualified_name}"
                    graph.add_node(
                        GraphNode(
                            id=method_id,
                            name=method.name,
                            qualified_name=method.qualified_name,
                            type="method",
                            file_path=module.file_path,
                            line_start=method.line_start,
                            line_end=method.line_end,
                            module_name=module.module_name,
                            is_test=is_test,
                            parent_id=class_id,
                            metadata={
                                "calls": method.calls,
                                "decorators": method.decorators,
                                "args": method.args,
                                "is_async": method.is_async,
                                "docstring": method.docstring,
                                "class_qualified_name": cls.qualified_name,
                            },
                        )
                    )
                    methods_by_class[class_id][method.name] = method_id
                    graph.add_edge(
                        GraphEdge(class_id, method_id, "contains", line=method.line_start,
                                  confidence=1.0, reason="Class defines method")
                    )

        # ── imports ─────────────────────────────────────────────
        for module in modules:
            file_id = f"file:{module.file_path}"
            aliases: dict[str, tuple[str, str | None]] = {}
            for imp in module.imports:
                resolved_module = resolve_relative_module(
                    module.module_name,
                    file_is_init.get(module.file_path, False),
                    imp,
                )
                if imp.name == "*":
                    graph.warnings.append(
                        f"Star import not expanded in {module.file_path}:{imp.line_number}"
                    )
                    continue

                local_name = imp.alias or (imp.name if imp.is_from_import else resolved_module.split(".")[0])
                if imp.is_from_import and imp.name:
                    aliases[local_name] = (resolved_module, imp.name)
                else:
                    aliases[local_name] = (resolved_module, None)

                targets = self._resolve_import_targets(
                    graph, module_by_name, entity_ids_by_module_name,
                    resolved_module, imp,
                )
                if not targets:
                    graph.unresolved_imports.append(
                        {
                            "file_path": module.file_path,
                            "line": imp.line_number,
                            "module": imp.module,
                            "name": imp.name,
                            "reason": "No internal module or entity matched",
                        }
                    )
                    continue
                for target, edge_type, reason in targets:
                    graph.add_edge(
                        GraphEdge(file_id, target, edge_type, line=imp.line_number,
                                  confidence=0.95, reason=reason)
                    )
            # cache aliases for call resolution below
            graph.graph.nodes[file_id]["metadata"]["aliases"] = {
                k: {"module": v[0], "symbol": v[1]} for k, v in aliases.items()
            }

        # ── inheritance ─────────────────────────────────────────
        for class_id, module_name, line, bases in class_bases:
            for base in bases:
                target = self._resolve_symbol(
                    graph, module_name, class_id, base, methods_by_class,
                    entity_ids_by_module_name, test_context=graph.graph.nodes[class_id].get("is_test", False),
                    unique_fallback=False,
                )
                if target and graph.graph.nodes[target]["type"] == "class":
                    graph.add_edge(
                        GraphEdge(class_id, target, "inherits", line=line,
                                  confidence=0.9, reason="Base class")
                    )

        # ── calls ───────────────────────────────────────────────
        for node_id, data in list(graph.graph.nodes(data=True)):
            if data["type"] not in ("function", "method"):
                continue
            parent_class = data.get("parent_id") if data["type"] == "method" else None
            for call in data.get("metadata", {}).get("calls", []):
                target = self._resolve_symbol(
                    graph,
                    data["module_name"],
                    parent_class,
                    call,
                    methods_by_class,
                    entity_ids_by_module_name,
                    test_context=data.get("is_test", False),
                    unique_fallback=bool(data.get("is_test")),
                )
                if target:
                    graph.add_edge(
                        GraphEdge(node_id, target, "call", line=data.get("line_start", 0),
                                  confidence=0.85 if data.get("is_test") else 0.9,
                                  reason=f"Calls {call}")
                    )

        logger.info(
            f"Graph built for {scan.repo_name}: {graph.graph.number_of_nodes()} nodes, "
            f"{graph.graph.number_of_edges()} edges"
        )
        return graph

    # ── resolution internals ────────────────────────────────────

    def _package_for(self, file_path: str, packages: set[str]) -> str | None:
        parent = str(PurePosixPath(file_path).parent)
        if parent in packages:
            return f"module:{parent}"
        return None

    @staticmethod
    def _import_dict(imp: ImportInfo) -> dict[str, Any]:
        return {
            "module": imp.module,
            "name": imp.name,
            "alias": imp.alias,
            "is_from": imp.is_from_import,
            "level": imp.level,
            "line": imp.line_number,
        }

    def _resolve_import_targets(
        self,
        graph: CodeGraph,
        modules: dict[str, ModuleParseResult],
        entities: dict[str, dict[str, str]],
        resolved_module: str,
        imp: ImportInfo,
    ) -> list[tuple[str, str, str]]:
        targets: list[tuple[str, str, str]] = []
        base_file = graph.module_files.get(resolved_module)
        if imp.is_from_import and imp.name:
            submodule = f"{resolved_module}.{imp.name}" if resolved_module else imp.name
            sub_file = graph.module_files.get(submodule)
            symbol = entities.get(resolved_module, {}).get(imp.name)
            if symbol:
                targets.append((symbol, "import_symbol", f"Imports {imp.name}"))
            elif sub_file:
                targets.append((sub_file, "import", f"Imports submodule {submodule}"))
            elif base_file:
                targets.append((base_file, "import", f"Imports from module {resolved_module}"))
        elif base_file:
            targets.append((base_file, "import", f"Imports module {resolved_module}"))
        else:
            # `import package.submodule` may target a package or a module that
            # is only partially available. Try the longest internal prefix.
            parts = resolved_module.split(".")
            for end in range(len(parts) - 1, 0, -1):
                prefix = ".".join(parts[:end])
                if prefix in graph.module_files:
                    targets.append(
                        (graph.module_files[prefix], "import", f"Imports package {prefix}")
                    )
                    break
        return targets

    def _resolve_symbol(
        self,
        graph: CodeGraph,
        module_name: str,
        class_id: str | None,
        raw_call: str,
        methods_by_class: dict[str, dict[str, str]],
        entities: dict[str, dict[str, str]],
        test_context: bool,
        unique_fallback: bool,
    ) -> str | None:
        if not raw_call:
            return None
        call = raw_call.strip()
        if call.startswith(("self.", "cls.")):
            rest = call.split(".", 1)[1]
            if class_id and "." not in rest:
                return methods_by_class.get(class_id, {}).get(rest)
            return None

        parts = call.split(".")
        head, tail = parts[0], parts[1:]

        # Same-module entity.
        local = entities.get(module_name, {})
        if not tail and head in local:
            return local[head]

        # A method on a class defined/imported in this module.
        if head in local:
            return self._walk_symbol_path(graph, local[head], tail, methods_by_class, entities)

        # Imported alias.
        file_node = graph.module_files.get(module_name)
        aliases = {}
        if file_node:
            aliases = graph.graph.nodes[file_node].get("metadata", {}).get("aliases", {})
        if head in aliases:
            alias = aliases[head]
            target_module = alias["module"]
            symbol = alias["symbol"]
            if symbol:
                symbol_id = entities.get(target_module, {}).get(symbol)
                if symbol_id:
                    return self._walk_symbol_path(
                        graph, symbol_id, tail, methods_by_class, entities
                    )
            if tail:
                joined = ".".join([target_module] + tail) if target_module else ".".join(tail)
                # An imported symbol may be a module.
                for candidate in (joined, f"{target_module}.{'.'.join(tail)}"):
                    if candidate in graph.module_files:
                        return graph.module_files[candidate]
                if target_module in graph.module_files:
                    target = entities.get(target_module, {}).get(tail[0])
                    if target:
                        return self._walk_symbol_path(
                            graph, target, tail[1:], methods_by_class, entities
                        )
            elif target_module in graph.module_files:
                return graph.module_files[target_module]

        # Fully qualified internal module, e.g. utils.math_helpers.add
        for index in range(len(parts) - 1, 0, -1):
            candidate_module = ".".join(parts[:index])
            if candidate_module in graph.module_files:
                target = entities.get(candidate_module, {}).get(parts[index])
                if target:
                    return self._walk_symbol_path(
                        graph, target, parts[index + 1:], methods_by_class, entities
                    )
                if index == len(parts):
                    return graph.module_files[candidate_module]

        # Test-only inference: unique method name across the repository.
        # This helps map test code such as `self.client.calculate(...)` where
        # static self-attribute tracking is unavailable. Confidence stays low.
        if unique_fallback and parts:
            last = parts[-1]
            matches = []
            for node_id, data in graph.graph.nodes(data=True):
                if data["type"] in ("function", "method") and data["name"] == last and not data.get("is_test"):
                    matches.append(node_id)
            if len(matches) == 1:
                return matches[0]
        return None

    def _walk_symbol_path(
        self,
        graph: CodeGraph,
        symbol_id: str,
        rest: list[str],
        methods_by_class: dict[str, dict[str, str]],
        entities: dict[str, dict[str, str]],
    ) -> str | None:
        data = graph.graph.nodes[symbol_id]
        if not rest:
            return symbol_id
        if data["type"] == "class":
            method = methods_by_class.get(symbol_id, {}).get(rest[0])
            if method:
                return method
        # Attribute access on an imported module symbol.
        if data["type"] == "file":
            target_entities = entities.get(data.get("module_name", ""), {})
            if rest[0] in target_entities:
                return self._walk_symbol_path(
                    graph, target_entities[rest[0]], rest[1:], methods_by_class, entities
                )
        return symbol_id


def resolve_relative_module(
    current_module: str, current_is_init: bool, imp: ImportInfo
) -> str:
    """Resolve a possibly-relative import to a dotted module name."""
    if imp.level <= 0:
        return imp.module

    parts = current_module.split(".") if current_module else []
    package = parts if current_is_init else parts[:-1]
    strip = max(0, imp.level - 1)
    if strip:
        package = package[:-strip] if strip <= len(package) else []
    base = ".".join(package)
    if imp.module:
        return f"{base}.{imp.module}" if base else imp.module
    return base


def is_test_path(file_path: str) -> bool:
    """Best-effort detection of pytest test files."""
    normalized = file_path.replace("\\", "/")
    path = PurePosixPath(normalized)
    parts = {part.lower() for part in path.parts[:-1]}
    name = path.name.lower()
    return (
        "tests" in parts
        or "test" in parts
        or name.startswith("test_")
        or name.endswith("_test.py")
    )


def module_name_for_path(relative_path: str) -> str:
    return file_path_to_module_name(relative_path, "")
