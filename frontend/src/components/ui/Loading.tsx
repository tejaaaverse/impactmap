export function Spinner({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <span
      role="status"
      aria-label="Loading"
      className={`inline-block animate-spin rounded-full border-2 border-violet-400/30 border-t-hot ${className}`}
    />
  );
}

export function LoadingBlock({ label = "Loading…" }: { label?: string }) {
  return (
    <div
      className="flex flex-col items-center justify-center gap-3 rounded-xl border border-violet-400/20 bg-plum/50 px-6 py-14 text-sm text-slate-400"
      role="status"
    >
      <span className="flex items-end gap-1" aria-hidden="true">
        {[0, 1, 2, 3].map((index) => (
          <span
            key={index}
            className="h-2 w-2 animate-pixel-pulse rounded-[1px] bg-gradient-to-t from-neon to-hot shadow-[0_0_10px_rgba(255,121,201,0.65)]"
            style={{ animationDelay: `${index * 140}ms` }}
          />
        ))}
      </span>
      <span className="pixel-label text-[8px] text-mauve">{label}</span>
    </div>
  );
}
