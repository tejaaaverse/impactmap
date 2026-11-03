import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  BarChart3,
  FlaskConical,
  PlayCircle,
  RefreshCw,
  Timer,
  TrendingDown,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, ApiError } from "../services/api";
import { useAsync } from "../hooks/useAsync";
import { PageHeader } from "../components/ui/PageHeader";
import { Section } from "../components/ui/Section";
import { LoadingBlock } from "../components/ui/Loading";
import { ErrorPanel } from "../components/ui/ErrorPanel";
import { EmptyState } from "../components/ui/EmptyState";
import { StatusBadge } from "../components/ui/StatusBadge";
import { StatCard } from "../components/ui/StatCard";
import { ConfirmDialog } from "../components/ui/ConfirmDialog";
import { TestExecutionView } from "../components/TestExecutionView";
import {
  formatDuration,
  formatPercent,
  formatTimestamp,
  shortenPath,
} from "../lib/format";
import type { BenchmarkDetail } from "../types";

const tooltipStyle = {
  backgroundColor: "#190C1B",
  border: "1px solid rgba(183,139,255,0.35)",
  borderRadius: 8,
  color: "#FCEAF5",
  fontSize: 12,
  boxShadow: "0 18px 50px -18px rgba(233,79,168,0.6)",
};

function average(values: (number | null)[]): number | null {
  const numbers = values.filter((value): value is number => value !== null);
  if (numbers.length === 0) return null;
  return numbers.reduce((sum, value) => sum + value, 0) / numbers.length;
}

