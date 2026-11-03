import type { ReactNode } from "react";
import { Sparkles } from "lucide-react";

export function PageHeader({
  title,
  subtitle,
  actions,
  eyebrow,
}: {
  title: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
  eyebrow?: string;
}) {
  return (
    <div className="y2k-window relative mb-6 overflow-hidden">
      <div className="y2k-titlebar">
        <span className="flex items-center gap-1" aria-hidden="true">
          <span className="window-control" data-tone="hot" />
          <span className="window-control" data-tone="lav" />
          <span className="window-control" data-tone="mint" />
        </span>
        <span className="pixel-label truncate text-[6px] text-blush">
          {eyebrow ?? "impactmap.exe"}
        </span>
        <span className="ml-auto hidden items-center gap-1.5 text-[9px] text-mauve sm:inline-flex">
          <span className="h-1 w-1 animate-pulse rounded-full bg-lav" />
          page loaded
        </span>
      </div>

      <div className="relative flex flex-col gap-4 p-4 sm:flex-row sm:items-end sm:justify-between sm:p-5">
        <span
          aria-hidden="true"
          className="pointer-events-none absolute -left-12 -top-16 h-40 w-40 rounded-full bg-neon/15 blur-3xl"
        />
        <div className="relative min-w-0">
          {eyebrow && (
            <p className="pixel-label mb-2 flex items-center gap-2 text-[7px] text-hot">
              <Sparkles className="h-3 w-3" aria-hidden="true" />
              {eyebrow}
            </p>
          )}
          <h1 className="truncate font-display text-2xl font-bold tracking-tight text-pale drop-shadow-[0_0_18px_rgba(233,79,168,0.35)] sm:text-3xl">
            {title}
          </h1>
          <div className="mt-2 flex items-center gap-2" aria-hidden="true">
            <span className="h-1 w-10 rounded-full bg-gradient-to-r from-neon to-lav shadow-[0_0_10px_rgba(255,121,201,0.7)]" />
            <span className="h-1 w-2 rounded-full bg-hot/60" />
            <span className="h-1 w-1 rounded-full bg-lav/60" />
          </div>
          {subtitle && (
            <div className="mt-2 max-w-3xl text-sm leading-relaxed text-slate-400">
              {subtitle}
            </div>
          )}
        </div>
        {actions && (
          <div className="relative flex shrink-0 flex-wrap gap-2">{actions}</div>
        )}
      </div>
    </div>
  );
}
