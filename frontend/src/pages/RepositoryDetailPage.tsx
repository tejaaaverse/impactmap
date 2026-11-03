import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft,
  Boxes,
  GitBranch,
  GitCommitHorizontal,
  Layers,
  PlayCircle,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  TestTube2,
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
import { GraphView } from "../components/GraphView";
import { ConfirmDialog } from "../components/ui/ConfirmDialog";
import { TestExecutionView } from "../components/TestExecutionView";
import {
  formatCount,
  formatDuration,
  formatRelative,
  formatTimestamp,
  nodeTypeTone,
} from "../lib/format";
import type { CoverageCollectResult, RepositoryDetail } from "../types";

type Tab = "overview" | "graph" | "entities" | "tests";

const TABS: { id: Tab; label: string; icon: typeof Boxes }[] = [
  { id: "overview", label: "Overview", icon: Layers },
  { id: "graph", label: "Dependency graph", icon: GitBranch },
  { id: "entities", label: "Entities", icon: Boxes },
  { id: "tests", label: "Tests & coverage", icon: TestTube2 },
];

export function RepositoryDetailPage() {
  const { repositoryId = "" } = useParams();
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>("overview");
  const repo = useAsync(() => api.getRepository(repositoryId), [repositoryId]);

  if (repo.loading && !repo.data)
    return <LoadingBlock label="Loading repository…" />;
  if (repo.error)
    return <ErrorPanel message={repo.error} onRetry={repo.reload} />;
  if (!repo.data) return null;

  const repository = repo.data;

  return (
    <div>
      <Link
        to="/repositories"
        className="mb-4 inline-flex items-center gap-1.5 text-xs text-mauve transition-colors hover:text-hot"
      >
        <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
        All repositories
      </Link>

      <PageHeader
        eyebrow="Repository"
        title={repository.name}
        subtitle={
          <span className="flex flex-wrap items-center gap-2">
            <span className="break-all font-mono text-xs text-mauve">
              {repository.path}
            </span>
            <StatusBadge status={repository.status} />
            {repository.is_git_repository ? (
              <Badge tone="emerald">
                <GitCommitHorizontal className="h-3 w-3" /> git
              </Badge>
            ) : (
              <Badge tone="amber">no git history</Badge>
            )}
          </span>
        }
        actions={
          <>
            <button type="button" className="btn-secondary" onClick={repo.reload}>
              <RefreshCw className="h-4 w-4" />
              Refresh
            </button>
            <button
              type="button"
              className="btn-primary"
              onClick={() => setTab("overview")}
            >
              <PlayCircle className="h-4 w-4" />
              Analyze changes
            </button>
          </>
        }
      />

      <div className="retro-tabs mb-5" role="group" aria-label="Repository views">
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

      {tab === "overview" && (
        <OverviewTab
          repository={repository}
          onAnalyzed={(analysisId) => navigate(`/analyses/${analysisId}`)}
        />
      )}
      {tab === "graph" && <GraphTab repositoryId={repository.id} />}
      {tab === "entities" && <EntitiesTab repository={repository} />}
      {tab === "tests" && <TestsTab repositoryId={repository.id} />}
    </div>
  );
}

