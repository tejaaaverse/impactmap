import { useMemo, useState } from "react";
import ReactFlow, {
  Background,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  type Edge,
  type Node,
  type NodeProps,
} from "reactflow";
import "reactflow/dist/style.css";
import { Search, X } from "lucide-react";
import type { GraphNode, RepositoryGraph } from "../types";
import { Badge } from "./ui/Badge";
import { Section } from "./ui/Section";
import { nodeTypeTone, shortenPath } from "../lib/format";

interface NodeData {
  label: string;
  type: string;
  filePath: string;
  moduleName: string;
  isTest: boolean;
  lineStart: number;
  qualifiedName: string;
}

const NODE_STYLES: Record<string, string> = {
  file: "border-mauve/40 bg-plum/90 text-blush",
  module: "border-lav/50 bg-lav/10 text-lav",
  class: "border-violet-400/50 bg-violet-400/10 text-violet-200",
  function: "border-hot/50 bg-neon/10 text-blush",
  method: "border-hot/30 bg-berry/10 text-blush",
  test: "border-berry/60 bg-berry/15 text-blush",
};

function EntityNode({ data, selected }: NodeProps<NodeData>) {
  const style = data.isTest
    ? NODE_STYLES.test
    : NODE_STYLES[data.type] ?? NODE_STYLES.file;
  return (
    <div
      className={`w-[220px] rounded-lg border px-3 py-2 text-left shadow-lg shadow-black/40 backdrop-blur ${style} ${
        selected ? "ring-2 ring-hot ring-offset-2 ring-offset-ink-950" : ""
      }`}
      title={`${data.qualifiedName} · ${data.filePath}:${data.lineStart}`}
    >
      <Handle type="target" position={Position.Left} className="!bg-lav" />
      <div className="flex items-center justify-between gap-2">
        <span className="truncate text-xs font-semibold">{data.label}</span>
        <span className="shrink-0 text-[9px] uppercase tracking-wider opacity-70">
          {data.isTest ? "test" : data.type}
        </span>
      </div>
      <div className="mt-0.5 truncate font-mono text-[10px] opacity-60">
        {shortenPath(data.filePath, 34)}:{data.lineStart}
      </div>
      <Handle type="source" position={Position.Right} className="!bg-lav" />
    </div>
  );
}

const NODE_TYPES = { entity: EntityNode };

const EDGE_COLORS: Record<string, string> = {
  import: "#FF79C9",
  calls: "#B78BFF",
  inherits: "#FFC5E8",
  contains: "#A83D83",
  tests: "#C99AB9",
};

const TYPE_FILTERS = ["all", "file", "module", "class", "function", "method", "test"];

