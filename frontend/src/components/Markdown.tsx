import { useEffect, useState, type ReactNode } from "react";
import { Check, Copy } from "lucide-react";
import type { CopilotEvidence } from "../types";

/**
 * Small, dependency-free Markdown renderer for Copilot answers.
 *
 * It intentionally renders React nodes instead of injecting HTML: model output
 * and repository content are untrusted, so raw HTML is shown as text and links
 * are restricted to http(s), root-relative and fragment URLs.
 */

interface MarkdownProps {
  content: string;
  evidence?: CopilotEvidence[];
  onCitation?: (evidence: CopilotEvidence) => void;
}

const CITATION_PATTERN = /\[[Ee]\d+\]/;
const FENCE_PATTERN = /^```([\w.+-]*)\s*$/;
const HEADING_PATTERN = /^(#{1,6})\s+(.+)$/;
const UNORDERED_PATTERN = /^\s*[-*+]\s+(.+)$/;
const ORDERED_PATTERN = /^\s*\d+[.)]\s+(.+)$/;
const QUOTE_PATTERN = /^>\s?(.*)$/;
const RULE_PATTERN = /^\s*([-*_])(\s*\1){2,}\s*$/;

function safeHref(href: string): string | null {
  const trimmed = href.trim();
  if (/^https?:\/\//i.test(trimmed)) return trimmed;
  if (trimmed.startsWith("/") || trimmed.startsWith("#")) return trimmed;
  return null;
}

function renderInline(
  text: string,
  evidence: CopilotEvidence[],
  onCitation?: (evidence: CopilotEvidence) => void,
  keyPrefix = "inline",
): ReactNode[] {
  const nodes: ReactNode[] = [];
  const pattern =
    /(`[^`\n]+`)|(\*\*[^*\n]+\*\*)|(__[^_\n]+__)|(\[[Ee]\d+\])|(\[[^\]\n]+\]\([^)\s]+\))|(\*[^*\n]+\*)/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let index = 0;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index));
    }

    const token = match[0];
    const key = `${keyPrefix}-${index++}`;

    if (token.startsWith("`")) {
      nodes.push(
        <code
          key={key}
          className="rounded border border-violet-400/20 bg-violet-400/10 px-1.5 py-0.5 font-mono text-[0.85em] text-blush"
        >
          {token.slice(1, -1)}
        </code>,
      );
    } else if (token.startsWith("**") || token.startsWith("__")) {
      nodes.push(
        <strong key={key} className="font-semibold text-pale">
          {renderInline(token.slice(2, -2), evidence, onCitation, key)}
        </strong>,
      );
    } else if (token.startsWith("*") && token.endsWith("*")) {
      nodes.push(
        <em key={key}>{renderInline(token.slice(1, -1), evidence, onCitation, key)}</em>,
      );
    } else if (CITATION_PATTERN.test(token)) {
      const id = token.slice(1, -1).toUpperCase();
      const item = evidence.find((entry) => entry.id.toUpperCase() === id);
      if (item && onCitation) {
        nodes.push(
          <button
            key={key}
            type="button"
            onClick={() => onCitation(item)}
            title={`Open evidence ${item.id}: ${item.title}`}
            aria-label={`Show evidence ${item.id}`}
            className="mx-0.5 inline-flex items-center rounded border border-hot/40 bg-neon/10 px-1 py-0 align-baseline font-mono text-[0.75em] font-semibold text-hot transition-colors hover:border-hot/70 hover:bg-neon/20 hover:text-blush"
          >
            {token}
          </button>,
        );
      } else {
        nodes.push(
          <span
            key={key}
            className="mx-0.5 font-mono text-[0.8em] text-slate-400"
            title={item ? item.title : "No matching evidence"}
          >
            {token}
          </span>,
        );
      }
    } else {
      const link = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(token);
      const href = link ? safeHref(link[2]) : null;
      if (link && href) {
        nodes.push(
          <a
            key={key}
            href={href}
            target={href.startsWith("http") ? "_blank" : undefined}
            rel={href.startsWith("http") ? "noreferrer noopener" : undefined}
            className="text-hot underline decoration-neon/40 underline-offset-2 hover:text-blush"
          >
            {link[1]}
          </a>,
        );
      } else {
        nodes.push(token);
      }
    }

    lastIndex = match.index + token.length;
  }

  if (lastIndex < text.length) nodes.push(text.slice(lastIndex));
  return nodes;
}

