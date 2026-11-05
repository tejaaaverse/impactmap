import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  ArrowRight,
  Bot,
  Boxes,
  ChevronDown,
  ChevronRight,
  FileCode2,
  FileText,
  Loader2,
  MessageSquarePlus,
  RefreshCw,
  Send,
  ShieldCheck,
  Sparkles,
  Trash2,
  User,
  X,
} from "lucide-react";
import { api, ApiError } from "../services/api";
import { useAsync } from "../hooks/useAsync";
import { useDialog } from "../hooks/useDialog";
import { PageHeader } from "../components/ui/PageHeader";
import { Section } from "../components/ui/Section";
import { Badge } from "../components/ui/Badge";
import { EmptyState } from "../components/ui/EmptyState";
import { ErrorPanel } from "../components/ui/ErrorPanel";
import { LoadingBlock } from "../components/ui/Loading";
import { ConfirmDialog } from "../components/ui/ConfirmDialog";
import { Markdown } from "../components/Markdown";
import { formatRelative } from "../lib/format";
import type {
  CopilotConversationSummary,
  CopilotEvidence,
  CopilotMessage,
  CopilotStatus,
  Repository,
} from "../types";

const STARTER_PROMPTS = [
  "Explain the overall architecture of this repository.",
  "Which files have the widest impact if they change?",
  "Which tests should I run for a change in this repository?",
  "Review this repository for likely bugs and risky code.",
  "Summarize the latest Git changes and what they affect.",
  "Where is a key function defined and what calls it?",
];

function errorMessage(error: unknown): string {
  if (error instanceof ApiError || error instanceof Error) return error.message;
  return String(error);
}

