/**
 * Typed API client for the IMPACTMAP backend.
 *
 * All requests go through `request`, which normalises FastAPI error payloads
 * (string or validation-array `detail`) into an ApiError.
 */

import type {
  AnalysisDetail,
  AnalysisList,
  BenchmarkDetail,
  BenchmarkList,
  CopilotChatResponse,
  CopilotConversationDetail,
  CopilotConversationList,
  CopilotStatus,
  CoverageCollectResult,
  CoverageSnapshot,
  DashboardStats,
  DiscoveredTests,
  GitRefs,
  GitStatus,
  Impact,
  Repository,
  RepositoryDetail,
  RepositoryFile,
  RepositoryGraph,
  RunAnalysisResult,
  ScanResult,
  Selection,
  TestMode,
  TestRun,
  TestRunHistory,
} from "../types";

const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "";

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, message: string, detail: unknown = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

function normaliseDetail(detail: unknown, fallback: string): string {
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (item && typeof item === "object" && "msg" in item) {
          return String((item as { msg: unknown }).msg);
        }
        return null;
      })
      .filter((value): value is string => Boolean(value));
    if (messages.length) return messages.join("; ");
  }
  if (detail && typeof detail === "object" && "message" in detail) {
    return String((detail as { message: unknown }).message);
  }
  return fallback;
}

async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...init.headers,
    },
  });

  if (response.status === 204) {
    return undefined as T;
  }

  const contentType = response.headers.get("content-type") ?? "";
  const payload = contentType.includes("application/json")
    ? await response.json().catch(() => null)
    : await response.text();

  if (!response.ok) {
    const detail =
      payload && typeof payload === "object" && "detail" in payload
        ? (payload as { detail: unknown }).detail
        : payload;
    throw new ApiError(
      response.status,
      normaliseDetail(detail, `Request failed with status ${response.status}`),
      detail,
    );
  }

  return payload as T;
}

function jsonBody(body: unknown): RequestInit {
  return { method: "POST", body: JSON.stringify(body) };
}

const encode = encodeURIComponent;

