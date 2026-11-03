import type { ReactNode } from "react";
import { Minus, Square, X } from "lucide-react";

export function Section({
  title,
  description,
  actions,
  children,
  className = "",
}: {
  title?: string;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`y2k-window ${className}`}>
      {(title || actions) && (
        <header className="y2k-titlebar flex-wrap">
          <span className="mr-1 hidden items-center gap-1 sm:flex" aria-hidden="true">
            <span className="window-control" data-tone="hot" />
            <span className="window-control" data-tone="lav" />
            <span className="window-control" data-tone="mint" />
          </span>
          {title && (
            <h2 className="pixel-label min-w-0 truncate text-[8px] text-blush">
              {title}
            </h2>
          )}
          {actions && (
            <div className="ml-auto flex flex-wrap items-center gap-2">{actions}</div>
          )}
          <span
            className="ml-1 hidden items-center gap-0.5 text-slate-600 sm:flex"
            aria-hidden="true"
          >
            <span className="grid h-4 w-4 place-items-center rounded-sm border border-violet-400/20 bg-ink-950/50">
              <Minus className="h-2 w-2" />
            </span>
            <span className="grid h-4 w-4 place-items-center rounded-sm border border-violet-400/20 bg-ink-950/50">
              <Square className="h-2 w-2" />
            </span>
            <span className="grid h-4 w-4 place-items-center rounded-sm border border-rose-400/30 bg-rose-500/15 text-rose-300">
              <X className="h-2 w-2" />
            </span>
          </span>
        </header>
      )}
      <div className="p-4 sm:p-5">
        {description && (
          <p className="mb-4 flex max-w-3xl items-start gap-2 text-xs leading-relaxed text-slate-400 sm:text-sm">
            <span
              className="mt-1.5 h-1.5 w-1.5 shrink-0 rotate-45 bg-hot shadow-[0_0_8px_rgba(255,121,201,0.9)]"
              aria-hidden="true"
            />
            <span>{description}</span>
          </p>
        )}
        {children}
      </div>
    </section>
  );
}