function localId(): string {
  return `local-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
}

export function CopilotPage() {
  const repositories = useAsync(() => api.listRepositories(), []);
  const status = useAsync(() => api.copilotStatus(), []);

  const [repoId, setRepoId] = useState("");
  const [messages, setMessages] = useState<CopilotMessage[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [history, setHistory] = useState<CopilotConversationSummary[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [historyVersion, setHistoryVersion] = useState(0);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [loadingConversation, setLoadingConversation] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedEvidence, setSelectedEvidence] = useState<CopilotEvidence | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<CopilotConversationSummary | null>(null);
  const [deleting, setDeleting] = useState(false);
  const endRef = useRef<HTMLDivElement | null>(null);

  const repositoriesList: Repository[] = repositories.data ?? [];
  const currentRepository = repositoriesList.find((item) => item.id === repoId) ?? null;

  useEffect(() => {
    if (!repoId && repositoriesList.length > 0) {
      setRepoId(repositoriesList[0].id);
    }
  }, [repoId, repositoriesList]);

  useEffect(() => {
    if (!repoId) return undefined;
    let active = true;
    setHistoryLoading(true);
    setHistoryError(null);
    api
      .listCopilotConversations(repoId)
      .then((result) => {
        if (active) setHistory(result.conversations);
      })
      .catch((err: unknown) => {
        if (active) setHistoryError(errorMessage(err));
      })
      .finally(() => {
        if (active) setHistoryLoading(false);
      });
    return () => {
      active = false;
    };
  }, [repoId, historyVersion]);

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ behavior: "smooth", block: "end" });
  }, [messages, busy]);

  function refreshHistory() {
    setHistoryVersion((value) => value + 1);
  }

  function resetConversation() {
    setConversationId(null);
    setMessages([]);
    setError(null);
    setSelectedEvidence(null);
  }

  function handleRepositoryChange(nextId: string) {
    if (nextId === repoId) return;
    setRepoId(nextId);
    resetConversation();
  }

  async function openConversation(conversation: CopilotConversationSummary) {
    if (loadingConversation) return;
    setLoadingConversation(true);
    setError(null);
    try {
      const detail = await api.getCopilotConversation(conversation.id);
      if (detail.conversation.repository_id !== repoId) {
        setRepoId(detail.conversation.repository_id);
      }
      setConversationId(detail.conversation.id);
      setMessages(detail.messages);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoadingConversation(false);
    }
  }

  async function ask(question: string) {
    const message = question.trim();
    // The default repository is selected in an effect, so a starter prompt can
    // be clicked in the same commit that first renders it. Fall back to the
    // first available repository so that early clicks are not silently dropped.
    const targetRepoId = repoId || repositoriesList[0]?.id;
    if (!message || busy || !targetRepoId) return;
    setBusy(true);
    setError(null);
    setDraft("");

    const optimistic: CopilotMessage = {
      id: localId(),
      conversation_id: conversationId ?? "",
      role: "user",
      content: message,
      intent: null,
      model: null,
      ai_enabled: false,
      evidence: [],
      follow_ups: [],
      warnings: [],
      error: null,
      latency_ms: null,
      created_at: new Date().toISOString(),
    };
    setMessages((current) => [...current, optimistic]);

    try {
      const response = await api.copilotChat(targetRepoId, {
        message,
        conversation_id: conversationId,
      });
      setConversationId(response.conversation_id);
      setMessages((current) => [...current, response.message]);
      refreshHistory();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    setError(null);
    try {
      await api.deleteCopilotConversation(deleteTarget.id);
      setHistory((current) => current.filter((item) => item.id !== deleteTarget.id));
      if (conversationId === deleteTarget.id) resetConversation();
      setDeleteTarget(null);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setDeleting(false);
    }
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    void ask(draft);
  }

  function handleComposerKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void ask(draft);
    }
  }

  return (
    <div>
      <PageHeader
        eyebrow="Repository Copilot"
        title="Ask your codebase"
        subtitle="Answers are grounded in retrieved files, symbols, dependency edges, Git state and test data. Read-only: no repository code is executed or modified."
        actions={
          <button type="button" className="btn-secondary" onClick={resetConversation}>
            <MessageSquarePlus className="h-4 w-4" />
            New conversation
          </button>
        }
      />

      {status.error && (
        <div className="mb-4">
          <ErrorPanel message={status.error} onRetry={status.reload} />
        </div>
      )}
      {status.data && <StatusBanner status={status.data} />}

      {repositories.loading && !repositories.data && (
        <LoadingBlock label="Loading repositories…" />
      )}
      {repositories.error && (
        <ErrorPanel message={repositories.error} onRetry={repositories.reload} />
      )}
      {repositories.data && repositoriesList.length === 0 && (
        <EmptyState
          icon={<Boxes className="h-5 w-5" />}
          title="No repositories scanned"
          description="Scan a local Python repository first, then ask the Copilot about its architecture, impact and tests."
          action={
            <Link className="btn-primary" to="/repositories">
              Scan a repository
              <ArrowRight className="h-4 w-4" />
            </Link>
          }
        />
      )}

      {repositoriesList.length > 0 && (
        <div className="grid gap-4 xl:grid-cols-[minmax(240px,300px)_minmax(0,1fr)]">
          <aside className="space-y-4">
            <Section title="Repository">
              <label className="label" htmlFor="copilot-repository">
                Scope
              </label>
              <select
                id="copilot-repository"
                className="input"
                value={repoId}
                onChange={(event) => handleRepositoryChange(event.target.value)}
              >
                {repositoriesList.map((repository) => (
                  <option key={repository.id} value={repository.id}>
                    {repository.name}
                  </option>
                ))}
              </select>
              {currentRepository && (
                <p className="mt-2 break-all font-mono text-[11px] text-slate-500">
                  {currentRepository.path}
                </p>
              )}
              {currentRepository && (
                <div className="mt-3 flex flex-wrap gap-1.5">
                  <Badge tone="sky">{currentRepository.total_files} files</Badge>
                  <Badge tone="violet">{currentRepository.total_functions} functions</Badge>
                  <Badge tone="emerald">
                    {currentRepository.total_dependencies} deps
                  </Badge>
                </div>
              )}
            </Section>

            <Section
              title="History"
              description="Saved threads for this repository."
              actions={
                <button
                  type="button"
                  className="btn-secondary px-2 py-1"
                  onClick={refreshHistory}
                  title="Refresh history"
                  aria-label="Refresh Copilot history"
                >
                  <RefreshCw className={`h-3.5 w-3.5 ${historyLoading ? "animate-spin" : ""}`} />
                </button>
              }
            >
              {historyError && (
                <p className="mb-2 text-xs text-rose-300">{historyError}</p>
              )}
              {historyLoading && history.length === 0 && (
                <p className="flex items-center gap-2 text-xs text-slate-500">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  Loading threads…
                </p>
              )}
              {!historyLoading && history.length === 0 && !historyError && (
                <p className="text-xs text-slate-500">
                  No saved conversations yet. Your first question will create one.
                </p>
              )}
              <ul className="space-y-1.5">
                {history.map((conversation) => {
                  const active = conversation.id === conversationId;
                  return (
                    <li key={conversation.id}>
                      <div
                        className={`group flex items-start gap-1 rounded-lg border px-2 py-2 transition-all ${
                          active
                            ? "border-hot/40 bg-gradient-to-r from-neon/15 to-violet-400/10 shadow-glow"
                            : "border-transparent hover:border-violet-400/25 hover:bg-rose-500/5"
                        }`}
                      >
                        <button
                          type="button"
                          onClick={() => void openConversation(conversation)}
                          className="min-w-0 flex-1 text-left"
                          disabled={loadingConversation}
                          aria-label={`Open conversation ${conversation.title}`}
                        >
                          <span
                            className={`block truncate text-xs font-medium ${
                              active ? "text-blush" : "text-slate-300"
                            }`}
                          >
                            {conversation.title}
                          </span>
                          <span className="mt-0.5 block truncate text-[10px] text-slate-500">
                            {conversation.message_count} messages ·{" "}
                            {formatRelative(conversation.updated_at)}
                          </span>
                        </button>
                        <button
                          type="button"
                          onClick={() => setDeleteTarget(conversation)}
                          className="rounded p-1 text-slate-600 opacity-0 transition-opacity hover:bg-rose-500/10 hover:text-rose-300 focus:opacity-100 group-hover:opacity-100"
                          title="Delete conversation"
                          aria-label={`Delete conversation ${conversation.title}`}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </li>
                  );
                })}
              </ul>
            </Section>

            <div className="retro-panel p-3 text-[11px] leading-relaxed text-slate-500">
              <p className="pixel-label mb-2 flex items-center gap-1.5 text-lav">
                <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
                Read-only by design
              </p>
              Repository content is treated as untrusted data. The Copilot retrieves
              relevant evidence instead of sending the whole repository, and never
              executes code or changes files.
            </div>
          </aside>

          <section className="y2k-window flex min-h-[68vh] flex-col overflow-hidden">
            <div className="y2k-titlebar">
              <span className="window-control" data-tone="hot" aria-hidden="true" />
              <span className="window-control" data-tone="lav" aria-hidden="true" />
              <span className="window-control" data-tone="mint" aria-hidden="true" />
              <span className="pixel-label ml-1 text-[7px] text-blush">
                copilot.exe
              </span>
              <span className="ml-auto inline-flex items-center gap-1.5 rounded-full border border-violet-400/25 bg-ink-950/60 px-2 py-0.5 text-[9px] text-slate-400">
                <ShieldCheck className="h-2.5 w-2.5 text-lav" aria-hidden="true" />
                read-only
              </span>
            </div>
            <div className="scrollbar-thin flex-1 space-y-5 overflow-y-auto p-4 sm:p-5">
              {loadingConversation && (
                <div className="flex items-center gap-2 text-xs text-slate-500">
                  <Loader2 className="h-3.5 w-3.5 animate-spin text-hot" />
                  Loading conversation…
                </div>
              )}

              {!loadingConversation && messages.length === 0 && (
                <div className="mx-auto max-w-2xl py-6">
                  <div className="mb-5 flex items-center gap-3">
                    <span className="grid h-12 w-12 place-items-center rounded-xl border border-hot/35 bg-gradient-to-br from-neon/15 to-violet-400/10 text-hot shadow-glow">
                      <Bot className="h-6 w-6" />
                    </span>
                    <div>
                      <p className="pixel-label mb-1.5 text-[7px] text-slate-500">
                        // new transmission
                      </p>
                      <h2 className="font-display text-base font-semibold text-pale">
                        Ask about{" "}
                        <span className="text-gradient-pink">
                          {currentRepository?.name ?? "this repository"}
                        </span>
                      </h2>
                      <p className="text-xs text-slate-500">
                        Questions are answered from retrieved evidence with citations.
                      </p>
                    </div>
                    <img
                      src="/assets/rabbit-pixel.svg"
                      alt=""
                      aria-hidden="true"
                      className="mascot-sprite ml-auto hidden h-14 w-14 animate-floaty sm:block"
                    />
                  </div>
                  <div className="grid gap-2 sm:grid-cols-2">
                    {STARTER_PROMPTS.map((prompt) => (
                      <button
                        key={prompt}
                        type="button"
                        onClick={() => void ask(prompt)}
                        disabled={busy}
                        className="group flex items-start gap-2 rounded-lg border border-violet-400/20 bg-ink-950/55 p-3 text-left text-xs text-slate-300 transition-all hover:-translate-y-0.5 hover:border-hot/40 hover:bg-panel/70 hover:text-pale hover:shadow-glow disabled:opacity-50"
                      >
                        <Sparkles className="mt-0.5 h-3.5 w-3.5 shrink-0 text-hot transition-transform group-hover:scale-110" />
                        {prompt}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {messages.map((message) =>
                message.role === "user" ? (
                  <UserMessage key={message.id} message={message} />
                ) : (
                  <AssistantMessage
                    key={message.id}
                    message={message}
                    onCitation={setSelectedEvidence}
                    onFollowUp={(prompt) => void ask(prompt)}
                    busy={busy}
                  />
                ),
              )}

              {busy && (
                <div
                  className="flex items-center gap-2.5 rounded-lg border border-violet-400/20 bg-ink-950/50 px-3 py-2.5 text-[11px] text-slate-400"
                  role="status"
                  aria-live="polite"
                >
                  <span className="flex items-end gap-1" aria-hidden="true">
                    {[0, 1, 2].map((index) => (
                      <span
                        key={index}
                        className="h-1.5 w-1.5 animate-pixel-pulse rounded-[1px] bg-hot"
                        style={{ animationDelay: `${index * 160}ms` }}
                      />
                    ))}
                  </span>
                  Retrieving repository evidence and composing an answer…
                </div>
              )}

              {error && (
                <div className="flex items-start gap-2 rounded-lg border border-rose-500/30 bg-rose-500/5 px-3 py-2 text-xs text-rose-200">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                  <span className="min-w-0 flex-1 break-words">{error}</span>
                  <button
                    type="button"
                    onClick={() => setError(null)}
                    className="text-rose-300 hover:text-rose-100"
                    aria-label="Dismiss error"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
              )}
              <div ref={endRef} />
            </div>

            <form
              onSubmit={handleSubmit}
              className="border-t border-violet-400/20 bg-gradient-to-b from-plum/60 to-ink-950/80 p-3 sm:p-4"
            >
              <label htmlFor="copilot-question" className="sr-only">
                Ask the repository Copilot
              </label>
              <div className="flex items-end gap-2">
                <textarea
                  id="copilot-question"
                  className="input min-h-[52px] max-h-40 flex-1 resize-y"
                  rows={2}
                  maxLength={8000}
                  placeholder={
                    repoId
                      ? "Ask about architecture, a symbol, impact, tests or Git changes…"
                      : "Select a repository first"
                  }
                  value={draft}
                  disabled={!repoId || busy}
                  onChange={(event) => setDraft(event.target.value)}
                  onKeyDown={handleComposerKeyDown}
                />
                <button
                  type="submit"
                  className="btn-primary h-[52px] px-4"
                  disabled={!repoId || busy || !draft.trim()}
                >
                  {busy ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Send className="h-4 w-4" />
                  )}
                  Ask
                </button>
              </div>
              <div className="mt-1.5 flex items-center justify-between text-[10px] text-slate-600">
                <span>Enter to send · Shift+Enter for a new line</span>
                <span className="font-mono">
                  {draft.length}/8000
                </span>
              </div>
            </form>
          </section>
        </div>
      )}

      {selectedEvidence && (
        <EvidenceDrawer
          repositoryId={repoId}
          evidence={selectedEvidence}
          onClose={() => setSelectedEvidence(null)}
        />
      )}

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title="Delete this conversation?"
        description={
          deleteTarget
            ? `“${deleteTarget.title}” and its ${deleteTarget.message_count} messages will be permanently removed.`
            : ""
        }
        confirmLabel="Delete conversation"
        busy={deleting}
        onConfirm={() => void confirmDelete()}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}

function StatusBanner({ status }: { status: CopilotStatus }) {
  const localOnly = !status.ai_enabled;
  return (
    <div
      className={`y2k-window mb-4 ${
        localOnly ? "border-rose-400/30" : "border-violet-400/35"
      }`}
    >
      <div className="y2k-titlebar">
        <span className="window-control" data-tone="hot" aria-hidden="true" />
        <span className="window-control" data-tone="lav" aria-hidden="true" />
        <span className="window-control" data-tone="mint" aria-hidden="true" />
        <span className="pixel-label text-[7px] text-slate-500">
          copilot.status
        </span>
        <Badge tone={localOnly ? "rose" : "violet"} className="ml-auto">
          {localOnly ? "local evidence" : "model online"}
        </Badge>
      </div>
      <div className="flex flex-wrap items-start gap-3 px-4 py-3 text-xs">
        <span className="mt-0.5 rounded-md border border-violet-400/25 bg-ink-950/60 p-1.5">
          {localOnly ? (
            <ShieldCheck className="h-4 w-4 text-hot" aria-hidden="true" />
          ) : (
            <Sparkles className="h-4 w-4 text-lav" aria-hidden="true" />
          )}
        </span>
        <div className="min-w-0 flex-1">
          <p className="font-semibold text-pale">
            {localOnly
              ? "Local evidence mode — no language model configured"
              : `Model answers enabled${status.model ? ` · ${status.model}` : ""}`}
          </p>
          <p className="mt-0.5 break-words text-slate-400">
            {localOnly
              ? status.setup
              : `Provider ${status.provider} · ${status.retrieval}. API keys stay on the backend.`}
          </p>
        </div>
        {status.key_configured && (
          <Badge tone="violet">
            <ShieldCheck className="h-3 w-3" /> key configured
          </Badge>
        )}
      </div>
    </div>
  );
}

function UserMessage({ message }: { message: CopilotMessage }) {
  return (
    <div className="flex items-start justify-end gap-3">
      <div className="max-w-[85%] rounded-xl rounded-tr-sm border border-hot/40 bg-gradient-to-br from-neon/20 to-berry/15 px-4 py-3 shadow-glow">
        <p className="whitespace-pre-wrap break-words text-sm text-pale">
          {message.content}
        </p>
      </div>
      <span className="mt-1 hidden h-8 w-8 shrink-0 place-items-center rounded-full border border-hot/35 bg-neon/10 text-blush sm:grid">
        <User className="h-4 w-4" />
      </span>
    </div>
  );
}

function AssistantMessage({
  message,
  onCitation,
  onFollowUp,
  busy,
}: {
  message: CopilotMessage;
  onCitation: (evidence: CopilotEvidence) => void;
  onFollowUp: (prompt: string) => void;
  busy: boolean;
}) {
  const [showEvidence, setShowEvidence] = useState(false);
  const evidence = message.evidence ?? [];
  const warnings = message.warnings ?? [];
  const followUps = message.follow_ups ?? [];

  return (
    <div className="flex items-start gap-3">
      <span className="mt-1 hidden h-8 w-8 shrink-0 place-items-center rounded-full border border-violet-400/40 bg-violet-400/10 text-lav shadow-lavender sm:grid">
        <Bot className="h-4 w-4" />
      </span>
      <div className="min-w-0 flex-1 rounded-xl rounded-tl-sm border border-violet-400/25 bg-gradient-to-br from-panel/70 to-ink-950/65 px-4 py-3">
        <div className="mb-1 flex flex-wrap items-center gap-2 text-[10px] text-slate-500">
          {message.intent && <Badge tone="sky">{message.intent.split("_").join(" ")}</Badge>}
          {message.model ? (
            <span className="font-mono text-lav">{message.model}</span>
          ) : (
            <span className="text-lav">local evidence</span>
          )}
          {typeof message.latency_ms === "number" && message.latency_ms > 0 && (
            <span>· {Math.round(message.latency_ms)} ms</span>
          )}
        </div>

        {message.content ? (
          <Markdown content={message.content} evidence={evidence} onCitation={onCitation} />
        ) : (
          <p className="text-sm text-slate-400">No answer content was returned.</p>
        )}

        {warnings.length > 0 && (
          <ul className="mt-2 space-y-1 rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-2 text-[11px] text-amber-200">
            {warnings.map((warning) => (
              <li key={warning} className="flex items-start gap-1.5">
                <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
                <span className="break-words">{warning}</span>
              </li>
            ))}
          </ul>
        )}

        {evidence.length > 0 && (
          <div className="mt-3 border-t border-violet-400/20 pt-2">
            <button
              type="button"
              onClick={() => setShowEvidence((value) => !value)}
              className="inline-flex items-center gap-1 text-[11px] font-medium text-slate-400 hover:text-blush"
              aria-expanded={showEvidence}
            >
              {showEvidence ? (
                <ChevronDown className="h-3.5 w-3.5" />
              ) : (
                <ChevronRight className="h-3.5 w-3.5" />
              )}
              Evidence sources ({evidence.length})
            </button>
            {showEvidence && (
              <div className="mt-2 grid gap-2 sm:grid-cols-2">
                {evidence.map((item) => (
                  <EvidenceCard
                    key={item.id}
                    evidence={item}
                    onClick={() => onCitation(item)}
                  />
                ))}
              </div>
            )}
          </div>
        )}

        {followUps.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {followUps.map((prompt) => (
              <button
                key={prompt}
                type="button"
                onClick={() => onFollowUp(prompt)}
                disabled={busy}
                className="rounded-full border border-violet-400/30 bg-violet-400/5 px-2.5 py-1 text-[11px] text-slate-300 transition-colors hover:border-hot/50 hover:text-blush disabled:opacity-50"
              >
                {prompt}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function evidenceKindIcon(kind: string) {
  switch (kind) {
    case "file":
    case "symbol":
      return <FileCode2 className="h-3.5 w-3.5" />;
    default:
      return <FileText className="h-3.5 w-3.5" />;
  }
}

function EvidenceCard({
  evidence,
  onClick,
}: {
  evidence: CopilotEvidence;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="y2k-bevel group rounded-lg p-2.5 text-left transition-all hover:-translate-y-0.5 hover:border-hot/40 hover:shadow-glow"
      title="Open evidence"
    >
      <div className="flex items-center justify-between gap-2">
        <span className="inline-flex items-center gap-1.5 text-[11px] font-medium text-slate-300">
          <span className="text-hot">{evidenceKindIcon(evidence.kind)}</span>
          <span className="font-mono text-hot">{evidence.id}</span>
          {evidence.kind}
        </span>
        {evidence.score > 0 && (
          <span className="font-mono text-[10px] text-slate-600">
            {evidence.score.toFixed(2)}
          </span>
        )}
      </div>
      <p className="mt-1 line-clamp-2 break-words text-[11px] text-blush transition-colors group-hover:text-pale">
        {evidence.title}
      </p>
      {evidence.file_path && (
        <p className="mt-1 truncate font-mono text-[10px] text-slate-500">
          {evidence.file_path}
          {evidence.line_start > 0 ? `:${evidence.line_start}` : ""}
          {evidence.line_end > evidence.line_start ? `–${evidence.line_end}` : ""}
        </p>
      )}
    </button>
  );
}

function EvidenceDrawer({
  repositoryId,
  evidence,
  onClose,
}: {
  repositoryId: string;
  evidence: CopilotEvidence;
  onClose: () => void;
}) {
  const hasFile = Boolean(repositoryId && evidence.file_path);
  const startLine = evidence.line_start > 8 ? evidence.line_start - 8 : 1;
  const endLine =
    evidence.line_end > 0
      ? evidence.line_end + 8
      : evidence.line_start > 0
        ? evidence.line_start + 20
        : undefined;

  const file = useAsync(
    () =>
      hasFile
        ? api.getRepositoryFile(repositoryId, evidence.file_path, {
            startLine,
            endLine,
          })
        : Promise.resolve(null),
    [repositoryId, evidence.id, evidence.file_path, startLine, endLine, hasFile],
  );

  const { containerRef, onBackdropClick } = useDialog(true, onClose);

  const lines = file.data?.content.split("\n") ?? [];
  const firstLine = file.data?.start_line ?? 1;

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-ink-950/85 backdrop-blur-sm"
      onClick={onBackdropClick}
    >
      <div
        ref={containerRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="evidence-title"
        tabIndex={-1}
        className="flex h-full w-full max-w-3xl flex-col border-l border-violet-400/30 bg-plum shadow-glow-lg focus:outline-none"
      >
        <header className="border-b border-violet-400/20 bg-gradient-to-r from-panel via-plum to-panel px-5 py-4">
          <div className="mb-3 flex items-center gap-2">
            <span className="window-control" data-tone="hot" aria-hidden="true" />
            <span className="window-control" data-tone="lav" aria-hidden="true" />
            <span className="window-control" data-tone="mint" aria-hidden="true" />
            <span className="pixel-label text-[7px] text-slate-500">
              evidence.viewer
            </span>
            <button
              type="button"
              onClick={onClose}
              className="btn-secondary ml-auto shrink-0 px-2 py-1"
              aria-label="Close evidence"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="min-w-0">
            <p className="mb-1 flex items-center gap-2 font-mono text-[10px] uppercase tracking-wider text-hot">
              <FileText className="h-3.5 w-3.5" aria-hidden="true" />
              Evidence {evidence.id} · {evidence.kind}
            </p>
            <h2 id="evidence-title" className="break-words text-sm font-semibold text-pale">
              {evidence.title}
            </h2>
            {evidence.file_path && (
              <p className="mt-1 break-all font-mono text-xs text-blush">
                {evidence.file_path}
                {evidence.line_start > 0 ? `:${evidence.line_start}` : ""}
                {evidence.line_end > evidence.line_start ? `–${evidence.line_end}` : ""}
              </p>
            )}
            {evidence.reason && (
              <p className="mt-1 text-[11px] text-slate-500">{evidence.reason}</p>
            )}
          </div>
        </header>

        <div className="flex-1 overflow-auto">
          {hasFile && file.loading && <LoadingBlock label="Loading file…" />}
          {hasFile && file.error && (
            <div className="p-5">
              <ErrorPanel message={file.error} onRetry={file.reload} />
            </div>
          )}
          {hasFile && file.data && (
            <div className="min-w-max py-2">
              <div className="flex items-center justify-between border-b border-violet-400/15 bg-ink-900/70 px-5 pb-2 pt-1 text-[10px] text-slate-500">
                <span className="font-mono">
                  {file.data.path} · {file.data.language} · {file.data.line_count} lines
                </span>
                {file.data.truncated && <span>Showing lines {firstLine}–{firstLine + lines.length - 1}</span>}
              </div>
              <div className="font-mono text-xs leading-6">
                {lines.map((line, index) => {
                  const lineNumber = firstLine + index;
                  const highlighted =
                    lineNumber >= evidence.line_start &&
                    lineNumber <= Math.max(evidence.line_end, evidence.line_start);
                  return (
                    <div
                      key={`${lineNumber}-${index}`}
                      className={`flex gap-4 px-3 ${
                        highlighted ? "bg-neon/10" : ""
                      }`}
                    >
                      <span
                        className={`w-12 shrink-0 select-none text-right ${
                          highlighted ? "text-hot" : "text-slate-600"
                        }`}
                      >
                        {lineNumber}
                      </span>
                      <span className="whitespace-pre text-slate-300">{line || " "}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
          {!hasFile && (
            <div className="space-y-3 p-5">
              <p className="text-xs text-slate-500">
                This evidence is computed data rather than a file location.
              </p>
              <pre className="retro-inset overflow-x-auto whitespace-pre-wrap p-4 font-mono text-xs leading-relaxed text-blush">
                {evidence.content || evidence.title}
              </pre>
              <p className="text-[11px] text-slate-600">
                Computed from repository metadata rather than a file location.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
