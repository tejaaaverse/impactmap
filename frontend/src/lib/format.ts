/** Formatting helpers shared by pages and components. */

export function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || Number.isNaN(ms)) return "—";
  if (ms < 1) return "<1 ms";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 2 : 1)} s`;
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.round(seconds % 60);
  return `${minutes}m ${remainder}s`;
}

export function formatPercent(
  value: number | null | undefined,
  digits = 1,
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${value.toFixed(digits)}%`;
}

export function formatCount(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("en-US").format(value);
}

export function formatTimestamp(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatRelative(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const diff = Date.now() - date.getTime();
  const seconds = Math.round(diff / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days}d ago`;
  return formatTimestamp(value);
}

/** Shorten long repository-relative paths while keeping the file name visible. */
export function shortenPath(path: string, max = 48): string {
  if (path.length <= max) return path;
  const parts = path.split("/");
  const file = parts[parts.length - 1] ?? path;
  const head = parts[0] ?? "";
  const candidate = `${head}/…/${file}`;
  if (candidate.length <= max) return candidate;
  return `…/${file}`;
}

export function truncate(value: string, max = 80): string {
  if (value.length <= max) return value;
  return `${value.slice(0, max - 1)}…`;
}

export type Tone = "sky" | "emerald" | "amber" | "rose" | "slate" | "violet";

export function statusTone(status: string | null | undefined): Tone {
  switch ((status ?? "").toLowerCase()) {
    case "completed":
    case "passed":
    case "success":
    case "ok":
    case "clean":
      return "emerald";
    case "running":
    case "pending":
    case "queued":
      return "sky";
    case "failed":
    case "error":
    case "timed_out":
      return "rose";
    case "partial":
    case "warning":
    case "fallback":
      return "amber";
    default:
      return "slate";
  }
}

export function nodeTypeTone(type: string): Tone {
  switch (type) {
    case "class":
      return "violet";
    case "function":
    case "method":
      return "sky";
    case "test":
      return "emerald";
    case "module":
      return "amber";
    default:
      return "slate";
  }
}

export const TONE_CLASSES: Record<Tone, string> = {
  sky: "border-sky-500/30 bg-sky-500/10 text-sky-300",
  emerald: "border-emerald-500/30 bg-emerald-500/10 text-emerald-300",
  amber: "border-amber-500/30 bg-amber-500/10 text-amber-300",
  rose: "border-rose-500/30 bg-rose-500/10 text-rose-300",
  slate: "border-slate-600/40 bg-slate-600/10 text-slate-300",
  violet: "border-violet-500/30 bg-violet-500/10 text-violet-300",
};

export function parseList(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}
