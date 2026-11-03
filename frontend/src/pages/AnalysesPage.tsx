import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Activity, GitPullRequest, RefreshCw, ScanSearch, Target } from "lucide-react";
import { api } from "../services/api";
import { useAsync } from "../hooks/useAsync";
import { PageHeader } from "../components/ui/PageHeader";
import { Section } from "../components/ui/Section";
import { LoadingBlock } from "../components/ui/Loading";
import { ErrorPanel } from "../components/ui/ErrorPanel";
import { EmptyState } from "../components/ui/EmptyState";
import { StatusBadge } from "../components/ui/StatusBadge";
import { formatDuration, formatTimestamp } from "../lib/format";

export function AnalysesPage() {
  const [repositoryFilter, setRepositoryFilter] = useState("all");
  const data = useAsync(
    () => Promise.all([api.listAnalyses(), api.listRepositories()]),
    [],
  );

  const rows = useMemo(() => {
    if (!data.data) return [];
    const [analyses, repositories] = data.data;
    const names = new Map(repositories.map((repo) => [repo.id, repo.name]));
    return analyses.analyses
      .filter(
        (analysis) =>
          repositoryFilter === "all" || analysis.repository_id === repositoryFilter,
      )
      .map((analysis) => ({
        ...analysis,
        repositoryName: names.get(analysis.repository_id) ?? analysis.repository_id,
      }));
  }, [data.data, repositoryFilter]);

  if (data.loading && !data.data) return <LoadingBlock label="Loading analyses…" />;
  if (data.error) return <ErrorPanel message={data.error} onRetry={data.reload} />;
  if (!data.data) return null;

  const [, repositories] = data.data;
  const completed = rows.filter((row) => row.status === "completed").length;
  const affected = rows.reduce((sum, row) => sum + row.total_affected_entities, 0);
  const changed = rows.reduce((sum, row) => sum + row.total_changed_files, 0);

  return (
    <div>
      <PageHeader
        eyebrow="History"
        title="Analyses"
        subtitle="Each run stores the Git diff, changed entities, impact traversal and both test-selection modes."
        actions={
          <>
            <button type="button" className="btn-secondary" onClick={data.reload}>
              <RefreshCw className="h-4 w-4" aria-hidden="true" />
              Refresh
            </button>
            <Link to="/repositories" className="btn-primary">
              <ScanSearch className="h-4 w-4" aria-hidden="true" />
              New analysis
            </Link>
          </>
        }
      />

      <div className="mb-4 grid gap-2 sm:grid-cols-3">
        {[
          {
            label: "Runs in view",
            value: rows.length,
            hint: `${completed} completed`,
            icon: Activity,
          },
          {
            label: "Changed files",
            value: changed,
            hint: "Across visible runs",
            icon: GitPullRequest,
          },
          {
            label: "Affected entities",
            value: affected,
            hint: "Reverse dependency hits",
            icon: Target,
          },
        ].map(({ label, value, hint, icon: Icon }) => (
          <div
            key={label}
            className="y2k-bevel flex items-center gap-3 rounded-xl px-3 py-2.5"
          >
            <span className="grid h-8 w-8 place-items-center rounded-lg border border-violet-400/25 bg-ink-950/60 text-hot">
              <Icon className="h-4 w-4" aria-hidden="true" />
            </span>
            <div>
              <p className="stat-value text-lg font-bold text-pale">{value}</p>
              <p className="pixel-label text-[6px] text-slate-500">
                {label} · {hint}
              </p>
            </div>
          </div>
        ))}
      </div>

      <Section
        title="Impact analyses"
        description={
          rows.length
            ? "Open a run to inspect its impact paths, selected tests and execution history."
            : undefined
        }
        actions={
          <select
            className="input w-auto"
            value={repositoryFilter}
            onChange={(event) => setRepositoryFilter(event.target.value)}
            aria-label="Filter by repository"
          >
            <option value="all">All repositories</option>
            {repositories.map((repo) => (
              <option key={repo.id} value={repo.id}>
                {repo.name}
              </option>
            ))}
          </select>
        }
      >
        {rows.length === 0 ? (
          <EmptyState
            icon={<ScanSearch className="h-5 w-5" />}
            title="No analyses recorded"
            description="Open a repository and run an impact analysis against a Git diff. Results will appear here with selection and test-run history."
            action={
              <Link to="/repositories" className="btn-secondary">
                Go to repositories
              </Link>
            }
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="table-base">
              <thead>
                <tr>
                  <th>Repository</th>
                  <th>Diff</th>
                  <th>Status</th>
                  <th>Changed files</th>
                  <th>Affected entities</th>
                  <th>Duration</th>
                  <th>Created</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {rows.map((analysis) => (
                  <tr key={analysis.id}>
                    <td className="font-medium text-pale">{analysis.repositoryName}</td>
                    <td className="whitespace-nowrap font-mono text-[11px] text-blush">
                      {analysis.base_ref} → {analysis.head_ref}
                    </td>
                    <td>
                      <StatusBadge status={analysis.status} />
                    </td>
                    <td className="text-slate-400">{analysis.total_changed_files}</td>
                    <td className="text-slate-400">
                      {analysis.total_affected_entities}
                    </td>
                    <td className="text-slate-400">
                      {formatDuration(analysis.analysis_duration_ms)}
                    </td>
                    <td className="whitespace-nowrap text-xs text-slate-500">
                      {formatTimestamp(analysis.created_at)}
                    </td>
                    <td className="text-right">
                      <Link
                        to={`/analyses/${analysis.id}`}
                        className="text-xs font-medium text-hot hover:text-blush"
                      >
                        Inspect
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {rows.length > 0 && (
          <p className="pixel-label mt-3 text-[7px] text-slate-600">
            {rows.length} run{rows.length === 1 ? "" : "s"} shown, newest first
          </p>
        )}
      </Section>
    </div>
  );
}
