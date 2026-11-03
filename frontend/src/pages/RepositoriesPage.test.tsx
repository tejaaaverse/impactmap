import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { RepositoriesPage } from "./RepositoriesPage";

const listRepositories = vi.fn();
const scanRepository = vi.fn();

vi.mock("../services/api", () => ({
  ApiError: class ApiError extends Error {},
  api: {
    listRepositories: () => listRepositories(),
    scanRepository: (...args: unknown[]) => scanRepository(...args),
  },
}));

const scanResult = {
  repository: {
    id: "repo-9",
    path: "/tmp/calculator",
    name: "calculator",
    status: "ready",
    total_files: 3,
    total_functions: 8,
    total_classes: 1,
    total_dependencies: 5,
    last_scanned_at: "2026-01-01T10:00:00Z",
    created_at: "2026-01-01T10:00:00Z",
    updated_at: "2026-01-01T10:00:00Z",
    scan_error: null,
  },
  files_discovered: 3,
  functions_discovered: 8,
  classes_discovered: 1,
  methods_discovered: 4,
  scan_duration_ms: 20,
  warnings: [],
};

function renderPage() {
  return render(
    <MemoryRouter
      initialEntries={["/repositories"]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <Routes>
        <Route path="/repositories" element={<RepositoriesPage />} />
        <Route path="/repositories/:repositoryId" element={<div>Repository destination</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("RepositoriesPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listRepositories.mockResolvedValue([]);
  });

  it("scans the entered path and navigates to the repository", async () => {
    scanRepository.mockResolvedValue(scanResult);

    renderPage();

    expect(await screen.findByText("No repositories scanned")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Repository path"), {
      target: { value: "/tmp/calculator" },
    });
    fireEvent.click(screen.getByRole("button", { name: /scan repository/i }));

    await waitFor(() =>
      expect(scanRepository).toHaveBeenCalledWith("/tmp/calculator"),
    );
    expect(await screen.findByText("Repository destination")).toBeInTheDocument();
  });

  it("validates an empty path without calling the API", async () => {
    renderPage();
    await screen.findByText("No repositories scanned");

    fireEvent.click(screen.getByRole("button", { name: /scan repository/i }));

    expect(
      screen.getByText("Enter an absolute path to a local Python repository."),
    ).toBeInTheDocument();
    expect(scanRepository).not.toHaveBeenCalled();
  });

  it("lists scanned repositories with their counts", async () => {
    listRepositories.mockResolvedValue([scanResult.repository]);

    renderPage();

    expect(await screen.findByText("calculator")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("8")).toBeInTheDocument();
  });
});
