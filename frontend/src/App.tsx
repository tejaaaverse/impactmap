import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { DashboardPage } from "./pages/DashboardPage";
import { RepositoriesPage } from "./pages/RepositoriesPage";
import { RepositoryDetailPage } from "./pages/RepositoryDetailPage";
import { AnalysesPage } from "./pages/AnalysesPage";
import { AnalysisDetailPage } from "./pages/AnalysisDetailPage";
import { BenchmarksPage } from "./pages/BenchmarksPage";
import { CopilotPage } from "./pages/CopilotPage";

export function App() {
  return (
    <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<DashboardPage />} />
          <Route path="repositories" element={<RepositoriesPage />} />
          <Route path="repositories/:repositoryId" element={<RepositoryDetailPage />} />
          <Route path="analyses" element={<AnalysesPage />} />
          <Route path="analyses/:analysisId" element={<AnalysisDetailPage />} />
          <Route path="benchmarks" element={<BenchmarksPage />} />
          <Route path="copilot" element={<CopilotPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
