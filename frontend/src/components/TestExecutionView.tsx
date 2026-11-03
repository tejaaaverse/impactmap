import type { TestExecution } from "../types";
import { formatDuration } from "../lib/format";
import { StatusBadge } from "./ui/StatusBadge";

export function TestExecutionView({ execution }: { execution: TestExecution }) {
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <StatusBadge status={execution.timed_out ? "timed_out" : execution.status} />
        <span className="text-slate-400">{execution.total_tests} tests</span>
        <span className="text-lav">{execution.passed} passed</span>
        <span className="text-hot">{execution.failed} failed</span>
        <span className="text-blush">{execution.errors} errors</span>
        <span className="text-slate-500">{execution.skipped} skipped</span>
        <span className="text-slate-400">{formatDuration(execution.duration_ms)}</span>
      </div>
      {execution.command.length > 0 && (
        <p className="retro-inset overflow-x-auto px-3 py-2 font-mono text-[11px] text-slate-400">
          <span className="text-hot">$</span> {execution.command.join(" ")}
        </p>
      )}
      {execution.results.length > 0 && (
        <div className="max-h-52 overflow-y-auto rounded-lg border border-violet-400/20">
          <table className="table-base">
            <thead>
              <tr>
                <th>Test</th>
                <th>Status</th>
                <th>Duration</th>
              </tr>
            </thead>
            <tbody>
              {execution.results.map((result) => (
                <tr key={result.test_id}>
                  <td className="max-w-[380px] truncate font-mono text-[11px] text-slate-300">
                    {result.test_id}
                  </td>
                  <td>
                    <StatusBadge status={result.status} />
                  </td>
                  <td className="text-slate-400">{formatDuration(result.duration_ms)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {(execution.stdout_tail || execution.stderr_tail) && (
        <details className="rounded-lg border border-violet-400/20 bg-ink-950">
          <summary className="cursor-pointer px-3 py-2 text-xs text-slate-400 transition-colors hover:text-blush">
            Process output
          </summary>
          <pre className="max-h-56 overflow-auto whitespace-pre-wrap border-t border-violet-400/15 px-3 py-3 font-mono text-[11px] text-slate-400">
            {execution.stdout_tail}
            {execution.stderr_tail ? `\n${execution.stderr_tail}` : ""}
          </pre>
        </details>
      )}
      {execution.warnings.length > 0 && (
        <ul className="space-y-1 rounded-lg border border-amber-500/20 bg-amber-500/5 p-3 text-xs text-amber-200">
          {execution.warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