function CodeBlock({ code, language }: { code: string; language: string }) {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!copied) return undefined;
    const timer = setTimeout(() => setCopied(false), 1500);
    return () => clearTimeout(timer);
  }, [copied]);

  async function copy() {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  return (
    <div className="my-3 overflow-hidden rounded-lg border border-violet-400/25 bg-ink-950/95 shadow-glow">
      <div className="flex items-center justify-between border-b border-violet-400/15 bg-gradient-to-r from-panel to-plum px-3 py-1.5">
        <span className="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wider text-hot">
          <span className="h-1.5 w-1.5 rounded-full bg-neon" aria-hidden="true" />
          {language || "code"}
        </span>
        <button
          type="button"
          onClick={copy}
          className="inline-flex items-center gap-1 text-[10px] text-slate-400 transition-colors hover:text-blush"
          aria-label="Copy code"
        >
          {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="overflow-x-auto p-3 text-xs leading-relaxed">
        <code className="font-mono text-blush">{code}</code>
      </pre>
    </div>
  );
}

export function Markdown({ content, evidence = [], onCitation }: MarkdownProps) {
  const lines = content.replace(/\r\n/g, "\n").split("\n");
  const blocks: ReactNode[] = [];
  let i = 0;
  let key = 0;

  const nextKey = () => `block-${key++}`;

  while (i < lines.length) {
    const line = lines[i];

    if (!line.trim()) {
      i += 1;
      continue;
    }

    const fence = FENCE_PATTERN.exec(line);
    if (fence) {
      const codeLines: string[] = [];
      i += 1;
      while (i < lines.length && !lines[i].startsWith("```")) {
        codeLines.push(lines[i]);
        i += 1;
      }
      if (i < lines.length) i += 1;
      blocks.push(
        <CodeBlock key={nextKey()} code={codeLines.join("\n")} language={fence[1]} />,
      );
      continue;
    }

    const heading = HEADING_PATTERN.exec(line);
    if (heading) {
      const depth = heading[1].length;
      const className =
        depth <= 2
          ? "mb-2 mt-4 text-base font-semibold text-pale"
          : "mb-1.5 mt-3 text-sm font-semibold text-blush";
      const Tag = (`h${Math.min(depth + 1, 6)}` as "h2" | "h3" | "h4" | "h5" | "h6");
      blocks.push(
        <Tag key={nextKey()} className={className}>
          {renderInline(heading[2], evidence, onCitation, nextKey())}
        </Tag>,
      );
      i += 1;
      continue;
    }

    if (RULE_PATTERN.test(line)) {
      blocks.push(<hr key={nextKey()} className="my-4 border-violet-400/20" />);
      i += 1;
      continue;
    }

    const quote = QUOTE_PATTERN.exec(line);
    if (quote) {
      const quoteLines: string[] = [];
      while (i < lines.length) {
        const match = QUOTE_PATTERN.exec(lines[i]);
        if (!match) break;
        quoteLines.push(match[1]);
        i += 1;
      }
      blocks.push(
        <blockquote
          key={nextKey()}
          className="my-2 border-l-2 border-lav/60 pl-3 text-sm text-slate-400"
        >
          {renderInline(quoteLines.join(" "), evidence, onCitation, nextKey())}
        </blockquote>,
      );
      continue;
    }

    const unordered = UNORDERED_PATTERN.exec(line);
    if (unordered) {
      const items: string[] = [];
      while (i < lines.length) {
        const match = UNORDERED_PATTERN.exec(lines[i]);
        if (!match) break;
        items.push(match[1]);
        i += 1;
      }
      blocks.push(
        <ul key={nextKey()} className="my-2 list-disc space-y-1 pl-5 text-sm text-slate-300">
          {items.map((item, index) => (
            <li key={`${nextKey()}-${index}`}>
              {renderInline(item, evidence, onCitation, nextKey())}
            </li>
          ))}
        </ul>,
      );
      continue;
    }

    const ordered = ORDERED_PATTERN.exec(line);
    if (ordered) {
      const items: string[] = [];
      while (i < lines.length) {
        const match = ORDERED_PATTERN.exec(lines[i]);
        if (!match) break;
        items.push(match[1]);
        i += 1;
      }
      blocks.push(
        <ol key={nextKey()} className="my-2 list-decimal space-y-1 pl-5 text-sm text-slate-300">
          {items.map((item, index) => (
            <li key={`${nextKey()}-${index}`}>
              {renderInline(item, evidence, onCitation, nextKey())}
            </li>
          ))}
        </ol>,
      );
      continue;
    }

    const paragraph: string[] = [line.trim()];
    i += 1;
    while (i < lines.length) {
      const candidate = lines[i];
      if (
        !candidate.trim() ||
        FENCE_PATTERN.test(candidate) ||
        HEADING_PATTERN.test(candidate) ||
        RULE_PATTERN.test(candidate) ||
        QUOTE_PATTERN.test(candidate) ||
        UNORDERED_PATTERN.test(candidate) ||
        ORDERED_PATTERN.test(candidate)
      ) {
        break;
      }
      paragraph.push(candidate.trim());
      i += 1;
    }
    blocks.push(
      <p key={nextKey()} className="my-2 text-sm leading-relaxed text-slate-300">
        {renderInline(paragraph.join(" "), evidence, onCitation, nextKey())}
      </p>,
    );
  }

  return <div className="markdown-body">{blocks}</div>;
}
