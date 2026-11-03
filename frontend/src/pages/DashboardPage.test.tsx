import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { DashboardPage } from "./DashboardPage";
import type { DashboardStats } from "../types";

const getDashboard = vi.fn();
const getRepository = vi.fn();
const listRepositories = vi.fn();
const listBenchmarks = vi.fn();
const listAnalyses = vi.fn();
const getAnalysis = vi.fn();
const scanRepository = vi.fn();

vi.mock("../services/api", () => ({
  ApiError: class ApiError extends Error {},
  api: {
    getDashboard: () => getDashboard(),
    getRepository: (...args: unknown[]) => getRepository(...args),
    listRepositories: () => listRepositories(),
    listBenchmarks: () => listBenchmarks(),
    listAnalyses: () => listAnalyses(),
    getAnalysis: (...args: unknown[]) => getAnalysis(...args),
    scanRepository: (...args: unknown[]) => scanRepository(...args),
  },
}));

const dashboard: DashboardStats = {
  repositories: 2,
  analyses: 7,
  completed_analyses: 6,
  benchmark_runs: 3,
  test_runs: 11,
  coverage_snapshots: 4,
  total_tracked_tests: 42,
  average_analysis_ms: 1500,
  average_selection_reduction: 63.4,
  recent_analyses: [
    {
      id: "analysis-1",
      repository_id: "repo-1",
      status: "completed",
      base_ref: "HEAD~1",
      head_ref: "WORKING",
      total_changed_files: 2,
      total_affected_entities: 9,
      analysis_duration_ms: 1200,
      created_at: "2026-01-01T10:00:00Z",
      completed_at: "2026-01-01T10:00:01Z",
      error_message: null,
    },
  ],
  recent_benchmarks: [],
};

describe("DashboardPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getDashboard.mockResolvedValue(dashboard);
  });

  it("renders measured dashboard values from the API", async () => {
    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <DashboardPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("HELLO, DEVELOPER!")).toBeInTheDocument();
    expect(screen.getByText("Welcome to your code universe.")).toBeInTheDocument();
    expect(
      screen.getByText(
        /Explore your repositories\.\s+Discover code impact\.\s+Make testing smarter\./,
      ),
    ).toBeInTheDocument();
    expect(await screen.findByText("Impact intelligence at a glance")).toBeInTheDocument();
    expect(await screen.findByText("1.50 s")).toBeInTheDocument();
    expect(screen.getByText("63.4%")).toBeInTheDocument();
    expect(screen.getByText("11")).toBeInTheDocument();
    expect(screen.getByText("HEAD~1 → WORKING")).toBeInTheDocument();
    expect(screen.getByText("No benchmark measurements yet")).toBeInTheDocument();
  });

  it("shows an empty state when no analyses exist", async () => {
    getDashboard.mockResolvedValue({
      ...dashboard,
      analyses: 0,
      completed_analyses: 0,
      recent_analyses: [],
    });

    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <DashboardPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("No analyses yet")).toBeInTheDocument();
  });

  it("surfaces API failures with a retry action", async () => {
    getDashboard.mockRejectedValue(new Error("backend unavailable"));

    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <DashboardPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Something went wrong")).toBeInTheDocument();
    expect(screen.getByText("backend unavailable")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
    await waitFor(() => expect(getDashboard).toHaveBeenCalledTimes(1));
  });
});