function OverviewTab({
  repository,
  onAnalyzed,
}: {
  repository: RepositoryDetail;
  onAnalyzed: (analysisId: string) => void;
}) {
  const [baseRef, setBaseRef] = useState("HEAD~1");
  const [headRef, setHeadRef] = useState("WORKING");
  const [includeTests, setIncludeTests] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleAnalyze(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = await api.analyzeRepository(repository.id, {
        base_ref: baseRef,
        head_ref: headRef,
        include_tests: includeTests,
      });
      onAnalyzed(result.analysis.id);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : err instanceof Error ? err.message : String(err),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Python files"
          value={formatCount(repository.total_files)}
          icon={<Boxes className="h-4 w-4" />}
        />
        <StatCard
          label="Functions"
          value={formatCount(repository.total_functions)}
          icon={<GitBranch className="h-4 w-4" />}
          tone="violet"
        />
        <StatCard
          label="Classes"
          value={formatCount(repository.total_classes)}
          icon={<Layers className="h-4 w-4" />}
          tone="amber"
        />
        <StatCard
          label="Dependencies"
          value={formatCount(repository.total_dependencies)}
          hint={`${repository.entities.length} stored entities`}
          icon={<Sparkles className="h-4 w-4" />}
          tone="emerald"
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]">
        <Section
          title="Run impact analysis"
          description="The analyzer diffs two Git states, maps changed symbols, traverses dependents and selects tests. No test code runs during analysis."
        >
          <form onSubmit={handleAnalyze} className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <label className="label" htmlFor="base-ref">
                  Base ref
                </label>
                <input
                  id="base-ref"
                  className="input font-mono text-xs"
                  value={baseRef}
                  onChange={(event) => setBaseRef(event.target.value)}
                  placeholder="HEAD~1"
                />
              </div>
              <div>
                <label className="label" htmlFor="head-ref">
                  Head ref
                </label>
                <input
                  id="head-ref"
                  className="input font-mono text-xs"
                  value={headRef}
                  onChange={(event) => setHeadRef(event.target.value)}
                  placeholder="WORKING"
                />
              </div>
            </div>
            <div className="retro-inset p-3 text-xs text-slate-400">
              <p className="pixel-label mb-2 text-[7px] text-lav">diff preview</p>
              <p>
                <span className="font-mono text-blush">
                  {baseRef || "HEAD~1"}..{headRef || "WORKING"}
                </span>{" "}
                — use <span className="font-mono text-hot">WORKING</span> to include
                uncommitted changes.
              </p>
            </div>
            <label className="flex cursor-pointer items-start gap-2 text-xs text-slate-400">
              <input
                type="checkbox"
                checked={includeTests}
                onChange={(event) => setIncludeTests(event.target.checked)}
                className="mt-0.5 accent-hot"
              />
              Include test nodes in the impact graph traversal (off by default so
              recommendations stay focused on production code).
            </label>
            {error && (
              <p className="rounded-lg border border-rose-500/30 bg-rose-500/5 px-3 py-2 text-sm text-rose-300">
                {error}
              </p>
            )}
            <div className="flex items-center gap-2">
              <button type="submit" className="btn-primary" disabled={busy || !repository.is_git_repository}>
                <PlayCircle className="h-4 w-4" />
                {busy ? "Analyzing…" : "Run analysis"}
              </button>
              {!repository.is_git_repository && (
                <span className="text-xs text-amber-300">
                  Git history is required for diff-based analysis.
                </span>
              )}
            </div>
          </form>
        </Section>

        <Section title="Scan metadata">
          <dl className="space-y-3 text-xs">
            {[
              ["Repository ID", repository.id],
              ["Status", repository.status],
              ["Last scanned", formatTimestamp(repository.last_scanned_at)],
              ["Created", formatTimestamp(repository.created_at)],
              ["Updated", formatRelative(repository.updated_at)],
            ].map(([label, value]) => (
              <div key={label} className="flex justify-between gap-3 border-b border-violet-400/10 pb-2">
                <dt className="text-slate-500">{label}</dt>
                <dd className="truncate text-right font-mono text-blush" title={String(value)}>
                  {value}
                </dd>
              </div>
            ))}
          </dl>
          {repository.scan_error && (
            <p className="mt-3 rounded-lg border border-rose-500/30 bg-rose-500/5 px-3 py-2 text-xs text-rose-300">
              {repository.scan_error}
            </p>
          )}
          {repository.entities.length > 0 && (
            <div className="mt-4">
              <p className="pixel-label mb-2 text-[7px] text-slate-500">
                Entity mix
              </p>
              <div className="flex flex-wrap gap-1.5">
                {Object.entries(
                  repository.entities.reduce<Record<string, number>>((acc, entity) => {
                    acc[entity.entity_type] = (acc[entity.entity_type] ?? 0) + 1;
                    return acc;
                  }, {}),
                ).map(([type, count]) => (
                  <Badge key={type} tone={nodeTypeTone(type)}>
                    {type} · {count}
                  </Badge>
                ))}
              </div>
            </div>
          )}
        </Section>
      </div>
    </div>
  );
}

function GraphTab({ repositoryId }: { repositoryId: string }) {
  const graph = useAsync(() => api.getGraph(repositoryId), [repositoryId]);

  if (graph.loading && !graph.data) return <LoadingBlock label="Building graph…" />;
  if (graph.error) return <ErrorPanel message={graph.error} onRetry={graph.reload} />;
  if (!graph.data) return null;

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Nodes" value={formatCount(graph.data.stats.nodes)} />
        <StatCard label="Edges" value={formatCount(graph.data.stats.edges)} tone="violet" />
        <StatCard
          label="Test nodes"
          value={formatCount(graph.data.stats.test_nodes)}
          tone="emerald"
        />
        <StatCard
          label="Unresolved imports"
          value={formatCount(graph.data.stats.unresolved_imports)}
          tone={graph.data.stats.unresolved_imports > 0 ? "amber" : "slate"}
        />
      </div>
      {graph.data.warnings.length > 0 && (
        <ul className="space-y-1 rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-2 text-xs text-amber-200">
          {graph.data.warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      )}
      <GraphView graph={graph.data} />
    </div>
  );
}

