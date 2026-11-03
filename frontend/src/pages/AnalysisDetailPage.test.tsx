import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AnalysisDetailPage } from "./AnalysisDetailPage";
import type { AnalysisDetail, ImpactEntry, SelectedTest } from "../types";

const getAnalysis = vi.fn();
const getTestRuns = vi.fn();

vi.mock("../services/api", () => ({
  ApiError: class ApiError extends Error {},
  api: {
    getAnalysis: (...args: unknown[]) => getAnalysis(...args),
    getTestRuns: (...args: unknown[]) => getTestRuns(...args),
  },
}));

function impactEntry(overrides: Partial<ImpactEntry>): ImpactEntry {
  return {
    node_id: "func:app/core.py::run",
    name: "run",
    qualified_name: "app.core.run",
    type: "function",
    file_path: "app/core.py",
    line_start: 1,
    line_end: 10,
    impact_type: "indirect",
    score: 80,
    depth: 1,
    reason: "Called by changed code",
    path: [],
    edge_types: ["calls"],
    confidence: 0.9,
    is_deleted: false,
    is_test: false,
    ...overrides,
  };
}

function selectedTest(overrides: Partial<SelectedTest>): SelectedTest {
  return {
    test_id: "tests/test_core.py::test_run",
    file_path: "tests/test_core.py",
    name: "test_run",
    class_name: null,
    score: 90,
    reasons: ["Executes changed code"],
    matched_direct: [],
    matched_indirect: [],
    matched_files: [],
    source: "coverage",
    previously_failed: false,
    ...overrides,
  };
}

const analysis: AnalysisDetail = {
  id: "analysis-1",
  repository_id: "repo-1",
  status: "completed",
  base_ref: "HEAD~1",
  head_ref: "WORKING",
  total_changed_files: 1,
  total_affected_entities: 2,
  analysis_duration_ms: 850,
  created_at: "2026-01-01T10:00:00Z",
  completed_at: "2026-01-01T10:00:01Z",
  error_message: null,
  changed_files: [
    {
      path: "app/core.py",
      change_type: "modified",
      added_line_count: 3,
      deleted_line_count: 1,
    },
  ],
  changed_entities: [
    {
      key: "func:app/core.py::run",
      kind: "function",
      name: "run",
      qualified_name: "app.core.run",
      file_path: "app/core.py",
      change_type: "modified",
    },
  ],
  impact: {
    repo_path: "/tmp/repo",
    changed_files: [],
    changed_entities: [],
    direct_impacts: [
      impactEntry({
        node_id: "func:app/core.py::run",
        name: "run",
        impact_type: "direct",
        score: 100,
        depth: 0,
        edge_types: [],
      }),
    ],
    indirect_impacts: [
      impactEntry({
        node_id: "func:app/api.py::handler",
        name: "handler",
        qualified_name: "app.api.handler",
        file_path: "app/api.py",
        score: 72,
      }),
    ],
    summary: {
      changed_file_count: 1,
      changed_entity_count: 1,
      direct_count: 1,
      indirect_count: 1,
      total_affected: 2,
      affected_file_count: 2,
      max_depth: 1,
      by_type: { function: 2 },
      truncated: false,
      excluded_test_nodes: 3,
    },
    warnings: [],
    methodology: "Reverse dependency traversal over static edges.",
  },
  selection: {
    coverage_available: false,
    total_tests_discovered: 20,
    measured_tests: 0,
    coverage_collected_at: null,
    safe: {
      mode: "safe",
      selected_tests: [
        selectedTest({
          test_id: "tests/test_core.py::test_safe",
          name: "test_safe",
          source: "static",
        }),
      ],
      selected_count: 1,
      total_tests: 20,
      reduction_percent: 95,
      fallback_used: false,
      warnings: [],
      rationale: "Static dependency evidence.",
    },
    optimized: {
      mode: "optimized",
      selected_tests: [
        selectedTest({ name: "test_optimized" }),
        selectedTest({
          test_id: "tests/test_api.py::test_optimized",
          name: "test_optimized",
        }),
      ],
      selected_count: 2,
      total_tests: 20,
      reduction_percent: 90,
      fallback_used: false,
      warnings: [],
      rationale: "Coverage-guided selection.",
    },
    warnings: ["Per-test coverage is not available; static evidence is used."],
    notes: ["Collect coverage to improve precision."],
  },
};

function renderPage() {
  return render(
    <MemoryRouter
      initialEntries={["/analyses/analysis-1"]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <Routes>
        <Route path="/analyses/:analysisId" element={<AnalysisDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("AnalysisDetailPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getAnalysis.mockResolvedValue(analysis);
    getTestRuns.mockResolvedValue({ runs: [], total: 0 });
  });

  it("renders the stored diff and impact summary", async () => {
    renderPage();

    expect(await screen.findByText("HEAD~1 → WORKING")).toBeInTheDocument();
    expect(screen.getAllByText("app/core.py").length).toBeGreaterThan(0);
    expect(screen.getByText("3 test nodes were excluded from traversal. Re-run the analysis with “include tests” to keep them.")).toBeInTheDocument();
    expect(screen.getByText("850 ms")).toBeInTheDocument();
    expect(screen.getByText("Impact concentration")).toBeInTheDocument();
    expect(screen.getByText("total affected")).toBeInTheDocument();
    expect(screen.getAllByText("function").length).toBeGreaterThan(0);
  });

  it("switches between optimized and safe selections and shows fallback state", async () => {
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /test selection/i }));

    expect(await screen.findByText("Fallback")).toBeInTheDocument();
    expect(screen.getByText("Per-test coverage is not available; static evidence is used.")).toBeInTheDocument();
    expect(screen.getByText("Coverage-guided selection.")).toBeInTheDocument();
    expect(screen.getAllByText("test_optimized")).toHaveLength(2);

    fireEvent.click(screen.getByRole("button", { name: "safe" }));

    expect(screen.getByText("Static dependency evidence.")).toBeInTheDocument();
    expect(screen.getByText("test_safe")).toBeInTheDocument();
    expect(screen.queryByText("test_optimized")).not.toBeInTheDocument();
    expect(screen.getByText("95.0%")).toBeInTheDocument();
  });

  it("expands an impacted entity to reveal its reason and dependency path", async () => {
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /^impact$/i }));

    expect(await screen.findByText("handler")).toBeInTheDocument();
    fireEvent.click(screen.getByText("handler"));

    expect(screen.getByText("Called by changed code")).toBeInTheDocument();
    expect(screen.getByText("edge: calls")).toBeInTheDocument();
  });
});
