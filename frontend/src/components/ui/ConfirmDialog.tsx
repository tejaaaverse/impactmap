import type { ReactNode } from "react";
import { AlertTriangle } from "lucide-react";
import { useDialog } from "../../hooks/useDialog";

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "Confirm",
  busy = false,
  onConfirm,
  onCancel,
  children,
}: {
  open: boolean;
  title: string;
  description: ReactNode;
  confirmLabel?: string;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  children?: ReactNode;
}) {
  const close = () => {
    if (!busy) onCancel();
  };
  const { containerRef, onBackdropClick } = useDialog(open, close);

  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-ink-950/80 p-4 backdrop-blur-sm"
      onClick={onBackdropClick}
    >
      <div
        ref={containerRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        aria-describedby="confirm-description"
        tabIndex={-1}
        className="y2k-window w-full max-w-lg shadow-glow-lg focus:outline-none"
      >
        <div className="y2k-titlebar">
          <span className="window-control" data-tone="hot" aria-hidden="true" />
          <span className="window-control" data-tone="lav" aria-hidden="true" />
          <span className="window-control" data-tone="mint" aria-hidden="true" />
          <span className="pixel-label text-[7px] text-slate-500">
            confirm.exe
          </span>
        </div>
        <div className="p-5">
          <div className="flex items-start gap-3">
            <span className="rounded-lg border border-rose-400/40 bg-rose-500/10 p-2 text-rose-200 shadow-glow">
              <AlertTriangle className="h-5 w-5" aria-hidden="true" />
            </span>
            <div className="min-w-0 flex-1">
              <h2
                id="confirm-title"
                className="font-display text-base font-semibold text-pale"
              >
                {title}
              </h2>
              <div
                id="confirm-description"
                className="mt-1 text-sm leading-relaxed text-slate-400"
              >
                {description}
              </div>
            </div>
          </div>
          {children && <div className="mt-4">{children}</div>}
          <div className="mt-5 flex justify-end gap-2">
            <button
              type="button"
              className="btn-secondary"
              onClick={onCancel}
              disabled={busy}
            >
              Cancel
            </button>
            <button
              type="button"
              className="btn-primary"
              onClick={onConfirm}
              disabled={busy}
            >
              {busy ? "Working…" : confirmLabel}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