export const api = {
  health: () =>
    request<{ status: string; version: string; app_name: string }>("/api/health"),

  scanRepository: (path: string) =>
    request<ScanResult>("/api/repositories/scan", jsonBody({ path })),

  listRepositories: () => request<Repository[]>("/api/repositories"),

  getRepository: (repositoryId: string) =>
    request<RepositoryDetail>(`/api/repositories/${encode(repositoryId)}`),

  getGraph: (
    repositoryId: string,
    options: { includeTests?: boolean; includeModules?: boolean } = {},
  ) => {
    const params = new URLSearchParams();
    if (options.includeTests !== undefined) {
      params.set("include_tests", String(options.includeTests));
    }
    if (options.includeModules !== undefined) {
      params.set("include_modules", String(options.includeModules));
    }
    const query = params.toString();
    return request<RepositoryGraph>(
      `/api/repositories/${encode(repositoryId)}/graph${query ? `?${query}` : ""}`,
    );
  },

  getRepositoryTests: (repositoryId: string) =>
    request<DiscoveredTests>(`/api/repositories/${encode(repositoryId)}/tests`),

  getCoverage: (repositoryId: string) =>
    request<CoverageSnapshot[]>(
      `/api/repositories/${encode(repositoryId)}/coverage`,
    ),

  collectCoverage: (
    repositoryId: string,
    body: { test_ids?: string[] | null; confirm: boolean; timeout_seconds?: number },
  ) =>
    request<CoverageCollectResult>(
      `/api/repositories/${encode(repositoryId)}/coverage`,
      jsonBody(body),
    ),

  getGitStatus: (repositoryId: string) =>
    request<GitStatus>(`/api/repositories/${encode(repositoryId)}/git-status`),

  getGitRefs: (repositoryId: string) =>
    request<GitRefs>(`/api/repositories/${encode(repositoryId)}/git-refs`),

  getRepositoryFile: (
    repositoryId: string,
    path: string,
    options: { startLine?: number; endLine?: number } = {},
  ) => {
    const params = new URLSearchParams({ path });
    if (options.startLine !== undefined) {
      params.set("start_line", String(options.startLine));
    }
    if (options.endLine !== undefined) {
      params.set("end_line", String(options.endLine));
    }
    return request<RepositoryFile>(
      `/api/repositories/${encode(repositoryId)}/file?${params.toString()}`,
    );
  },

  analyzeRepository: (
    repositoryId: string,
    body: { base_ref?: string; head_ref?: string; include_tests?: boolean } = {},
  ) =>
    request<RunAnalysisResult>(
      `/api/repositories/${encode(repositoryId)}/analyze`,
      jsonBody({
        base_ref: body.base_ref ?? "HEAD~1",
        head_ref: body.head_ref ?? "WORKING",
        include_tests: body.include_tests ?? false,
      }),
    ),

  listAnalyses: (repositoryId?: string) => {
    const query = repositoryId
      ? `?repository_id=${encode(repositoryId)}`
      : "";
    return request<AnalysisList>(`/api/analysis${query}`);
  },

  getAnalysis: (analysisId: string) =>
    request<AnalysisDetail>(`/api/analysis/${encode(analysisId)}`),

  getImpact: (analysisId: string) =>
    request<Impact>(`/api/analysis/${encode(analysisId)}/impact`),

  getSelection: (analysisId: string) =>
    request<Selection>(`/api/analysis/${encode(analysisId)}/tests`),

  runTests: (
    analysisId: string,
    body: {
      mode: TestMode;
      test_ids?: string[] | null;
      confirm: boolean;
      collect_coverage?: boolean;
      timeout_seconds?: number;
    },
  ) =>
    request<TestRun>(
      `/api/analysis/${encode(analysisId)}/run-tests`,
      jsonBody(body),
    ),

  getTestRuns: (analysisId: string) =>
    request<TestRunHistory>(
      `/api/analysis/${encode(analysisId)}/test-runs`,
    ),

  listBenchmarks: (repositoryId?: string) => {
    const query = repositoryId
      ? `?repository_id=${encode(repositoryId)}`
      : "";
    return request<BenchmarkList>(`/api/benchmarks${query}`);
  },

  getBenchmark: (benchmarkId: string) =>
    request<BenchmarkDetail>(`/api/benchmarks/${encode(benchmarkId)}`),

  runBenchmark: (body: {
    repository_id: string;
    analysis_id?: string | null;
    base_ref?: string;
    head_ref?: string;
    mode?: "safe" | "optimized";
    dataset_name?: string | null;
    confirm: boolean;
    timeout_seconds?: number;
  }) =>
    request<BenchmarkDetail>("/api/benchmarks/run", jsonBody(body)),

  getDashboard: () => request<DashboardStats>("/api/dashboard"),

  copilotStatus: () => request<CopilotStatus>("/api/copilot/status"),

  copilotChat: (
    repositoryId: string,
    body: { message: string; conversation_id?: string | null },
  ) =>
    request<CopilotChatResponse>(
      `/api/copilot/repositories/${encode(repositoryId)}/chat`,
      jsonBody(body),
    ),

  listCopilotConversations: (repositoryId?: string, limit = 50) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (repositoryId) params.set("repository_id", repositoryId);
    return request<CopilotConversationList>(
      `/api/copilot/conversations?${params.toString()}`,
    );
  },

  getCopilotConversation: (conversationId: string) =>
    request<CopilotConversationDetail>(
      `/api/copilot/conversations/${encode(conversationId)}`,
    ),

  deleteCopilotConversation: (conversationId: string) =>
    request<void>(`/api/copilot/conversations/${encode(conversationId)}`, {
      method: "DELETE",
    }),
};
