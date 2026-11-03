import type { ReactNode } from "react";
import { TONE_CLASSES, type Tone } from "../../lib/format";

export function StatCard({
  label,
  value,
  hint,
  icon,
  tone = "sky",
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  icon?: ReactNode;
  tone?: Tone;
}) {
  return (
    <div className="y2k-bevel group relative overflow-hidden rounded-xl p-4 transition-transform duration-300 hover:-translate-y-0.5">
      <span
        aria-hidden="true"
        className="pointer-events-none absolute -right-8 -top-10 h-24 w-24 rounded-full bg-gradient-to-br from-rose-500/30 to-violet-400/15 blur-2xl"
      />
      <span
        aria-hidden="true"
        className="pointer-events-none absolute left-1.5 top-1.5 h-1 w-1 bg-hot/70"
      />
      <span
        aria-hidden="true"
        className="pointer-events-none absolute right-1.5 top-1.5 h-1 w-1 bg-lav/70"
      />
      <div className="relative flex items-start justify-between gap-3">
        <p className="pixel-label pt-0.5 text-[7px] text-slate-500">{label}</p>
        {icon && (
          <span
            className={`rounded-lg border p-1.5 shadow-[0_0_20px_-10px_rgba(233,79,168,0.8)] ${TONE_CLASSES[tone]}`}
            aria-hidden="true"
          >
            {icon}
          </span>
        )}
      </div>
      <p className="stat-value relative mt-3 font-display text-2xl font-bold text-pale">
        {value}
      </p>
      {hint && (
        <p className="relative mt-1 text-[11px] leading-relaxed text-slate-500">
          {hint}
        </p>
      )}
      <span
        aria-hidden="true"
        className="absolute inset-x-4 bottom-0 h-px bg-gradient-to-r from-rose-500/50 via-violet-400/30 to-transparent"
      />
      <span
        aria-hidden="true"
        className="pointer-events-none absolute bottom-0 left-0 h-6 w-px bg-gradient-to-t from-hot/50 to-transparent"
      />
    </div>
  );
}