export function GraphView({ graph }: { graph: RepositoryGraph }) {
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");
  const [showTests, setShowTests] = useState(true);
  const [selected, setSelected] = useState<GraphNode | null>(null);

  const visibleNodes = useMemo(() => {
    const query = search.trim().toLowerCase();
    return graph.nodes.filter((node) => {
      if (!showTests && (node.is_test || node.type === "test")) return false;
      if (typeFilter === "test" && !node.is_test) return false;
      if (typeFilter !== "all" && typeFilter !== "test" && node.type !== typeFilter) {
        return false;
      }
      if (!query) return true;
      return (
        node.name.toLowerCase().includes(query) ||
        node.qualified_name.toLowerCase().includes(query) ||
        node.file_path.toLowerCase().includes(query)
      );
    });
  }, [graph.nodes, search, typeFilter, showTests]);

  const visibleIds = useMemo(
    () => new Set(visibleNodes.map((node) => node.id)),
    [visibleNodes],
  );

  const flowNodes = useMemo<Node<NodeData>[]>(() => {
    const byFile = new Map<string, GraphNode[]>();
    for (const node of visibleNodes) {
      const list = byFile.get(node.file_path) ?? [];
      list.push(node);
      byFile.set(node.file_path, list);
    }
    const files = [...byFile.entries()].sort((a, b) => a[0].localeCompare(b[0]));
    const result: Node<NodeData>[] = [];
    files.forEach(([, nodes], column) => {
      const sorted = [...nodes].sort(
        (a, b) => a.line_start - b.line_start || a.name.localeCompare(b.name),
      );
      sorted.forEach((node, row) => {
        result.push({
          id: node.id,
          type: "entity",
          position: { x: column * 290, y: row * 82 },
          data: {
            label: node.name,
            type: node.type,
            filePath: node.file_path,
            moduleName: node.module_name,
            isTest: node.is_test,
            lineStart: node.line_start,
            qualifiedName: node.qualified_name,
          },
        });
      });
    });
    return result;
  }, [visibleNodes]);

  const flowEdges = useMemo<Edge[]>(
    () =>
      graph.edges
        .filter((edge) => visibleIds.has(edge.source) && visibleIds.has(edge.target))
        .map((edge, index) => {
          const color = EDGE_COLORS[edge.type] ?? "#C99AB9";
          return {
            id: `${edge.source}->${edge.target}:${edge.type}:${index}`,
            source: edge.source,
            target: edge.target,
            label: edge.type,
            labelStyle: { fill: "#FCEAF5", fontSize: 9, fontFamily: "JetBrains Mono" },
            labelBgStyle: { fill: "#190C1B", fillOpacity: 0.9 },
            style: {
              stroke: color,
              strokeWidth: selected?.id === edge.source ? 2.4 : 1.2,
              opacity: selected ? (selected.id === edge.source || selected.id === edge.target ? 1 : 0.25) : 0.7,
            },
            markerEnd: {
              type: MarkerType.ArrowClosed,
              color,
              width: 14,
              height: 14,
            },
          };
        }),
    [graph.edges, visibleIds, selected],
  );

  const neighbours = useMemo(() => {
    if (!selected) return { incoming: [], outgoing: [] };
    const byId = new Map(graph.nodes.map((node) => [node.id, node]));
    const incoming = graph.edges
      .filter((edge) => edge.target === selected.id)
      .map((edge) => ({ edge, node: byId.get(edge.source) }))
      .filter((item): item is { edge: typeof graph.edges[number]; node: GraphNode } => Boolean(item.node));
    const outgoing = graph.edges
      .filter((edge) => edge.source === selected.id)
      .map((edge) => ({ edge, node: byId.get(edge.target) }))
      .filter((item): item is { edge: typeof graph.edges[number]; node: GraphNode } => Boolean(item.node));
    return { incoming, outgoing };
  }, [graph.edges, graph.nodes, selected]);

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative min-w-[200px] flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
            <input
              className="input pl-9"
              placeholder="Search symbol, file or qualified name…"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              aria-label="Search graph"
            />
          </div>
          <select
            className="input w-auto"
            value={typeFilter}
            onChange={(event) => setTypeFilter(event.target.value)}
            aria-label="Filter node type"
          >
            {TYPE_FILTERS.map((type) => (
              <option key={type} value={type}>
                {type === "all" ? "All node types" : type}
              </option>
            ))}
          </select>
          <label className="flex cursor-pointer items-center gap-2 rounded-lg border border-violet-400/30 bg-ink-950/60 px-3 py-2 text-xs text-slate-300">
            <input
              type="checkbox"
              checked={showTests}
              onChange={(event) => setShowTests(event.target.checked)}
              className="accent-hot"
            />
            Tests
          </label>
        </div>

        <div className="flex flex-wrap items-center gap-3 text-[11px] text-slate-500">
          <span>
            {visibleNodes.length}/{graph.nodes.length} nodes
          </span>
          <span>{flowEdges.length} visible edges</span>
          {Object.entries(graph.stats.edge_types).map(([type, count]) => (
            <span key={type} className="inline-flex items-center gap-1.5">
              <span
                className="h-2 w-2 rounded-full"
                style={{ backgroundColor: EDGE_COLORS[type] ?? "#C99AB9" }}
              />
              {type} {count}
            </span>
          ))}
        </div>

        <div
          className="h-[620px] overflow-hidden rounded-xl border border-violet-400/25 bg-ink-950 shadow-glow"
          data-testid="graph-canvas"
        >
          {visibleNodes.length === 0 ? (
            <div className="grid h-full place-items-center text-sm text-slate-500">
              No nodes match the current filters.
            </div>
          ) : (
            <ReactFlow
              key={typeFilter}
              nodes={flowNodes}
              edges={flowEdges}
              nodeTypes={NODE_TYPES}
              fitView
              minZoom={0.1}
              proOptions={{ hideAttribution: false }}
              onNodeClick={(_, node) =>
                setSelected(graph.nodes.find((item) => item.id === node.id) ?? null)
              }
              onPaneClick={() => setSelected(null)}
            >
              <Background color="#3A1640" gap={22} size={1} />
              <Controls />
              <MiniMap
                pannable
                zoomable
                maskColor="rgba(16,8,18,0.72)"
                nodeColor={(node) => {
                  const data = node.data as NodeData;
                  if (data.isTest) return "#C99AB9";
                  if (data.type === "class") return "#B78BFF";
                  if (data.type === "module") return "#FFC5E8";
                  return "#FF79C9";
                }}
              />
            </ReactFlow>
          )}
        </div>
      </div>

      <aside className="h-fit xl:sticky xl:top-6">
        <Section title={selected ? "Node details" : "Graph explorer"}>
          {selected ? (
          <div className="space-y-4">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-pale">
                  {selected.name}
                </p>
                <p className="mt-0.5 break-all font-mono text-[11px] text-mauve">
                  {selected.qualified_name}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setSelected(null)}
                className="rounded p-1 text-slate-500 transition-colors hover:bg-rose-500/10 hover:text-blush"
                aria-label="Clear selection"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="flex flex-wrap gap-1.5">
              <Badge tone={nodeTypeTone(selected.type)}>{selected.type}</Badge>
              {selected.is_test && <Badge tone="emerald">test</Badge>}
              <Badge>{selected.module_name || "no module"}</Badge>
            </div>
            <dl className="space-y-2 text-xs">
              <div>
                <dt className="text-slate-500">File</dt>
                <dd className="break-all font-mono text-slate-300">
                  {selected.file_path}:{selected.line_start}
                </dd>
              </div>
              <div>
                <dt className="text-slate-500">Lines</dt>
                <dd className="text-slate-300">
                  {selected.line_start}–{selected.line_end}
                </dd>
              </div>
            </dl>

            <div>
              <p className="pixel-label mb-1 text-[7px] text-slate-500">
                Depends on ({neighbours.outgoing.length})
              </p>
              <ul className="max-h-40 space-y-1 overflow-y-auto text-xs">
                {neighbours.outgoing.length === 0 && (
                  <li className="text-slate-600">No outgoing edges</li>
                )}
                {neighbours.outgoing.map(({ edge, node }) => (
                  <li key={`${edge.source}-${edge.target}-${edge.type}`}>
                    <button
                      type="button"
                      className="w-full truncate rounded px-1.5 py-1 text-left text-slate-300 transition-colors hover:bg-rose-500/10 hover:text-blush"
                      onClick={() => setSelected(node)}
                    >
                      <span className="mr-1 text-hot">{edge.type}</span>
                      {node.name}
                    </button>
                  </li>
                ))}
              </ul>
            </div>

            <div>
              <p className="pixel-label mb-1 text-[7px] text-slate-500">
                Used by ({neighbours.incoming.length})
              </p>
              <ul className="max-h-40 space-y-1 overflow-y-auto text-xs">
                {neighbours.incoming.length === 0 && (
                  <li className="text-slate-600">No incoming edges</li>
                )}
                {neighbours.incoming.map(({ edge, node }) => (
                  <li key={`${edge.source}-${edge.target}-${edge.type}`}>
                    <button
                      type="button"
                      className="w-full truncate rounded px-1.5 py-1 text-left text-slate-300 transition-colors hover:bg-rose-500/10 hover:text-blush"
                      onClick={() => setSelected(node)}
                    >
                      <span className="mr-1 text-hot">{edge.type}</span>
                      {node.name}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        ) : (
          <div className="space-y-3 text-sm text-slate-400">
            <p>
              Edges point from a dependent to its dependency. Select any node to
              inspect its file, module and direct relationships.
            </p>
            <div className="space-y-1.5 text-xs">
              {[
                ["import", "module import"],
                ["calls", "function/method call"],
                ["inherits", "class inheritance"],
                ["contains", "structural containment"],
              ].map(([type, label]) => (
                <div key={type} className="flex items-center gap-2">
                  <span
                    className="h-2 w-2 rounded-full"
                    style={{ backgroundColor: EDGE_COLORS[type] }}
                  />
                  <span className="text-slate-300">{type}</span>
                  <span className="text-slate-600">· {label}</span>
                </div>
              ))}
            </div>
            <p className="border-t border-violet-400/15 pt-3 text-xs text-slate-500">
              {graph.stats.unresolved_imports} unresolved import
              {graph.stats.unresolved_imports === 1 ? "" : "s"} ·{" "}
              {graph.stats.test_nodes} test nodes
            </p>
          </div>
        )}
        </Section>
      </aside>
    </div>
  );
}
