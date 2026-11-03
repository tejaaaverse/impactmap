import type { ReactNode } from "react";
import { TONE_CLASSES, type Tone } from "../../lib/format";

interface BadgeProps {
  children: ReactNode;
  tone?: Tone;
  className?: string;
  title?: string;
}

export function Badge({ children, tone = "slate", className = "", title }: BadgeProps) {
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide shadow-[inset_0_0_10px_rgba(255,121,201,0.05)] ${TONE_CLASSES[tone]} ${className}`}
    >
      {children}
    </span>
  );
}
