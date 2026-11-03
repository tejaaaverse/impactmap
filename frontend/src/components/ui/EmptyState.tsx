import type { ReactNode } from "react";
import { Inbox } from "lucide-react";

export function EmptyState({
  title,
  description,
  action,
  icon,
}: {
  title: string;
  description: string;
  action?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="relative flex flex-col items-center justify-center gap-3 overflow-hidden rounded-xl border border-dashed border-violet-400/30 bg-gradient-to-b from-panel/50 to-ink-950/50 px-6 py-12 text-center">
      <span
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 bg-pixel-grid bg-grid-32 opacity-30 [mask-image:radial-gradient(circle_at_center,black,transparent_75%)]"
      />
      {icon ? (
        <div className="relative rounded-full border border-violet-400/30 bg-panel/80 p-3 text-hot shadow-glow">
          {icon}
        </div>
      ) : (
        <div className="relative flex items-end gap-1">
          <img
            src="/assets/rabbit-pixel.svg"
            alt=""
            aria-hidden="true"
            className="mascot-sprite h-12 w-12 animate-floaty"
          />
          <img
            src="/assets/tortoise-pixel.svg"
            alt=""
            aria-hidden="true"
            className="mascot-sprite h-12 w-12 animate-floaty [animation-delay:1.1s]"
          />
          <span className="absolute -right-3 -top-1 text-hot">
            <Inbox className="h-4 w-4" aria-hidden="true" />
          </span>
        </div>
      )}
      <div className="relative">
        <p className="pixel-label mb-2 text-[7px] text-slate-600">// empty space</p>
        <p className="text-sm font-semibold text-pale">{title}</p>
        <p className="mx-auto mt-1 max-w-md text-xs leading-relaxed text-slate-400 sm:text-sm">
          {description}
        </p>
      </div>
      {action && <div className="relative">{action}</div>}
    </div>
  );
}
