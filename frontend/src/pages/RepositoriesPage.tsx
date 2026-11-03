import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Activity,
  Boxes,
  CalendarClock,
  FileCode2,
  FolderGit2,
  FolderSearch,
  GitBranch,
  Plus,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import { api, ApiError } from "../services/api";
import { useAsync } from "../hooks/useAsync";
import { PageHeader } from "../components/ui/PageHeader";
import { Section } from "../components/ui/Section";
import { LoadingBlock } from "../components/ui/Loading";
import { ErrorPanel } from "../components/ui/ErrorPanel";
import { EmptyState } from "../components/ui/EmptyState";
import { StatusBadge } from "../components/ui/StatusBadge";
import {
  formatCount,
  formatRelative,
  formatTimestamp,
  shortenPath,
} from "../lib/format";

export function RepositoriesPage() {
  const navigate = useNavigate();
  const repositories = useAsync(() => api.listRepositories(), []);
  const [path, setPath] = useState("");
  const [busy, setBusy] = useState(false);
  const [scanError, setScanError] = useState<string | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);

  async function handleScan(event: React.FormEvent) {
    event.preventDefault();
    if (!path.trim()) {
      setScanError("Enter an absolute path to a local Python repository.");
      return;
    }
    setBusy(true);
    setScanError(null);
    setWarnings([]);
    try {
      const result = await api.scanRepository(path.trim());
      setWarnings(result.warnings);
      setPath("");
      repositories.reload();
      navigate(`/repositories/${result.repository.id}`);
    } catch (err) {
      setScanError(
        err instanceof ApiError ? err.message : err instanceof Error ? err.message : String(err),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <PageHeader
        eyebrow="Source inventory"
        title="Repositories"
        subtitle="Scan a local Python repository to build its AST symbol graph and prepare it for Git-diff impact analysis."
        actions={
          <>
            <span className="hidden items-center gap-1.5 rounded-full border border-violet-400/25 bg-violet-400/10 px-2.5 py-1.5 text-[10px] text-lav sm:inline-flex">
              <Sparkles className="h-3 w-3" aria-hidden="true" />
              {repositories.data?.length ?? 0} in orbit
            </span>
            <button type="button" className="btn-secondary" onClick={repositories.reload}>
              <RefreshCw className="h-4 w-4" aria-hidden="true" />
              Refresh
            </button>
          </>
        }
      />

      <Section
        title="Scan a local repository"
        description="Files are parsed with Python's AST. Existing repository paths are rescanned in place."
      >
        <form onSubmit={handleScan} className="flex flex-col gap-3 sm:flex-row">
          <div className="relative flex-1">
            <FolderSearch
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500"
              aria-hidden="true"
            />
            <input
              className="input pl-9 font-mono text-xs"
              placeholder="/absolute/path/to/python-repository"
              value={path}
              onChange={(event) => setPath(event.target.value)}
              aria-label="Repository path"
              spellCheck={false}
              disabled={busy}
            />
          </div>
          <button type="submit" className="btn-primary" disabled={busy} aria-busy={busy}>
            <Plus className="h-4 w-4" aria-hidden="true" />
            {busy ? "Scanning…" : "Scan repository"}
          </button>
        </form>

        {busy && (
          <div className="mt-4" role="status" aria-live="polite">
            <div className="scan-progress">
              <span />
            </div>
            <p className="pixel-label mt-2 flex items-center gap-2 text-[7px] text-hot">
              <Activity className="h-3 w-3 animate-pulse" aria-hidden="true" />
              parsing AST · mapping symbols · resolving dependencies
            </p>
          </div>
        )}

        {scanError && (
          <p className="mt-3 rounded-lg border border-rose-400/35 bg-rose-500/10 px-3 py-2 text-sm text-rose-200">
            {scanError}
          </p>
        )}
        {warnings.length > 0 && (
          <ul className="mt-3 space-y-1 rounded-lg border border-violet-400/25 bg-violet-400/10 px-3 py-2 text-xs text-blush">
            {warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        )}
      </Section>

      <div className="mt-6">
        {repositories.loading && !repositories.data ? (
          <LoadingBlock label="Loading repositories…" />
        ) : repositories.error ? (
          <ErrorPanel message={repositories.error} onRetry={repositories.reload} />
        ) : !repositories.data || repositories.data.length === 0 ? (
          <EmptyState
            icon={<Boxes className="h-5 w-5" />}
            title="No repositories scanned"
            description="Enter an absolute path above to scan your first Python repository. The sample calculator lives under sample_repositories/calculator."
          />
        ) : (
          <div className="grid gap-3 lg:grid-cols-2 xl:grid-cols-3">
            {repositories.data.map((repo) => (
              <Link
                key={repo.id}
                to={`/repositories/${repo.id}`}
                className="y2k-bevel pixel-corners group relative flex flex-col overflow-hidden rounded-xl p-4 transition-all duration-300 hover:-translate-y-0.5 hover:border-hot/45 hover:shadow-glow"
              >
                <span
                  aria-hidden="true"
                  className="pointer-events-none absolute -right-10 -top-12 h-28 w-28 rounded-full bg-gradient-to-br from-rose-500/25 to-violet-400/15 blur-2xl transition-opacity group-hover:opacity-90"
                />
                <div className="relative mb-3 flex items-center justify-between gap-2 border-b border-violet-400/15 pb-2">
                  <span className="pixel-label text-[5px] text-slate-600">
                    repo://{repo.id.slice(0, 8)}
                  </span>
                  <span className="flex items-center gap-1" aria-hidden="true">
                    <span className="h-1 w-1 bg-hot/70" />
                    <span className="h-1 w-1 bg-lav/60" />
                    <span className="h-1 w-1 bg-blush/50" />
                  </span>
                </div>
                <div className="relative flex items-start justify-between gap-2">
                  <div className="flex min-w-0 items-start gap-3">
                    <span className="mt-0.5 rounded-lg border border-hot/35 bg-gradient-to-br from-neon/15 to-violet-400/10 p-2 text-hot shadow-glow">
                      <FolderGit2 className="h-4 w-4" aria-hidden="true" />
                    </span>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold text-pale transition-colors group-hover:text-blush">
                        {repo.name}
                      </p>
                      <p
                        className="mt-0.5 truncate font-mono text-[10px] text-slate-500"
                        title={repo.path}
                      >
                        {shortenPath(repo.path, 54)}
                      </p>
                    </div>
                  </div>
                  <StatusBadge status={repo.status} />
                </div>

                <div className="relative mt-4 grid grid-cols-4 gap-1.5 text-center">
                  {[
                    { label: "Files", value: repo.total_files, icon: FileCode2 },
                    { label: "Funcs", value: repo.total_functions, icon: GitBranch },
                    { label: "Classes", value: repo.total_classes, icon: Boxes },
                    { label: "Deps", value: repo.total_dependencies, icon: CalendarClock },
                  ].map(({ label, value, icon: Icon }) => (
                    <div
                      key={label}
                      className="rounded-lg border border-violet-400/15 bg-ink-950/50 px-1.5 py-2"
                    >
                      <Icon
                        className="mx-auto mb-1 h-3 w-3 text-slate-600"
                        aria-hidden="true"
                      />
                      <p className="stat-value text-sm font-semibold text-blush">
                        {formatCount(value)}
                      </p>
                      <p className="pixel-label mt-0.5 text-[6px] text-slate-600">{label}</p>
                    </div>
                  ))}
                </div>

                <div className="relative mt-3 flex items-center justify-between border-t border-violet-400/15 pt-3 text-[10px] text-slate-500">
                  <span>Scanned {formatRelative(repo.last_scanned_at)}</span>
                  <span className="font-mono">{formatTimestamp(repo.updated_at)}</span>
                </div>
                {repo.scan_error && (
                  <p
                    className="relative mt-2 truncate text-xs text-rose-300"
                    title={repo.scan_error}
                  >
                    {repo.scan_error}
                  </p>
                )}
              </Link>
            ))}
          </div>
        )}
      </div>

      {repositories.data && repositories.data.length > 0 && (
        <p className="pixel-label mt-4 text-right text-[7px] text-slate-600">
          {repositories.data.length} repositories · scan durations recorded per run
        </p>
      )}
    </div>
  );
}
