import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { CopilotPage } from "./CopilotPage";
import type {
  CopilotChatResponse,
  CopilotConversationDetail,
  CopilotStatus,
  Repository,
} from "../types";

const listRepositories = vi.fn();
const copilotStatus = vi.fn();
const listCopilotConversations = vi.fn();
const getCopilotConversation = vi.fn();
const deleteCopilotConversation = vi.fn();
const copilotChat = vi.fn();
const getRepositoryFile = vi.fn();

vi.mock("../services/api", () => ({
  ApiError: class ApiError extends Error {},
  api: {
    listRepositories: () => listRepositories(),
    copilotStatus: () => copilotStatus(),
    listCopilotConversations: (...args: unknown[]) => listCopilotConversations(...args),
    getCopilotConversation: (...args: unknown[]) => getCopilotConversation(...args),
    deleteCopilotConversation: (...args: unknown[]) => deleteCopilotConversation(...args),
    copilotChat: (...args: unknown[]) => copilotChat(...args),
    getRepositoryFile: (...args: unknown[]) => getRepositoryFile(...args),
  },
}));

const repository: Repository = {
  id: "repo-1",
  path: "/tmp/calculator",
  name: "calculator",
  status: "ready",
  total_files: 9,
  total_functions: 18,
  total_classes: 2,
  total_dependencies: 28,
  last_scanned_at: "2026-01-01T10:00:00Z",
  created_at: "2026-01-01T10:00:00Z",
  updated_at: "2026-01-01T10:00:00Z",
  scan_error: null,
};

const status: CopilotStatus = {
  ai_enabled: false,
  provider: "openai-compatible",
  model: "gpt-test",
  base_url: "https://example.invalid/v1",
  key_configured: false,
  retrieval: "BM25 over files/symbols plus dependency-graph expansion",
  max_context_chars: 24000,
  retrieval_top_k: 12,
  max_history_messages: 8,
  setup: "Configure LLM_API_KEY in backend/.env to enable model-written answers.",
};

const chatResponse: CopilotChatResponse = {
  conversation_id: "conversation-1",
  ai_enabled: false,
  intent: "explain",
  model: null,
  latency_ms: 42,
  follow_ups: ["Which tests cover this file?"],
  warnings: [],
  evidence: [
    {
      id: "E1",
      kind: "file",
      title: "utils/math_helpers.py",
      content: "def add(a, b):\n    return a + b",
      file_path: "utils/math_helpers.py",
      line_start: 1,
      line_end: 2,
      reason: "Retrieved by BM25",
      score: 4.2,
    },
  ],
  message: {
    id: "message-2",
    conversation_id: "conversation-1",
    role: "assistant",
    content:
      "`utils/math_helpers.py` contains the arithmetic helpers [E1].\n\n- It is imported by `main.py`.",
    intent: "explain",
    model: null,
    ai_enabled: false,
    evidence: [
      {
        id: "E1",
        kind: "file",
        title: "utils/math_helpers.py",
        content: "def add(a, b):\n    return a + b",
        file_path: "utils/math_helpers.py",
        line_start: 1,
        line_end: 2,
        reason: "Retrieved by BM25",
        score: 4.2,
      },
    ],
    follow_ups: ["Which tests cover this file?"],
    warnings: [],
    error: null,
    latency_ms: 42,
    created_at: "2026-01-01T10:00:00Z",
  },
};

const conversationDetail: CopilotConversationDetail = {
  conversation: {
    id: "conversation-1",
    repository_id: "repo-1",
    title: "Architecture overview",
    message_count: 2,
    last_message_preview: "The repository is split into modules.",
    created_at: "2026-01-01T10:00:00Z",
    updated_at: "2026-01-01T10:00:00Z",
  },
  messages: [
    {
      id: "message-1",
      conversation_id: "conversation-1",
      role: "user",
      content: "Explain the architecture",
      intent: null,
      model: null,
      ai_enabled: false,
      evidence: [],
      follow_ups: [],
      warnings: [],
      error: null,
      latency_ms: null,
      created_at: "2026-01-01T10:00:00Z",
    },
    {
      id: "message-2",
      conversation_id: "conversation-1",
      role: "assistant",
      content: "The repository is split into modules [E1].",
      intent: "explain",
      model: null,
      ai_enabled: false,
      evidence: chatResponse.evidence,
      follow_ups: [],
      warnings: [],
      error: null,
      latency_ms: 12,
      created_at: "2026-01-01T10:00:01Z",
    },
  ],
};

function renderPage() {
  return render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <CopilotPage />
    </MemoryRouter>,
  );
}

describe("CopilotPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listRepositories.mockResolvedValue([repository]);
    copilotStatus.mockResolvedValue(status);
    listCopilotConversations.mockResolvedValue({ conversations: [], total: 0 });
    deleteCopilotConversation.mockResolvedValue(undefined);
    getRepositoryFile.mockResolvedValue({
      path: "utils/math_helpers.py",
      content: "def add(a, b):\n    return a + b",
      line_count: 2,
      size_bytes: 40,
      truncated: false,
      language: "python",
      start_line: 1,
      end_line: 2,
    });
  });

  it("shows local evidence mode and asks a grounded question", async () => {
    copilotChat.mockResolvedValue(chatResponse);
    renderPage();

    expect(await screen.findByText(/Local evidence mode/)).toBeInTheDocument();
    expect(screen.getByText(repository.path)).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: /Explain the overall architecture/i }),
    );

    await waitFor(() =>
      expect(copilotChat).toHaveBeenCalledWith("repo-1", {
        message: "Explain the overall architecture of this repository.",
        conversation_id: null,
      }),
    );
    expect(
      await screen.findByText(/contains the arithmetic helpers/i),
    ).toBeInTheDocument();
    expect(screen.getByText("Which tests cover this file?")).toBeInTheDocument();
    expect(listCopilotConversations).toHaveBeenCalledTimes(2);
  });

  it("opens a cited file in the evidence drawer with line numbers", async () => {
    copilotChat.mockResolvedValue(chatResponse);
    renderPage();

    fireEvent.click(
      await screen.findByRole("button", { name: /Explain the overall architecture/i }),
    );

    fireEvent.click(await screen.findByRole("button", { name: "Show evidence E1" }));

    await waitFor(() =>
      expect(getRepositoryFile).toHaveBeenCalledWith("repo-1", "utils/math_helpers.py", {
        startLine: 1,
        endLine: 10,
      }),
    );
    expect(await screen.findByText("def add(a, b):")).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("loads a saved conversation and deletes it after confirmation", async () => {
    listCopilotConversations.mockResolvedValue({
      conversations: [conversationDetail.conversation],
      total: 1,
    });
    getCopilotConversation.mockResolvedValue(conversationDetail);
    renderPage();

    fireEvent.click(
      await screen.findByRole("button", {
        name: "Open conversation Architecture overview",
      }),
    );
    expect(
      await screen.findByText(/The repository is split into modules/i),
    ).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: /Delete conversation Architecture overview/i }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Delete conversation" }));

    await waitFor(() =>
      expect(deleteCopilotConversation).toHaveBeenCalledWith("conversation-1"),
    );
    await waitFor(() =>
      expect(screen.queryByText("Architecture overview")).not.toBeInTheDocument(),
    );
  });

  it("shows the empty state when no repositories are scanned", async () => {
    listRepositories.mockResolvedValue([]);
    renderPage();

    expect(await screen.findByText("No repositories scanned")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Scan a repository/i })).toBeInTheDocument();
  });
});
