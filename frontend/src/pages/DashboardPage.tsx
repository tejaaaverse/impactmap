import { Link } from "react-router-dom";
import {
  Activity,
  ArrowUpRight,
  BarChart3,
  Bot,
  Boxes,
  FlaskConical,
  Gauge,
  GitPullRequest,
  Layers,
  ScanSearch,
  Sparkles,
  Star,
  Timer,
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
import { api } from "../services/api";
import { useAsync } from "../hooks/useAsync";
import { StatCard } from "../components/ui/StatCard";
import { Section } from "../components/ui/Section";
import { LoadingBlock } from "../components/ui/Loading";
import { ErrorPanel } from "../components/ui/ErrorPanel";
import { EmptyState } from "../components/ui/EmptyState";
import { StatusBadge } from "../components/ui/StatusBadge";
import {
  formatCount,
  formatDuration,
  formatPercent,
  formatRelative,
  formatTimestamp,
  shortenPath,
} from "../lib/format";

const chartTooltipStyle = {
  backgroundColor: "#190C1B",
  border: "1px solid rgba(183,139,255,0.35)",
  borderRadius: 8,
  color: "#FCEAF5",
  fontSize: 12,
  boxShadow: "0 18px 50px -18px rgba(233,79,168,0.6)",
};

const QUICK_LINKS = [
  {
    to: "/repositories",
    label: "Repositories",
    hint: "Scan & explore source trees",
    icon: Boxes,
  },
  {
    to: "/analyses",
    label: "Analyses",
    hint: "Inspect impact paths",
    icon: ScanSearch,
  },
  {
    to: "/benchmarks",
    label: "Benchmarks",
    hint: "Compare full vs selected",
    icon: BarChart3,
  },
  {
    to: "/copilot",
    label: "Copilot",
    hint: "Ask your codebase",
    icon: Bot,
  },
];

export function DashboardPage() {
  const { data, loading, error, reload } = useAsync(() => api.getDashboard(), []);

  if (loading && !data) return <LoadingBlock label="Booting your code universe…" />;
  if (error) return <ErrorPanel message={error} onRetry={reload} />;
  if (!data) return null;

  const chartData = data.recent_benchmarks
    .filter(
      (benchmark) =>
        benchmark.full_duration_ms !== null &&
        benchmark.selected_duration_ms !== null,
    )
    .slice()
    .reverse()
    .map((benchmark) => ({
      name: benchmark.dataset_name ?? benchmark.id.slice(0, 8),
      full: Math.round(benchmark.full_duration_ms ?? 0),
      selected: Math.round(benchmark.selected_duration_ms ?? 0),
    }));

  const hasBenchmarks = data.recent_benchmarks.length > 0;

  return (
    <div className="space-y-5">
      <section
        className="y2k-window scanline relative overflow-hidden"
        aria-labelledby="dashboard-hero"
      >
        <div className="y2k-titlebar">
          <span className="flex items-center gap-1" aria-hidden="true">
            <span className="window-control" data-tone="hot" />
            <span className="window-control" data-tone="lav" />
            <span className="window-control" data-tone="mint" />
          </span>
          <span className="pixel-label text-[6px] text-blush">welcome.exe</span>
          <span className="ml-auto hidden items-center gap-1.5 text-[9px] text-mauve sm:inline-flex">
            <span className="h-1 w-1 animate-pulse rounded-full bg-lav" />
            sys.online
          </span>
          <span className="y2k-sticker !px-1.5 !py-0.5 !text-[5px]" data-tone="mint">
            live
          </span>
        </div>

        <div className="relative p-5 sm:p-8">
          <div className="wireframe-horizon" aria-hidden="true">
            <span className="wireframe-sun" />
          </div>

          <div className="relative z-10 grid gap-6 xl:grid-cols-[minmax(0,1fr)_auto] xl:items-end">
            <div className="min-w-0">
              <div className="mb-4 flex flex-wrap items-center gap-3">
                <span className="y2k-sticker text-[6px]">★ new profile</span>
                <span className="pixel-label text-[7px] text-slate-400">
                  sys.online // operational overview
                </span>
                <span className="inline-flex items-center gap-1 rounded-full border border-violet-400/30 bg-violet-400/10 px-2 py-0.5 text-[9px] text-lav">
                  <span className="h-1 w-1 animate-pulse rounded-full bg-lav" />
                  live
                </span>
              </div>

              <h1
                id="dashboard-hero"
                className="pixel-font holo-text text-lg leading-[1.9] sm:text-2xl lg:text-[2.1rem]"
              >
                HELLO, DEVELOPER!
              </h1>
              <p className="mt-3 font-display text-lg font-medium text-blush sm:text-xl">
                Welcome to your code universe.
              </p>
              <p className="mt-1 text-sm font-medium text-lav">
                Explore your repositories. Discover code impact. Make testing
                smarter.
              </p>
              <p className="mt-2 max-w-2xl text-sm leading-relaxed text-slate-400">
                <span className="text-pale">Impact intelligence at a glance</span>
                {" — "}live counts from the IMPACTMAP database, real dependency
                graphs and measured test runs. Nothing here is pre-computed or
                simulated.
              </p>

              <div className="mt-5 flex flex-wrap gap-2">
                <Link to="/repositories" className="btn-primary">
                  <Boxes className="h-4 w-4" aria-hidden="true" />
                  Scan a repository
                </Link>
                <Link to="/benchmarks" className="btn-secondary">
                  <BarChart3 className="h-4 w-4" aria-hidden="true" />
                  Benchmarks
                </Link>
                <Link to="/copilot" className="btn-secondary">
                  <Sparkles className="h-4 w-4" aria-hidden="true" />
                  Ask Copilot
                </Link>
              </div>

              <div className="mt-5 flex flex-wrap gap-x-4 gap-y-2 text-[10px] text-slate-500">
                <span className="inline-flex items-center gap-1.5">
                  <Activity className="h-3 w-3 text-hot" aria-hidden="true" />
                  Real AST + Git diff
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <Layers className="h-3 w-3 text-lav" aria-hidden="true" />
                  Coverage-guided selection
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <Timer className="h-3 w-3 text-blush" aria-hidden="true" />
                  Wall-clock benchmarks
                </span>
              </div>
            </div>

            <div
              className="relative grid grid-cols-2 gap-2 sm:min-w-[310px]"
              aria-label="IMPACTMAP companions"
            >
              <div className="sparkle-decal y2k-bevel relative rounded-xl p-3 text-center">
                <div className="y2k-inset mx-auto grid h-20 w-20 place-items-center rounded-lg">
                  <img
                    src="/assets/rabbit-pixel.svg"
                    alt="Pip the rabbit"
                    className="mascot-sprite h-16 w-16 animate-floaty"
                    draggable={false}
                  />
                </div>
                <p className="pixel-label mt-2 text-[7px] text-hot">PIP</p>
                <p className="mt-1 text-[10px] text-slate-500">
                  curiosity // speed
                </p>
              </div>
              <div className="sparkle-decal y2k-bevel relative rounded-xl p-3 text-center">
                <div className="y2k-inset mx-auto grid h-20 w-20 place-items-center rounded-lg">
                  <img
                    src="/assets/tortoise-pixel.svg"
                    alt="Moss the tortoise"
                    className="mascot-sprite h-16 w-16 animate-floaty [animation-delay:1.4s]"
                    draggable={false}
                  />
                </div>
                <p className="pixel-label mt-2 text-[7px] text-lav">MOSS</p>
                <p className="mt-1 text-[10px] text-slate-500">
                  patience // reliability
                </p>
              </div>
              <p className="col-span-2 mt-1 flex items-center justify-center gap-1.5 text-[9px] text-slate-600">
                <Sparkles className="h-3 w-3 text-hot" aria-hidden="true" />
                your resident code companions
              </p>
            </div>
          </div>

          <div className="relative z-10 mt-6 flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-violet-400/15 pt-3 text-[9px] text-slate-600">
            <span className="pixel-label text-[6px] text-mauve">
              est. 2026 · made with real data
            </span>
            <span className="hidden h-3 w-px bg-violet-400/20 sm:block" />
            <span className="inline-flex items-center gap-1.5">
              <Star className="h-3 w-3 text-hot" aria-hidden="true" />
              best viewed with curiosity
            </span>
            <span className="ml-auto hidden items-center gap-1.5 sm:inline-flex">
              <span className="equalizer" aria-hidden="true">
                <span />
                <span />
                <span />
                <span />
              </span>
              signal: strong
            </span>
          </div>
        </div>
      </section>


      <section className="y2k-window" aria-labelledby="telemetry-heading">
        <div className="y2k-titlebar">
          <span className="flex items-center gap-1" aria-hidden="true">
            <span className="window-control" data-tone="hot" />
            <span className="window-control" data-tone="lav" />
            <span className="window-control" data-tone="mint" />
          </span>
          <h2 id="telemetry-heading" className="pixel-label text-[6px] text-blush">
            system.telemetry
          </h2>
          <span className="ml-auto text-[9px] text-slate-500">
            live · database snapshot
          </span>
        </div>
        <div className="space-y-3 p-3 sm:p-4">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard
              label="Repositories"
              value={formatCount(data.repositories)}
              hint="Python repositories scanned"
              icon={<Boxes className="h-4 w-4" />}
            />
            <StatCard
              label="Analyses"
              value={formatCount(data.analyses)}
              hint={`${data.completed_analyses} completed`}
              icon={<GitPullRequest className="h-4 w-4" />}
              tone="violet"
            />
            <StatCard
              label="Test runs"
              value={formatCount(data.test_runs)}
              hint="Confirmed subprocess executions"
              icon={<FlaskConical className="h-4 w-4" />}
              tone="emerald"
            />
            <StatCard
              label="Avg analysis time"
              value={formatDuration(data.average_analysis_ms)}
              hint="End-to-end impact pipeline"
              icon={<Timer className="h-4 w-4" />}
              tone="amber"
            />
          </div>

          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard
              label="Avg test reduction"
              value={formatPercent(data.average_selection_reduction)}
              hint="From stored selections"
              icon={<Gauge className="h-4 w-4" />}
              tone="emerald"
            />
            <StatCard
              label="Tracked tests"
              value={formatCount(data.total_tracked_tests)}
              hint="Last value per repository"
              icon={<Layers className="h-4 w-4" />}
            />
            <StatCard
              label="Coverage snapshots"
              value={formatCount(data.coverage_snapshots)}
              hint="Per-test coverage collections"
              icon={<Activity className="h-4 w-4" />}
              tone="violet"
            />
            <StatCard
              label="Benchmark runs"
              value={formatCount(data.benchmark_runs)}
              hint="Full vs selected measurements"
              icon={<BarChart3 className="h-4 w-4" />}
              tone="amber"
            />
          </div>
        </div>
      </section>

      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
        {QUICK_LINKS.map(({ to, label, hint, icon: Icon }) => (
          <Link
            key={to}
            to={to}
            className="y2k-bevel group flex items-center gap-3 rounded-xl px-3 py-2.5 transition-all hover:-translate-y-0.5 hover:border-hot/45 hover:shadow-glow"
          >
            <span className="grid h-8 w-8 place-items-center rounded-lg border border-violet-400/25 bg-ink-950/60 text-hot transition-colors group-hover:border-hot/40 group-hover:text-blush">
              <Icon className="h-4 w-4" aria-hidden="true" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block text-xs font-semibold text-pale">{label}</span>
              <span className="block truncate text-[10px] text-slate-500">{hint}</span>
            </span>
            <ArrowUpRight
              className="h-3.5 w-3.5 shrink-0 text-slate-600 transition-colors group-hover:text-hot"
              aria-hidden="true"
            />
          </Link>
        ))}
      </div>

      <div className="mt-6 grid gap-4 xl:grid-cols-2">
        <Section
          title="Measured suite duration"
          description="Wall-clock milliseconds recorded by executing each suite with the same interpreter."
        >
          {chartData.length === 0 ? (
            <EmptyState
              title="No benchmark measurements yet"
              description="Run a benchmark to compare the full suite against coverage-guided selection."
              action={
                <Link to="/benchmarks" className="btn-secondary">
                  Run benchmark
                </Link>
              }
            />
          ) : (
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={chartData}
                  margin={{ top: 8, right: 8, left: -12, bottom: 0 }}
                >
                  <defs>
                    <linearGradient id="dashFull" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#A83D83" />
                      <stop offset="100%" stopColor="#5A2A54" />
                    </linearGradient>
                    <linearGradient id="dashSelected" x1="0" y1="0" x2="0" y2="1">
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
                    width={64}
                  />
                  <Tooltip
                    contentStyle={chartTooltipStyle}
                    cursor={{ fill: "rgba(255,121,201,0.06)" }}
                    formatter={(value) => formatDuration(Number(value))}
                  />
                  <Legend wrapperStyle={{ fontSize: 11, color: "#C99AB9" }} />
                  <Bar
                    dataKey="full"
                    name="Full suite"
                    fill="url(#dashFull)"
                    radius={[4, 4, 0, 0]}
                  />
                  <Bar
                    dataKey="selected"
                    name="Selected suite"
                    fill="url(#dashSelected)"
                    radius={[4, 4, 0, 0]}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </Section>

        <Section
          title="Recent analyses"
          description={
            data.recent_analyses.length
              ? "Latest Git-diff impact runs across all repositories."
              : undefined
          }
          actions={
            <Link
              to="/analyses"
              className="inline-flex items-center gap-1 text-[11px] text-hot hover:text-blush"
            >
              View all <ArrowUpRight className="h-3 w-3" aria-hidden="true" />
            </Link>
          }
        >
          {data.recent_analyses.length === 0 ? (
            <EmptyState
              title="No analyses yet"
              description="Scan a repository, then run an impact analysis against a Git diff."
              action={
                <Link to="/repositories" className="btn-secondary">
                  Open repositories
                </Link>
              }
            />
          ) : (
            <ul className="divide-y divide-violet-400/10">
              {data.recent_analyses.map((analysis) => (
                <li key={analysis.id}>
                  <Link
                    to={`/analyses/${analysis.id}`}
                    className="flex items-center justify-between gap-3 rounded-lg px-1 py-3 transition-colors hover:bg-rose-500/5"
                  >
                    <div className="min-w-0">
                      <p className="truncate font-mono text-xs text-blush">
                        {analysis.base_ref} → {analysis.head_ref}
                      </p>
                      <p className="mt-1 text-[11px] text-slate-500">
                        {formatTimestamp(analysis.created_at)} ·{" "}
                        {analysis.total_changed_files} files ·{" "}
                        {analysis.total_affected_entities} affected
                      </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      <StatusBadge status={analysis.status} />
                      <span className="text-[11px] text-slate-500">
                        {formatDuration(analysis.analysis_duration_ms)}
                      </span>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Section>
      </div>

      {hasBenchmarks && (
        <Section
          className="mt-4"
          title="Recent benchmark runs"
          description="Precision and recall compare the selected suite with tests that actually executed changed code."
          actions={
            <Link
              to="/benchmarks"
              className="inline-flex items-center gap-1 text-[11px] text-hot hover:text-blush"
            >
              View all <ArrowUpRight className="h-3 w-3" aria-hidden="true" />
            </Link>
          }
        >
          <div className="overflow-x-auto">
            <table className="table-base">
              <thead>
                <tr>
                  <th>Benchmark</th>
                  <th>Mode</th>
                  <th>Full</th>
                  <th>Selected</th>
                  <th>Reduction</th>
                  <th>Precision</th>
                  <th>Recall</th>
                  <th>When</th>
                </tr>
              </thead>
              <tbody>
                {data.recent_benchmarks.map((benchmark) => (
                  <tr key={benchmark.id}>
                    <td className="font-mono text-xs text-blush">
                      {benchmark.dataset_name ?? shortenPath(benchmark.id, 16)}
                    </td>
                    <td>
                      <StatusBadge status={benchmark.mode} />
                    </td>
                    <td className="text-slate-400">
                      {formatDuration(benchmark.full_duration_ms)}
                    </td>
                    <td className="text-slate-400">
                      {formatDuration(benchmark.selected_duration_ms)}
                    </td>
                    <td className="text-hot">
                      {formatPercent(benchmark.reduction_percent)}
                    </td>
                    <td className="text-slate-400">
                      {formatPercent(benchmark.selection_precision)}
                    </td>
                    <td className="text-slate-400">
                      {formatPercent(benchmark.selection_recall)}
                    </td>
                    <td className="text-slate-500">
                      {formatRelative(benchmark.created_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
      )}
    </div>
  );
}
