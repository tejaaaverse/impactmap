import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowLeft,
  ChevronDown,
  ChevronRight,
  FlaskConical,
  GitPullRequest,
  ListChecks,
  PlayCircle,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Target,
} from "lucide-react";
import { api, ApiError } from "../services/api";
import { useAsync } from "../hooks/useAsync";
import { PageHeader } from "../components/ui/PageHeader";
import { Section } from "../components/ui/Section";
import { LoadingBlock } from "../components/ui/Loading";
import { ErrorPanel } from "../components/ui/ErrorPanel";
import { EmptyState } from "../components/ui/EmptyState";
import { StatusBadge } from "../components/ui/StatusBadge";
import { Badge } from "../components/ui/Badge";
import { StatCard } from "../components/ui/StatCard";
import { ConfirmDialog } from "../components/ui/ConfirmDialog";
import { TestExecutionView } from "../components/TestExecutionView";
import {
  formatDuration,
  formatPercent,
  formatTimestamp,
  nodeTypeTone,
  shortenPath,
  statusTone,
} from "../lib/format";
import type {
  AnalysisDetail,
  ChangedFile,
  ImpactEntry,
  ModeSelection,
  TestMode,
  TestRun,
} from "../types";

type Tab = "overview" | "impact" | "tests" | "runs";

const TABS: { id: Tab; label: string; icon: typeof Sparkles }[] = [
  { id: "overview", label: "Overview", icon: Sparkles },
  { id: "impact", label: "Impact", icon: Target },
  { id: "tests", label: "Test selection", icon: ListChecks },
  { id: "runs", label: "Test runs", icon: FlaskConical },
];

export function AnalysisDetailPage() {
  const { analysisId = "" } = useParams();
  const [tab, setTab] = useState<Tab>("overview");
  const data = useAsync(() => api.getAnalysis(analysisId), [analysisId]);

  if (data.loading && !data.data) return <LoadingBlock label="Loading analysis…" />;
  if (data.error) return <ErrorPanel message={data.error} onRetry={data.reload} />;
  if (!data.data) return null;

  const analysis = data.data;

  return <AnalysisView analysis={analysis} tab={tab} setTab={setTab} />;
}

function AnalysisView({
  analysis,
  tab,
  setTab,
}: {
  analysis: AnalysisDetail;
  tab: Tab;
  setTab: (tab: Tab) => void;
}) {
  return (
    <div>
      <Link
        to="/analyses"
        className="mb-4 inline-flex items-center gap-1.5 text-xs text-mauve transition-colors hover:text-hot"
      >
        <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
        All analyses
      </Link>

      <PageHeader
        eyebrow="Impact analysis"
        title={`${analysis.base_ref ?? "base"} → ${analysis.head_ref ?? "head"}`}
        subtitle={
          <span className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-xs text-mauve">{analysis.id}</span>
            <StatusBadge status={analysis.status} />
            <span className="text-xs text-slate-500">
              {formatTimestamp(analysis.created_at)}
            </span>
          </span>
        }
        actions={
          <Link
            to={`/repositories/${analysis.repository_id}`}
            className="btn-secondary"
          >
            <GitPullRequest className="h-4 w-4" />
            Open repository
          </Link>
        }
      />

      <div className="retro-tabs mb-5" role="group" aria-label="Analysis views">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            aria-pressed={tab === id}
            onClick={() => setTab(id)}
            className={`retro-tab ${tab === id ? "retro-tab-active" : ""}`}
          >
            <Icon className="h-3.5 w-3.5" aria-hidden="true" />
            {label}
          </button>
        ))}
      </div>

      {tab === "overview" && <OverviewTab analysis={analysis} />}
      {tab === "impact" && <ImpactTab analysis={analysis} />}
      {tab === "tests" && <SelectionTab analysis={analysis} />}
      {tab === "runs" && <TestRunsTab analysisId={analysis.id} />}
    </div>
  );
}

const IMPACT_BAR_TONES = [
  "from-hot to-berry",
  "from-lav to-hot",
  "from-berry to-lav",
  "from-blush to-berry",
  "from-neon to-lav",
  "from-pale to-hot",
];

