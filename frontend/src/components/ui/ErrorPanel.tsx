import { AlertTriangle, RotateCcw } from "lucide-react";

export function ErrorPanel({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-rose-400/35 bg-gradient-to-br from-rose-500/10 to-plum/60 px-4 py-4 text-sm text-rose-200 shadow-glow">
      <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-hot" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <p className="pixel-label text-[8px] text-hot">Something went wrong</p>
        <p className="mt-1.5 break-words text-rose-100/90">{message}</p>
      </div>
      {onRetry && (
        <button type="button" onClick={onRetry} className="btn-secondary shrink-0">
          <RotateCcw className="h-4 w-4" aria-hidden="true" />
          Retry
        </button>
      )}
    </div>
  );
}
