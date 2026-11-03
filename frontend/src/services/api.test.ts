import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "./api";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("api client", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("POSTs the repository path as JSON and returns the scan result", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ repository: { id: "repo-1" }, files_discovered: 3 }, 201),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await api.scanRepository("/tmp/project");

    expect(result.repository.id).toBe("repo-1");
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/repositories/scan");
    expect(init.method).toBe("POST");
    expect(init.headers).toMatchObject({ "Content-Type": "application/json" });
    expect(JSON.parse(String(init.body))).toEqual({ path: "/tmp/project" });
  });

  it("passes graph filters as query parameters", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ nodes: [], edges: [] }));
    vi.stubGlobal("fetch", fetchMock);

    await api.getGraph("repo-1", { includeTests: false, includeModules: true });

    expect(fetchMock.mock.calls[0][0]).toBe(
      "/api/repositories/repo-1/graph?include_tests=false&include_modules=true",
    );
  });

  it("normalises FastAPI validation errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          { detail: [{ loc: ["body", "path"], msg: "Path does not exist", type: "value_error" }] },
          422,
        ),
      ),
    );

    await expect(api.scanRepository("/missing")).rejects.toMatchObject({
      name: "ApiError",
      status: 422,
      message: "Path does not exist",
    });
  });

  it("preserves string error details and exposes the status", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse({ detail: "Repository not found" }, 404)),
    );

    try {
      await api.getRepository("missing");
      throw new Error("expected rejection");
    } catch (error) {
      expect(error).toBeInstanceOf(ApiError);
      expect((error as ApiError).status).toBe(404);
      expect((error as ApiError).message).toBe("Repository not found");
    }
  });

  it("sends confirmed benchmark payloads unchanged", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ id: "bench-1" }, 201));
    vi.stubGlobal("fetch", fetchMock);

    await api.runBenchmark({
      repository_id: "repo-1",
      mode: "optimized",
      confirm: true,
      dataset_name: "sample",
    });

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toMatchObject({
      repository_id: "repo-1",
      mode: "optimized",
      confirm: true,
      dataset_name: "sample",
    });
  });

  it("sends Copilot questions to the repository-scoped endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ conversation_id: "conversation-1", message: { id: "m1" } }, 201),
    );
    vi.stubGlobal("fetch", fetchMock);

    await api.copilotChat("repo-1", {
      message: "Explain architecture",
      conversation_id: "conversation-0",
    });

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/copilot/repositories/repo-1/chat");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({
      message: "Explain architecture",
      conversation_id: "conversation-0",
    });
  });

  it("encodes repository file paths and optional line ranges", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ path: "a b.py" }));
    vi.stubGlobal("fetch", fetchMock);

    await api.getRepositoryFile("repo 1", "utils/a b.py", {
      startLine: 3,
      endLine: 9,
    });

    expect(fetchMock.mock.calls[0][0]).toBe(
      "/api/repositories/repo%201/file?path=utils%2Fa+b.py&start_line=3&end_line=9",
    );
  });

  it("filters Copilot history by repository", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ conversations: [] }));
    vi.stubGlobal("fetch", fetchMock);

    await api.listCopilotConversations("repo-1", 25);

    expect(fetchMock.mock.calls[0][0]).toBe(
      "/api/copilot/conversations?limit=25&repository_id=repo-1",
    );
  });
});