function EntitiesTab({ repository }: { repository: RepositoryDetail }) {
  const [search, setSearch] = useState("");
  const [type, setType] = useState("all");

  const types = useMemo(
    () => ["all", ...new Set(repository.entities.map((entity) => entity.entity_type))].sort(),
    [repository.entities],
  );

  const entities = useMemo(() => {
    const query = search.trim().toLowerCase();
    return repository.entities.filter((entity) => {
      if (type !== "all" && entity.entity_type !== type) return false;
      if (!query) return true;
      return (
        entity.name.toLowerCase().includes(query) ||
        entity.qualified_name.toLowerCase().includes(query) ||
        entity.file_path.toLowerCase().includes(query)
      );
    });
  }, [repository.entities, search, type]);

  return (
    <Section
      title="Discovered entities"
      description="Functions, classes, methods and modules extracted from the Python AST during the last scan."
      actions={
        <div className="flex gap-2">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
            <input
              className="input w-56 pl-9"
              placeholder="Search entities…"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              aria-label="Search entities"
            />
          </div>
          <select
            className="input w-auto"
            value={type}
            onChange={(event) => setType(event.target.value)}
            aria-label="Filter entity type"
          >
            {types.map((item) => (
              <option key={item} value={item}>
                {item === "all" ? "All types" : item}
              </option>
            ))}
          </select>
        </div>
      }
    >
      {entities.length === 0 ? (
        <EmptyState
          title="No matching entities"
          description="Adjust the search or type filter. Entities appear after a successful scan."
        />
      ) : (
        <div className="max-h-[640px] overflow-auto">
          <table className="table-base">
            <thead className="sticky top-0 bg-ink-900">
              <tr>
                <th>Name</th>
                <th>Type</th>
                <th>File</th>
                <th>Lines</th>
                <th>Docstring</th>
              </tr>
            </thead>
            <tbody>
              {entities.map((entity) => (
                <tr key={entity.id}>
                  <td>
                    <p className="font-medium text-slate-200">{entity.name}</p>
                    <p className="font-mono text-[10px] text-slate-500">
                      {entity.qualified_name}
                    </p>
                  </td>
                  <td>
                    <Badge tone={nodeTypeTone(entity.entity_type)}>
                      {entity.entity_type}
                    </Badge>
                  </td>
                  <td className="max-w-[280px] truncate font-mono text-[11px] text-slate-400">
                    {entity.file_path}
                  </td>
                  <td className="whitespace-nowrap text-xs text-slate-500">
                    {entity.line_start ?? "—"}–{entity.line_end ?? "—"}
                  </td>
                  <td className="max-w-[260px] truncate text-xs text-slate-500">
                    {entity.docstring || "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="mt-3 text-xs text-slate-600">
        Showing {entities.length} of {repository.entities.length} entities
      </p>
    </Section>
  );
}

function TestsTab({ repositoryId }: { repositoryId: string }) {
  const tests = useAsync(
    () => Promise.all([api.getRepositoryTests(repositoryId), api.getCoverage(repositoryId)]),
    [repositoryId],
  );
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [collecting, setCollecting] = useState(false);
  const [collectError, setCollectError] = useState<string | null>(null);
  const [collectResult, setCollectResult] = useState<CoverageCollectResult | null>(null);
  const [timeout, setTimeoutValue] = useState(600);
  const [search, setSearch] = useState("");

  async function collectFullCoverage() {
    setCollecting(true);
    setCollectError(null);
    try {
      const result = await api.collectCoverage(repositoryId, {
        confirm: true,
        timeout_seconds: timeout,
      });
      setCollectResult(result);
      setConfirmOpen(false);
      tests.reload();
    } catch (err) {
      setCollectError(
        err instanceof ApiError ? err.message : err instanceof Error ? err.message : String(err),
      );
    } finally {
      setCollecting(false);
    }
  }

  if (tests.loading && !tests.data) return <LoadingBlock label="Loading tests…" />;
  if (tests.error) return <ErrorPanel message={tests.error} onRetry={tests.reload} />;
  if (!tests.data) return null;

  const [discovered, coverage] = tests.data;
  const query = search.trim().toLowerCase();
  const filtered = discovered.tests.filter((test) =>
    query
      ? test.name.toLowerCase().includes(query) ||
        test.file_path.toLowerCase().includes(query) ||
        (test.class_name ?? "").toLowerCase().includes(query)
      : true,
  );

  return (
    <div className="space-y-6">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Discovered tests"
          value={formatCount(discovered.total)}
          icon={<TestTube2 className="h-4 w-4" />}
          tone="emerald"
        />
        <StatCard
          label="Coverage snapshots"
          value={formatCount(coverage.length)}
          icon={<ShieldCheck className="h-4 w-4" />}
          tone="violet"
        />
        <StatCard
          label="Measured tests"
          value={formatCount(coverage[0]?.measured_tests ?? 0)}
          hint="Latest snapshot"
          icon={<GitBranch className="h-4 w-4" />}
          tone="sky"
        />
        <StatCard
          label="Covered files"
          value={formatCount(coverage[0]?.covered_files ?? 0)}
          hint="Latest snapshot"
          icon={<Boxes className="h-4 w-4" />}
          tone="amber"
        />
      </div>

      <Section
        title="Coverage collection"
        description="Runs the repository test suite with a generated pytest plugin that records Coverage.py dynamic contexts per test. Collection executes repository code in a subprocess."
        actions={
          <button type="button" className="btn-primary" onClick={() => setConfirmOpen(true)}>
            <ShieldCheck className="h-4 w-4" />
            Collect coverage
          </button>
        }
      >
        {coverage.length === 0 ? (
          <EmptyState
            title="No coverage snapshots"
            description="Collect per-test coverage once to enable coverage-guided test selection. Without it, analyses use static-evidence selection with an explicit fallback."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="table-base">
              <thead>
                <tr>
                  <th>Collected</th>
                  <th>Status</th>
                  <th>Tests</th>
                  <th>Measured</th>
                  <th>Files</th>
                  <th>Duration</th>
                  <th>Error</th>
                </tr>
              </thead>
              <tbody>
                {coverage.map((snapshot) => (
                  <tr key={snapshot.id}>
                    <td className="text-slate-300">{formatTimestamp(snapshot.collected_at)}</td>
                    <td>
                      <StatusBadge status={snapshot.status} />
                    </td>
                    <td className="text-slate-400">{snapshot.total_tests}</td>
                    <td className="text-slate-400">{snapshot.measured_tests}</td>
                    <td className="text-slate-400">{snapshot.covered_files}</td>
                    <td className="text-slate-400">{formatDuration(snapshot.duration_ms)}</td>
                    <td className="max-w-[220px] truncate text-xs text-rose-300">
                      {snapshot.error_message ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {collectError && (
          <p className="mt-3 rounded-lg border border-rose-500/30 bg-rose-500/5 px-3 py-2 text-sm text-rose-300">
            {collectError}
          </p>
        )}
        {collectResult && (
          <div className="mt-4 space-y-2">
            <p className="text-xs uppercase tracking-wider text-slate-500">
              Collection result
              {collectResult.merged_with_previous ? " · merged with previous snapshot" : ""}
            </p>
            <TestExecutionView execution={collectResult.execution} />
          </div>
        )}
      </Section>

      <Section
        title="Discovered tests"
        description="Pytest test functions and methods detected from the source tree."
        actions={
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
            <input
              className="input w-56 pl-9"
              placeholder="Search tests…"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              aria-label="Search discovered tests"
            />
          </div>
        }
      >
        {filtered.length === 0 ? (
          <EmptyState
            title="No matching tests"
            description="Tests are discovered from files matching pytest conventions (test_*.py, *_test.py and tests/)."
          />
        ) : (
          <div className="max-h-[520px] overflow-auto">
            <table className="table-base">
              <thead className="sticky top-0 bg-ink-900">
                <tr>
                  <th>Test</th>
                  <th>Class</th>
                  <th>File</th>
                  <th>Lines</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((test) => (
                  <tr key={test.node_id}>
                    <td className="font-medium text-slate-200">{test.name}</td>
                    <td className="text-xs text-slate-500">{test.class_name ?? "—"}</td>
                    <td className="max-w-[300px] truncate font-mono text-[11px] text-slate-400">
                      {test.file_path}
                    </td>
                    <td className="text-xs text-slate-500">
                      {test.line_start}–{test.line_end}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="mt-3 text-xs text-slate-600">
          Showing {filtered.length} of {discovered.total} tests
        </p>
      </Section>

      <ConfirmDialog
        open={confirmOpen}
        title="Execute the repository test suite?"
        description={
          <>
            Coverage collection runs repository test code in a subprocess with the
            repository working directory. Only proceed for code you trust.
          </>
        }
        confirmLabel={collecting ? "Collecting…" : "Run and collect"}
        busy={collecting}
        onCancel={() => setConfirmOpen(false)}
        onConfirm={collectFullCoverage}
      >
        <label className="label" htmlFor="coverage-timeout">
          Timeout (seconds)
        </label>
        <input
          id="coverage-timeout"
          type="number"
          min={1}
          max={3600}
          className="input"
          value={timeout}
          onChange={(event) => setTimeoutValue(Number(event.target.value))}
        />
      </ConfirmDialog>
    </div>
  );
}