export function BenchmarksPage() {
  const data = useAsync(
    () => Promise.all([api.listBenchmarks(), api.listRepositories(), api.listAnalyses()]),
    [],
  );
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [repositoryId, setRepositoryId] = useState("");
  const [analysisId, setAnalysisId] = useState("");
  const [baseRef, setBaseRef] = useState("HEAD~1");
  const [headRef, setHeadRef] = useState("WORKING");
  const [mode, setMode] = useState<"safe" | "optimized">("optimized");
  const [datasetName, setDatasetName] = useState("");
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [timeout, setTimeoutValue] = useState(900);

  const benchmarks = data.data?.[0].benchmarks ?? [];
  const repositories = data.data?.[1] ?? [];
  const analyses = data.data?.[2].analyses ?? [];

  const repoAnalyses = useMemo(
    () => analyses.filter((analysis) => analysis.repository_id === repositoryId),
    [analyses, repositoryId],
  );

  const chartData = useMemo(
    () =>
      benchmarks
        .filter(
          (benchmark) =>
            benchmark.full_duration_ms !== null &&
            benchmark.selected_duration_ms !== null,
        )
        .slice(0, 12)
        .reverse()
        .map((benchmark) => ({
          name: benchmark.dataset_name ?? benchmark.id.slice(0, 8),
          full: Math.round(benchmark.full_duration_ms ?? 0),
          selected: Math.round(benchmark.selected_duration_ms ?? 0),
        })),
    [benchmarks],
  );

  const avgReduction = average(benchmarks.map((benchmark) => benchmark.reduction_percent));
  const avgPrecision = average(benchmarks.map((benchmark) => benchmark.selection_precision));
  const avgRecall = average(benchmarks.map((benchmark) => benchmark.selection_recall));

  async function runBenchmark() {
    if (!repositoryId) {
      setRunError("Select a repository first.");
      return;
    }
    setRunning(true);
    setRunError(null);
    try {
      const result = await api.runBenchmark({
        repository_id: repositoryId,
        analysis_id: analysisId || null,
        base_ref: baseRef || "HEAD~1",
        head_ref: headRef || "WORKING",
        mode,
        dataset_name: datasetName.trim() || null,
        confirm: true,
        timeout_seconds: timeout,
      });
      setSelectedId(result.id);
      setConfirmOpen(false);
      data.reload();
    } catch (err) {
      setRunError(
        err instanceof ApiError ? err.message : err instanceof Error ? err.message : String(err),
      );
    } finally {
      setRunning(false);
    }
  }

  if (data.loading && !data.data) return <LoadingBlock label="Loading benchmarks…" />;
  if (data.error) return <ErrorPanel message={data.error} onRetry={data.reload} />;
  if (!data.data) return null;

  return (
    <div>
      <PageHeader
        eyebrow="Measurement"
        title="Benchmarks"
        subtitle="Every benchmark executes both the full suite and the selected suite with the same interpreter, working directory and timeout. Durations are measured, not estimated."
        actions={
          <>
            <span className="hidden items-center gap-1.5 rounded-full border border-violet-400/25 bg-violet-400/10 px-2.5 py-1.5 text-[10px] text-lav sm:inline-flex">
              <FlaskConical className="h-3 w-3" aria-hidden="true" />
              {benchmarks.length} measured run{benchmarks.length === 1 ? "" : "s"}
            </span>
            <button type="button" className="btn-secondary" onClick={data.reload}>
              <RefreshCw className="h-4 w-4" aria-hidden="true" />
              Refresh
            </button>
          </>
        }
      />

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Benchmark runs"
          value={benchmarks.length}
          icon={<BarChart3 className="h-4 w-4" />}
        />
        <StatCard
          label="Avg duration reduction"
          value={formatPercent(avgReduction)}
          icon={<TrendingDown className="h-4 w-4" />}
          tone="emerald"
        />
        <StatCard
          label="Avg selection precision"
          value={formatPercent(avgPrecision)}
          icon={<FlaskConical className="h-4 w-4" />}
          tone="violet"
        />
        <StatCard
          label="Avg selection recall"
          value={formatPercent(avgRecall)}
          icon={<Timer className="h-4 w-4" />}
          tone="amber"
        />
      </div>

      <div className="mt-6 grid gap-4 xl:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)]">
        <Section
          title="Run a benchmark"
          description="A fresh analysis is created when no existing analysis is selected."
        >
          <form
            className="space-y-3"
            onSubmit={(event) => {
              event.preventDefault();
              setConfirmOpen(true);
            }}
          >
            <div>
              <label className="label" htmlFor="benchmark-repository">
                Repository
              </label>
              <select
                id="benchmark-repository"
                className="input"
                value={repositoryId}
                onChange={(event) => {
                  setRepositoryId(event.target.value);
                  setAnalysisId("");
                }}
              >
                <option value="">Select a repository…</option>
                {repositories.map((repo) => (
                  <option key={repo.id} value={repo.id}>
                    {repo.name}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="label" htmlFor="benchmark-analysis">
                Existing analysis (optional)
              </label>
              <select
                id="benchmark-analysis"
                className="input"
                value={analysisId}
                onChange={(event) => setAnalysisId(event.target.value)}
                disabled={!repositoryId}
              >
                <option value="">Create a fresh analysis</option>
                {repoAnalyses.map((analysis) => (
                  <option key={analysis.id} value={analysis.id}>
                    {analysis.base_ref} → {analysis.head_ref} ·{" "}
                    {formatTimestamp(analysis.created_at)}
                  </option>
                ))}
              </select>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="label" htmlFor="benchmark-base">
                  Base ref
                </label>
                <input
                  id="benchmark-base"
                  className="input font-mono text-xs"
                  value={baseRef}
                  onChange={(event) => setBaseRef(event.target.value)}
                />
              </div>
              <div>
                <label className="label" htmlFor="benchmark-head">
                  Head ref
                </label>
                <input
                  id="benchmark-head"
                  className="input font-mono text-xs"
                  value={headRef}
                  onChange={(event) => setHeadRef(event.target.value)}
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="label" htmlFor="benchmark-mode">
                  Selection mode
                </label>
                <select
                  id="benchmark-mode"
                  className="input"
                  value={mode}
                  onChange={(event) => setMode(event.target.value as "safe" | "optimized")}
                >
                  <option value="optimized">Optimized</option>
                  <option value="safe">Safe</option>
                </select>
              </div>
              <div>
                <label className="label" htmlFor="benchmark-timeout">
                  Timeout (s)
                </label>
                <input
                  id="benchmark-timeout"
                  type="number"
                  min={1}
                  max={7200}
                  className="input"
                  value={timeout}
                  onChange={(event) => setTimeoutValue(Number(event.target.value))}
                />
              </div>
            </div>

            <div>
              <label className="label" htmlFor="benchmark-dataset">
                Dataset label (optional)
              </label>
              <input
                id="benchmark-dataset"
                className="input"
                placeholder="e.g. calculator-refactor"
                value={datasetName}
                onChange={(event) => setDatasetName(event.target.value)}
              />
            </div>

            {runError && (
              <p className="rounded-lg border border-rose-500/30 bg-rose-500/5 px-3 py-2 text-xs text-rose-300">
                {runError}
              </p>
            )}
            <button type="submit" className="btn-primary w-full" disabled={!repositoryId || running}>
              <PlayCircle className="h-4 w-4" />
              {running ? "Measuring…" : "Run benchmark"}
            </button>
            <p className="text-[11px] leading-relaxed text-slate-500">
              The full suite runs first, then the selected suite. Both execute repository
              code in subprocesses.
            </p>
          </form>

          <ConfirmDialog
            open={confirmOpen}
            title="Execute both test suites?"
            description="The full suite and the selected suite will run in separate subprocesses. This executes repository test code; only proceed for trusted repositories."
            confirmLabel={running ? "Measuring…" : "Run benchmark"}
            busy={running}
            onCancel={() => setConfirmOpen(false)}
            onConfirm={runBenchmark}
          />
        </Section>

        <Section
          title="Duration comparison"
          description="Full suite versus selected suite, in milliseconds."
        >
          {chartData.length === 0 ? (
            <EmptyState
              title="No measurements yet"
              description="Run a benchmark to produce a real full-versus-selected timing comparison."
            />
          ) : (
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
                  <defs>
                    <linearGradient id="benchFull" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#A83D83" />
                      <stop offset="100%" stopColor="#5A2A54" />
                    </linearGradient>
                    <linearGradient id="benchSelected" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#FF79C9" />
                      <stop offset="100%" stopColor="#B78BFF" />
                    </linearGradient>
                  </defs>
                  <CartesianGrid
                    stroke="rgba(183,139,255,0.14)"
                    strokeDasharray="3 3"
                    vertical={false}
                  />
                  <XAxis
                    dataKey="name"
                    tick={{ fill: "#C99AB9", fontSize: 10, fontFamily: "JetBrains Mono" }}
                  />
                  <YAxis
                    tick={{ fill: "#C99AB9", fontSize: 10, fontFamily: "JetBrains Mono" }}
                    unit="ms"
                    width={66}
                  />
                  <Tooltip
                    contentStyle={tooltipStyle}
                    cursor={{ fill: "rgba(255,121,201,0.06)" }}
                    formatter={(value) => formatDuration(Number(value))}
                  />
                  <Legend wrapperStyle={{ fontSize: 11, color: "#C99AB9" }} />
                  <Bar
                    dataKey="full"
                    name="Full suite"
                    fill="url(#benchFull)"
                    radius={[4, 4, 0, 0]}
                  />
                  <Bar
                    dataKey="selected"
                    name="Selected suite"
                    fill="url(#benchSelected)"
                    radius={[4, 4, 0, 0]}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </Section>
      </div>

      <div className="mt-4">
        <Section
          title="Benchmark history"
          description="Precision and recall compare selected tests against tests that actually executed changed production code during the full run."
        >
          {benchmarks.length === 0 ? (
            <EmptyState
              title="No benchmark runs"
              description="Select a repository above and run the first measurement."
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="table-base">
                <thead>
                  <tr>
                    <th>Dataset</th>
                    <th>Repository</th>
                    <th>Diff</th>
                    <th>Mode</th>
                    <th>Tests</th>
                    <th>Full</th>
                    <th>Selected</th>
                    <th>Reduction</th>
                    <th>Precision</th>
                    <th>Recall</th>
                    <th>When</th>
                  </tr>
                </thead>
                <tbody>
                  {benchmarks.map((benchmark) => {
                    const repo = repositories.find(
                      (item) => item.id === benchmark.repository_id,
                    );
                    return (
                      <tr
                        key={benchmark.id}
                        className="cursor-pointer"
                        onClick={() =>
                          setSelectedId(selectedId === benchmark.id ? null : benchmark.id)
                        }
                      >
                        <td className="font-mono text-[11px] text-hot">
                          {benchmark.dataset_name ?? shortenPath(benchmark.id, 14)}
                        </td>
                        <td className="text-xs text-slate-300">
                          {repo?.name ?? benchmark.repository_id}
                        </td>
                        <td className="whitespace-nowrap font-mono text-[10px] text-slate-500">
                          {benchmark.base_ref} → {benchmark.head_ref}
                        </td>
                        <td>
                          <StatusBadge status={benchmark.mode} />
                        </td>
                        <td className="text-xs text-slate-400">
                          {benchmark.selected_tests}/{benchmark.total_tests}
                        </td>
                        <td className="text-xs text-slate-400">
                          {formatDuration(benchmark.full_duration_ms)}
                        </td>
                        <td className="text-xs text-slate-400">
                          {formatDuration(benchmark.selected_duration_ms)}
                        </td>
                        <td className="text-xs text-lav">
                          {formatPercent(benchmark.reduction_percent)}
                        </td>
                        <td className="text-xs text-slate-400">
                          {formatPercent(benchmark.selection_precision)}
                        </td>
                        <td className="text-xs text-slate-400">
                          {formatPercent(benchmark.selection_recall)}
                        </td>
                        <td className="whitespace-nowrap text-[11px] text-slate-500">
                          {formatTimestamp(benchmark.created_at)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
          {benchmarks.length > 0 && (
            <p className="mt-3 text-xs text-slate-600">
              Select a row to load its stored execution details.{" "}
              <Link to="/analyses" className="text-hot hover:text-blush">
                Inspect analyses
              </Link>
            </p>
          )}
        </Section>
      </div>

      {selectedId && <BenchmarkDetailPanel benchmarkId={selectedId} />}
    </div>
  );
}

function BenchmarkDetailPanel({ benchmarkId }: { benchmarkId: string }) {
  const detail = useAsync(() => api.getBenchmark(benchmarkId), [benchmarkId]);

  if (detail.loading && !detail.data) return <LoadingBlock label="Loading benchmark detail…" />;
  if (detail.error) return <ErrorPanel message={detail.error} onRetry={detail.reload} />;
  if (!detail.data) return null;

  const benchmark: BenchmarkDetail = detail.data;
  return (
    <Section
      className="mt-4"
      title={`Benchmark ${benchmark.dataset_name ?? benchmark.id.slice(0, 12)}`}
      description={`${benchmark.mode} mode · ${formatTimestamp(benchmark.created_at)}`}
      actions={<StatusBadge status={benchmark.error_message ? "failed" : "completed"} />}
    >
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <StatCard label="Full suite" value={formatDuration(benchmark.full_duration_ms)} />
        <StatCard
          label="Selected suite"
          value={formatDuration(benchmark.selected_duration_ms)}
          tone="sky"
        />
        <StatCard
          label="Reduction"
          value={formatPercent(benchmark.reduction_percent)}
          tone="emerald"
        />
        <StatCard
          label="Precision"
          value={formatPercent(benchmark.selection_precision)}
          tone="violet"
        />
        <StatCard
          label="Recall"
          value={formatPercent(benchmark.selection_recall)}
          tone="amber"
        />
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <div>
          <p className="pixel-label mb-2 text-[7px] text-slate-400">
            Full suite execution
          </p>
          {benchmark.full_run ? (
            <TestExecutionView execution={benchmark.full_run} />
          ) : (
            <p className="text-xs text-slate-500">No execution payload stored.</p>
          )}
        </div>
        <div>
          <p className="pixel-label mb-2 text-[7px] text-slate-400">
            Selected suite execution
          </p>
          {benchmark.selected_run ? (
            <TestExecutionView execution={benchmark.selected_run} />
          ) : (
            <p className="text-xs text-slate-500">No execution payload stored.</p>
          )}
        </div>
      </div>

      {benchmark.notes && Object.keys(benchmark.notes).length > 0 && (
        <div className="mt-4">
          <p className="pixel-label mb-2 text-[7px] text-slate-400">
            Notes
          </p>
          <pre className="overflow-auto rounded-lg border border-violet-400/20 bg-ink-950/80 p-3 font-mono text-[11px] text-slate-400">
            {JSON.stringify(benchmark.notes, null, 2)}
          </pre>
        </div>
      )}
      {benchmark.error_message && (
        <p className="mt-3 rounded-lg border border-rose-500/30 bg-rose-500/5 px-3 py-2 text-xs text-rose-300">
          {benchmark.error_message}
        </p>
      )}
    </Section>
  );
}