function OverviewTab({ analysis }: { analysis: AnalysisDetail }) {
  const impact = analysis.impact;
  const byType = Object.entries(impact?.summary.by_type ?? {}).sort(
    (left, right) => right[1] - left[1],
  );
  const maxTypeCount = byType[0]?.[1] ?? 1;
  const direct = impact?.summary.direct_count ?? 0;
  const indirect = impact?.summary.indirect_count ?? 0;
  const totalAffected = direct + indirect;

  return (
    <div className="space-y-6">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Changed files"
          value={analysis.total_changed_files}
          hint={`${analysis.changed_entities.length} changed entities`}
          icon={<GitPullRequest className="h-4 w-4" />}
        />
        <StatCard
          label="Affected entities"
          value={impact?.summary.total_affected ?? analysis.total_affected_entities}
          hint={
            impact
              ? `${impact.summary.direct_count} direct · ${impact.summary.indirect_count} indirect`
              : undefined
          }
          icon={<Target className="h-4 w-4" />}
          tone="violet"
        />
        <StatCard
          label="Affected files"
          value={impact?.summary.affected_file_count ?? "—"}
          hint={impact ? `max depth ${impact.summary.max_depth}` : undefined}
          icon={<Sparkles className="h-4 w-4" />}
          tone="amber"
        />
        <StatCard
          label="Analysis duration"
          value={formatDuration(analysis.analysis_duration_ms)}
          hint={formatTimestamp(analysis.completed_at)}
          icon={<RefreshCw className="h-4 w-4" />}
          tone="emerald"
        />
      </div>

      {analysis.error_message && (
        <ErrorPanel message={analysis.error_message} />
      )}
      {impact && impact.warnings.length > 0 && (
        <ul className="space-y-1 rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-2 text-xs text-amber-200">
          {impact.warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      )}

      {impact && totalAffected > 0 && (
        <Section
          title="Impact concentration"
          description="Every affected entity from this run, grouped by node type. Longer bars mean a wider blast radius."
        >
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_220px] lg:items-start">
            <ul className="space-y-2.5" aria-label="Affected entities by type">
              {byType.length === 0 && (
                <li className="text-xs text-slate-500">
                  This run did not include a per-type breakdown.
                </li>
              )}
              {byType.map(([type, count], index) => {
                const width = Math.max(
                  6,
                  Math.round((count / Math.max(maxTypeCount, 1)) * 100),
                );
                return (
                  <li
                    key={type}
                    className="grid grid-cols-[minmax(72px,110px)_minmax(0,1fr)_44px] items-center gap-2.5"
                  >
                    <span
                      className="truncate font-mono text-[11px] text-slate-300"
                      title={type}
                    >
                      {type}
                    </span>
                    <span className="y2k-inset block h-3 overflow-hidden rounded-sm">
                      <span
                        className={`block h-full rounded-sm bg-gradient-to-r ${
                          IMPACT_BAR_TONES[index % IMPACT_BAR_TONES.length]
                        }`}
                        style={{ width: `${width}%` }}
                        aria-hidden="true"
                      />
                    </span>
                    <span className="text-right font-mono text-[11px] text-blush">
                      {count}
                    </span>
                  </li>
                );
              })}
            </ul>

            <div className="y2k-bevel rounded-xl p-3">
              <p className="pixel-label text-[6px] text-mauve">reach.split</p>
              <p className="mt-2 font-display text-2xl font-semibold text-pale">
                {totalAffected}
              </p>
              <p className="text-[10px] text-slate-500">total affected</p>
              <div className="mt-3 flex h-2 overflow-hidden rounded-full border border-violet-400/20">
                <span
                  className="bg-hot"
                  style={{
                    width: `${totalAffected ? (direct / totalAffected) * 100 : 0}%`,
                  }}
                  aria-hidden="true"
                />
                <span
                  className="bg-lav"
                  style={{
                    width: `${
                      totalAffected ? (indirect / totalAffected) * 100 : 0
                    }%`,
                  }}
                  aria-hidden="true"
                />
              </div>
              <dl className="mt-2 space-y-1 text-[11px]">
                <div className="flex items-center justify-between gap-2">
                  <dt className="inline-flex items-center gap-1.5 text-slate-400">
                    <span className="h-1.5 w-1.5 rounded-full bg-hot" aria-hidden="true" />
                    Direct
                  </dt>
                  <dd className="font-mono text-hot">{direct}</dd>
                </div>
                <div className="flex items-center justify-between gap-2">
                  <dt className="inline-flex items-center gap-1.5 text-slate-400">
                    <span className="h-1.5 w-1.5 rounded-full bg-lav" aria-hidden="true" />
                    Indirect
                  </dt>
                  <dd className="font-mono text-lav">{indirect}</dd>
                </div>
              </dl>
            </div>
          </div>
        </Section>
      )}

      <div className="grid gap-4 xl:grid-cols-2">
        <Section
          title="Changed files"
          description="Parsed from the Git diff, including rename and deletion detection."
        >
          {analysis.changed_files.length === 0 ? (
            <EmptyState
              title="No changed files"
              description="The selected refs produced an empty diff."
            />
          ) : (
            <div className="max-h-[420px] overflow-auto">
              <table className="table-base">
                <thead className="sticky top-0 bg-ink-900">
                  <tr>
                    <th>File</th>
                    <th>Change</th>
                    <th>+ / −</th>
                  </tr>
                </thead>
                <tbody>
                  {analysis.changed_files.map((file) => {
                    const rows = file as ChangedFile & {
                      added_line_count?: number;
                      deleted_line_count?: number;
                    };
                    const path = String(rows.path ?? "—");
                    return (
                      <tr key={`${path}-${String(rows.change_type)}`}>
                        <td className="max-w-[320px] truncate font-mono text-[11px] text-slate-300" title={path}>
                          {path}
                        </td>
                        <td>
                          <StatusBadge status={String(rows.change_type ?? "modified")} />
                        </td>
                        <td className="whitespace-nowrap text-xs">
                          <span className="text-lav">
                            +{rows.added_line_count ?? 0}
                          </span>{" "}
                          <span className="text-hot">
                            −{rows.deleted_line_count ?? 0}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Section>

        <Section
          title="Changed entities"
          description="Functions, methods and classes whose spans intersect changed hunks."
        >
          {analysis.changed_entities.length === 0 ? (
            <EmptyState
              title="No Python entities changed"
              description="The diff may contain non-Python files or only comments and imports."
            />
          ) : (
            <div className="max-h-[420px] overflow-auto">
              <table className="table-base">
                <thead className="sticky top-0 bg-ink-900">
                  <tr>
                    <th>Entity</th>
                    <th>Change</th>
                    <th>File</th>
                  </tr>
                </thead>
                <tbody>
                  {analysis.changed_entities.map((entity, index) => {
                    const record = entity as Record<string, unknown>;
                    const key = String(record.key ?? index);
                    const name = String(record.qualified_name ?? record.name ?? "—");
                    const kind = String(record.kind ?? record.type ?? "entity");
                    const path = String(record.file_path ?? "—");
                    return (
                      <tr key={key}>
                        <td>
                          <p className="text-xs font-medium text-slate-200">{name}</p>
                          <Badge tone={nodeTypeTone(kind)}>{kind}</Badge>
                        </td>
                        <td>
                          <StatusBadge status={String(record.change_type ?? "modified")} />
                        </td>
                        <td className="max-w-[220px] truncate font-mono text-[11px] text-slate-400" title={path}>
                          {shortenPath(path, 34)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Section>
      </div>

      {impact && (
        <Section title="Methodology">
          <p className="text-sm leading-relaxed text-slate-400">{impact.methodology}</p>
          {impact.summary.truncated && (
            <p className="mt-2 text-xs text-amber-300">
              Traversal was truncated by the configured node/depth limits.
            </p>
          )}
          {impact.summary.excluded_test_nodes > 0 && (
            <p className="mt-1 text-xs text-slate-500">
              {impact.summary.excluded_test_nodes} test nodes were excluded from
              traversal. Re-run the analysis with “include tests” to keep them.
            </p>
          )}
        </Section>
      )}
    </div>
  );
}

type ImpactFilter = "all" | "direct" | "indirect";

function ImpactTab({ analysis }: { analysis: AnalysisDetail }) {
  const [filter, setFilter] = useState<ImpactFilter>("all");
  const [search, setSearch] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);

  const impact = analysis.impact;
  const entries = useMemo(() => {
    if (!impact) return [];
    const combined =
      filter === "direct"
        ? impact.direct_impacts
        : filter === "indirect"
          ? impact.indirect_impacts
          : [...impact.direct_impacts, ...impact.indirect_impacts];
    const query = search.trim().toLowerCase();
    return combined
      .filter((entry) =>
        query
          ? entry.name.toLowerCase().includes(query) ||
            entry.qualified_name.toLowerCase().includes(query) ||
            entry.file_path.toLowerCase().includes(query) ||
            entry.reason.toLowerCase().includes(query)
          : true,
      )
      .sort((a, b) => b.score - a.score);
  }, [impact, filter, search]);

  if (!impact) {
    return (
      <EmptyState
        title="No impact result"
        description="This analysis did not produce an impact result. Check the run status and error message."
      />
    );
  }

  return (
    <div className="space-y-5">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Direct impacts" value={impact.summary.direct_count} tone="sky" />
        <StatCard label="Indirect impacts" value={impact.summary.indirect_count} tone="violet" />
        <StatCard label="Affected files" value={impact.summary.affected_file_count} tone="amber" />
        <StatCard label="Max depth" value={impact.summary.max_depth} tone="emerald" />
      </div>

      {impact.summary.by_type && Object.keys(impact.summary.by_type).length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {Object.entries(impact.summary.by_type).map(([type, count]) => (
            <Badge key={type} tone={nodeTypeTone(type)}>
              {type} · {count}
            </Badge>
          ))}
        </div>
      )}

      <Section
        title="Reverse dependency impact"
        description="Ranked by a multiplicative score. Direct seeds start at 100; each hop decays by edge type and confidence."
        actions={
          <div className="flex flex-wrap gap-2">
            <input
              className="input w-52"
              placeholder="Search impacted code…"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              aria-label="Search impacts"
            />
            <select
              className="input w-auto"
              value={filter}
              onChange={(event) => setFilter(event.target.value as ImpactFilter)}
              aria-label="Filter impact type"
            >
              <option value="all">All impacts</option>
              <option value="direct">Direct only</option>
              <option value="indirect">Indirect only</option>
            </select>
          </div>
        }
      >
        {entries.length === 0 ? (
          <EmptyState
            title="No matching impacts"
            description="Try clearing the search or switching the impact filter."
          />
        ) : (
          <div className="max-h-[620px] overflow-auto">
            <table className="table-base">
              <thead className="sticky top-0 bg-ink-900">
                <tr>
                  <th>Score</th>
                  <th>Entity</th>
                  <th>Type</th>
                  <th>File</th>
                  <th>Depth</th>
                  <th>Confidence</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {entries.map((entry) => (
                  <ImpactRow
                    key={entry.node_id}
                    entry={entry}
                    expanded={expanded === entry.node_id}
                    onToggle={() =>
                      setExpanded(expanded === entry.node_id ? null : entry.node_id)
                    }
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <Section title="Why these results?">
        <p className="text-sm leading-relaxed text-slate-400">{impact.methodology}</p>
        <p className="mt-2 text-xs text-slate-500">
          Scores are static risk estimates derived from resolved edges and confidence
          weights. They are not probabilities that a test will fail.
        </p>
      </Section>
    </div>
  );
}

function ImpactRow({
  entry,
  expanded,
  onToggle,
}: {
  entry: ImpactEntry;
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <>
      <tr className="cursor-pointer" onClick={onToggle}>
        <td>
          <div className="flex items-center gap-2">
            <span className="w-10 text-right font-mono text-xs text-hot">
              {entry.score.toFixed(1)}
            </span>
            <span className="h-1.5 w-16 overflow-hidden rounded-full border border-violet-400/20 bg-ink-950">
              <span
                className="block h-full rounded-full bg-gradient-to-r from-neon via-hot to-lav shadow-[0_0_8px_rgba(255,121,201,0.7)]"
                style={{ width: `${Math.min(100, entry.score)}%` }}
              />
            </span>
          </div>
        </td>
        <td>
          <p className="text-xs font-medium text-slate-200">{entry.name}</p>
          <p className="font-mono text-[10px] text-slate-500">{entry.qualified_name}</p>
        </td>
        <td>
          <Badge tone={nodeTypeTone(entry.type)}>
            {entry.impact_type === "direct" ? "direct" : "indirect"} · {entry.type}
          </Badge>
        </td>
        <td className="max-w-[240px] truncate font-mono text-[11px] text-slate-400" title={entry.file_path}>
          {shortenPath(entry.file_path, 36)}
        </td>
        <td className="text-xs text-slate-400">{entry.depth}</td>
        <td className="text-xs text-slate-400">{formatPercent(entry.confidence * 100, 0)}</td>
        <td className="text-right text-slate-500">
          {expanded ? <ChevronDown className="ml-auto h-4 w-4" /> : <ChevronRight className="ml-auto h-4 w-4" />}
        </td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan={7} className="bg-ink-950/60">
            <div className="space-y-3 p-2">
              <p className="text-xs text-slate-300">{entry.reason}</p>
              <div className="flex flex-wrap gap-1.5">
                {entry.edge_types.map((edgeType) => (
                  <Badge key={edgeType} tone="slate">
                    edge: {edgeType}
                  </Badge>
                ))}
                {entry.is_deleted && <Badge tone="rose">deleted</Badge>}
                {entry.is_test && <Badge tone="emerald">test</Badge>}
              </div>
              {entry.path.length > 0 && (
                <div>
                  <p className="mb-1 text-[10px] uppercase tracking-wider text-slate-500">
                    Dependency path
                  </p>
                  <ol className="space-y-1">
                    {entry.path.map((step, index) => (
                      <li
                        key={`${String(step.node_id ?? step.id ?? index)}-${index}`}
                        className="flex items-center gap-2 text-[11px] text-slate-400"
                      >
                        <span className="grid h-4 w-4 shrink-0 place-items-center rounded-full border border-violet-400/25 bg-violet-400/10 text-[9px] text-blush">
                          {index + 1}
                        </span>
                        <span className="font-mono text-slate-300">
                          {String(step.name ?? step.node_id ?? "—")}
                        </span>
                        <span className="text-slate-600">
                          {String(step.type ?? "")}{" "}
                          {step.file_path ? `· ${String(step.file_path)}` : ""}
                        </span>
                      </li>
                    ))}
                  </ol>
                </div>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

function SelectionTab({ analysis }: { analysis: AnalysisDetail }) {
  const selection = analysis.selection;
  const [mode, setMode] = useState<"optimized" | "safe">("optimized");
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [lastRun, setLastRun] = useState<TestRun | null>(null);
  const [runMode, setRunMode] = useState<TestMode>("optimized");
  const [collectCoverage, setCollectCoverage] = useState(false);
  const [timeout, setTimeoutValue] = useState(600);

  if (!selection) {
    return (
      <EmptyState
        title="No test selection stored"
        description="The analysis completed without a selection result. Re-run the analysis or inspect its error message."
      />
    );
  }

  const current: ModeSelection | null = mode === "safe" ? selection.safe : selection.optimized;
  const modeSelection =
    runMode === "optimized"
      ? selection.optimized
      : runMode === "safe"
        ? selection.safe
        : null;
  const runCount = runMode === "full" ? selection.total_tests_discovered : (modeSelection?.selected_count ?? 0);

  async function executeTests() {
    setRunning(true);
    setRunError(null);
    try {
      const result = await api.runTests(analysis.id, {
        mode: runMode,
        confirm: true,
        collect_coverage: collectCoverage,
        timeout_seconds: timeout,
      });
      setLastRun(result);
      setConfirmOpen(false);
    } catch (err) {
      setRunError(
        err instanceof ApiError ? err.message : err instanceof Error ? err.message : String(err),
      );
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="space-y-5">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Coverage evidence"
          value={selection.coverage_available ? "Available" : "Fallback"}
          hint={
            selection.coverage_available
              ? `${selection.measured_tests} measured tests`
              : "No per-test coverage snapshot"
          }
          tone={selection.coverage_available ? "emerald" : "amber"}
          icon={<ShieldCheck className="h-4 w-4" />}
        />
        <StatCard
          label="Discovered tests"
          value={selection.total_tests_discovered}
          icon={<ListChecks className="h-4 w-4" />}
        />
        <StatCard
          label="Selected"
          value={current?.selected_count ?? "—"}
          hint={current ? `mode: ${current.mode}` : undefined}
          tone="violet"
          icon={<Target className="h-4 w-4" />}
        />
        <StatCard
          label="Reduction"
          value={formatPercent(current?.reduction_percent)}
          hint={current?.fallback_used ? "fallback to full suite" : "vs. full suite"}
          tone={current?.fallback_used ? "amber" : "emerald"}
          icon={<FlaskConical className="h-4 w-4" />}
        />
      </div>

      <Section
        title="Selection mode"
        description="Safe mode includes every test that depends on changed code. Optimized mode additionally ranks by coverage evidence."
        actions={
          <div className="inline-flex rounded-lg border border-violet-400/25 bg-ink-950 p-0.5">
            {(["optimized", "safe"] as const).map((value) => (
              <button
                key={value}
                type="button"
                onClick={() => setMode(value)}
                className={`rounded-md px-3 py-1.5 text-xs capitalize transition-all ${
                  mode === value
                    ? "bg-gradient-to-r from-neon/25 to-lav/15 text-pale shadow-glow"
                    : "text-slate-500 hover:text-pale"
                }`}
              >
                {value}
              </button>
            ))}
          </div>
        }
      >
        {current ? (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <StatusBadge
                status={current.fallback_used ? "fallback" : "completed"}
                label={current.fallback_used ? "fallback used" : "complete selection"}
              />
              <span className="text-slate-400">
                {current.selected_count} of {current.total_tests} tests
              </span>
              <span className="text-slate-500">
                {formatPercent(current.reduction_percent)} reduction
              </span>
            </div>
            <p className="retro-inset p-3 text-xs leading-relaxed text-slate-400">
              {current.rationale || "No rationale recorded."}
            </p>
            {current.warnings.length > 0 && (
              <ul className="space-y-1 rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-2 text-xs text-amber-200">
                {current.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            )}

            {current.selected_tests.length === 0 ? (
              <EmptyState
                title="No tests selected"
                description="No tests were selected for this mode. Running the full suite is still available below."
              />
            ) : (
              <div className="max-h-[460px] overflow-auto">
                <table className="table-base">
                  <thead className="sticky top-0 bg-ink-900">
                    <tr>
                      <th>Test</th>
                      <th>Score</th>
                      <th>Source</th>
                      <th>Reasons</th>
                      <th>Previously failed</th>
                    </tr>
                  </thead>
                  <tbody>
                    {current.selected_tests.map((test) => (
                      <tr key={test.test_id}>
                        <td>
                          <p className="text-xs font-medium text-slate-200">{test.name}</p>
                          <p className="break-all font-mono text-[10px] text-slate-500">
                            {test.test_id}
                          </p>
                        </td>
                        <td className="font-mono text-xs text-hot">
                          {test.score.toFixed(1)}
                        </td>
                        <td>
                          <Badge tone={test.source === "coverage" ? "emerald" : "slate"}>
                            {test.source}
                          </Badge>
                        </td>
                        <td className="max-w-[340px] text-[11px] text-slate-400">
                          {test.reasons.length ? test.reasons.join(" · ") : "—"}
                        </td>
                        <td>
                          {test.previously_failed ? (
                            <Badge tone="rose">yes</Badge>
                          ) : (
                            <span className="text-xs text-slate-600">no</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        ) : (
          <EmptyState
            title={`No ${mode} selection`}
            description="This analysis stored only one selection mode."
          />
        )}

        {selection.warnings.length > 0 && (
          <div className="mt-4 rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-2 text-xs text-amber-200">
            <p className="mb-1 font-medium uppercase tracking-wider text-amber-300/80">
              Selection warnings
            </p>
            <ul className="space-y-1">
              {selection.warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          </div>
        )}
        {selection.notes.length > 0 && (
          <ul className="mt-3 space-y-1 text-xs text-slate-500">
            {selection.notes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        )}
      </Section>

      <Section
        title="Execute selected suite"
        description="Test execution runs repository code in a subprocess and always requires explicit confirmation."
      >
        <div className="grid gap-3 sm:grid-cols-3">
          <div>
            <label className="label" htmlFor="run-mode">
              Run mode
            </label>
            <select
              id="run-mode"
              className="input"
              value={runMode}
              onChange={(event) => setRunMode(event.target.value as TestMode)}
            >
              <option value="optimized">Optimized selection</option>
              <option value="safe">Safe selection</option>
              <option value="full">Full suite</option>
            </select>
          </div>
          <div>
            <label className="label" htmlFor="run-timeout">
              Timeout (seconds)
            </label>
            <input
              id="run-timeout"
              type="number"
              min={1}
              max={3600}
              className="input"
              value={timeout}
              onChange={(event) => setTimeoutValue(Number(event.target.value))}
            />
          </div>
          <div className="flex items-end">
            <label className="flex cursor-pointer items-center gap-2 text-xs text-slate-400">
              <input
                type="checkbox"
                checked={collectCoverage}
                onChange={(event) => setCollectCoverage(event.target.checked)}
                className="accent-hot"
              />
              Collect coverage for this run
            </label>
          </div>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            type="button"
            className="btn-primary"
            onClick={() => setConfirmOpen(true)}
            disabled={runCount === 0 && runMode !== "full"}
          >
            <PlayCircle className="h-4 w-4" />
            Run tests
          </button>
          <span className="text-xs text-slate-500">
            {runMode === "full"
              ? `Runs all ${runCount} discovered tests.`
              : `${runCount} tests selected in ${runMode} mode.`}
          </span>
        </div>

        {runError && (
          <p className="mt-3 rounded-lg border border-rose-500/30 bg-rose-500/5 px-3 py-2 text-sm text-rose-300">
            {runError}
          </p>
        )}

        {lastRun && (
          <div className="mt-4 space-y-2 border-t border-violet-400/15 pt-4">
            <div className="flex items-center gap-2 text-xs">
              <p className="uppercase tracking-wider text-slate-500">Run result</p>
              <StatusBadge status={lastRun.status} />
              <span className="text-slate-500">{formatTimestamp(lastRun.created_at)}</span>
            </div>
            <TestExecutionView execution={lastRun.execution} />
          </div>
        )}

        <ConfirmDialog
          open={confirmOpen}
          title="Execute repository tests?"
          description={
            <>
              {runMode === "full"
                ? "This runs every discovered test."
                : `${runCount} ${runMode} tests will run.`}{" "}
              Repository test code executes in a subprocess; only proceed for trusted
              repositories.
            </>
          }
          confirmLabel={running ? "Running…" : "Run tests"}
          busy={running}
          onCancel={() => setConfirmOpen(false)}
          onConfirm={executeTests}
        >
          {collectCoverage && (
            <p className="rounded-lg border border-violet-400/25 bg-violet-400/5 px-3 py-2 text-xs text-blush">
              Coverage will be collected and merged into the repository snapshot after
              the run.
            </p>
          )}
        </ConfirmDialog>
      </Section>
    </div>
  );
}

function TestRunsTab({ analysisId }: { analysisId: string }) {
  const runs = useAsync(() => api.getTestRuns(analysisId), [analysisId]);
  const [expanded, setExpanded] = useState<string | null>(null);

  if (runs.loading && !runs.data) return <LoadingBlock label="Loading test runs…" />;
  if (runs.error) return <ErrorPanel message={runs.error} onRetry={runs.reload} />;
  if (!runs.data) return null;

  return (
    <Section
      title="Execution history"
      description="Confirmed test runs associated with this analysis, including captured process output."
      actions={
        <button type="button" className="btn-secondary" onClick={runs.reload}>
          <RefreshCw className="h-4 w-4" />
          Refresh
        </button>
      }
    >
      {runs.data.runs.length === 0 ? (
        <EmptyState
          icon={<FlaskConical className="h-5 w-5" />}
          title="No test runs yet"
          description="Execute the selected or full suite from the Test selection tab. Runs are stored with durations, counts and output tails."
        />
      ) : (
        <div className="space-y-2">
          {runs.data.runs.map((run) => (
            <div key={run.id} className="retro-inset overflow-hidden">
              <button
                type="button"
                className="flex w-full flex-wrap items-center justify-between gap-2 px-3 py-2.5 text-left transition-colors hover:bg-rose-500/5"
                onClick={() => setExpanded(expanded === run.id ? null : run.id)}
              >
                <span className="flex items-center gap-2 text-xs">
                  <Badge tone={statusTone(run.status) === "slate" ? "slate" : statusTone(run.status)}>
                    {run.mode}
                  </Badge>
                  <StatusBadge status={run.status} />
                  <span className="text-slate-400">
                    {run.total_tests} tests · {run.passed} passed · {run.failed} failed
                  </span>
                  <span className="text-slate-500">{formatDuration(run.duration_ms)}</span>
                </span>
                <span className="flex items-center gap-2 text-[11px] text-slate-500">
                  {formatTimestamp(run.created_at)}
                  {expanded === run.id ? (
                    <ChevronDown className="h-4 w-4" />
                  ) : (
                    <ChevronRight className="h-4 w-4" />
                  )}
                </span>
              </button>
              {expanded === run.id && (
                <div className="border-t border-violet-400/15 px-3 py-3">
                  <TestExecutionView execution={run.execution} />
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </Section>
  );
}
