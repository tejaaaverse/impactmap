/**
 * API types mirroring the FastAPI/Pydantic schemas.
 * Keep this file in sync with backend/app/schemas/schemas.py.
 */

export interface CodeEntity {
  id: string;
  name: string;
  qualified_name: string;
  entity_type: string;
  file_path: string;
  line_start: number | null;
  line_end: number | null;
  docstring: string | null;
  decorators: string[] | null;
}

export interface Repository {
  id: string;
  path: string;
  name: string;
  status: string;
  total_files: number;
  total_functions: number;
  total_classes: number;
  total_dependencies: number;
  last_scanned_at: string | null;
  created_at: string;
  updated_at: string;
  scan_error: string | null;
}

export interface RepositoryDetail extends Repository {
  entities: CodeEntity[];
  is_git_repository: boolean;
  scan_stats: Record<string, unknown>;
}

export interface ScanResult {
  repository: Repository;
  files_discovered: number;
  functions_discovered: number;
  classes_discovered: number;
  methods_discovered: number;
  dependencies_discovered: number;
  directories_explored: number;
  files_parsed: number;
  files_skipped: number;
  files_with_errors: number;
  imports_discovered: number;
  parse_errors: string[];
  scan_duration_ms: number;
  warnings: string[];
}

export interface GraphNode {
  id: string;
  name: string;
  qualified_name: string;
  type: string;
  file_path: string;
  line_start: number;
  line_end: number;
  module_name: string;
  is_test: boolean;
  parent_id: string | null;
  key: string;
  metadata: Record<string, unknown>;
}

export interface GraphEdge {
  source: string;
  target: string;
  type: string;
  line: number;
  confidence: number;
  reason: string;
}

export interface GraphStats {
  nodes: number;
  edges: number;
  node_types: Record<string, number>;
  edge_types: Record<string, number>;
  test_nodes: number;
  unresolved_imports: number;
}

export interface RepositoryGraph {
  repo_path: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  stats: GraphStats;
  warnings: string[];
  unresolved_imports: Record<string, unknown>[];
}

export interface AnalysisSummary {
  id: string;
  repository_id: string;
  status: string;
  base_ref: string | null;
  head_ref: string | null;
  total_changed_files: number;
  total_affected_entities: number;
  analysis_duration_ms: number | null;
  created_at: string;
  completed_at: string | null;
  error_message: string | null;
}

export interface ImpactPathStep {
  node_id?: string;
  name?: string;
  type?: string;
  file_path?: string;
  edge_type?: string;
  [key: string]: unknown;
}

export interface ImpactEntry {
  node_id: string;
  name: string;
  qualified_name: string;
  type: string;
  file_path: string;
  line_start: number;
  line_end: number;
  impact_type: string;
  score: number;
  depth: number;
  reason: string;
  path: ImpactPathStep[];
  edge_types: string[];
  confidence: number;
  is_deleted: boolean;
  is_test: boolean;
}

export interface ChangedFile {
  path?: string;
  change_type?: string;
  status?: string;
  additions?: number;
  deletions?: number;
  is_deleted?: boolean;
  [key: string]: unknown;
}

export interface ImpactSummaryStats {
  changed_file_count: number;
  changed_entity_count: number;
  direct_count: number;
  indirect_count: number;
  total_affected: number;
  affected_file_count: number;
  max_depth: number;
  by_type: Record<string, number>;
  truncated: boolean;
  excluded_test_nodes: number;
}

export interface Impact {
  repo_path: string;
  changed_files: ChangedFile[];
  changed_entities: Record<string, unknown>[];
  direct_impacts: ImpactEntry[];
  indirect_impacts: ImpactEntry[];
  summary: ImpactSummaryStats;
  warnings: string[];
  methodology: string;
}

export interface SelectedTest {
  test_id: string;
  file_path: string;
  name: string;
  class_name: string | null;
  score: number;
  reasons: string[];
  matched_direct: string[];
  matched_indirect: string[];
  matched_files: string[];
  source: string;
  previously_failed: boolean;
}

export interface ModeSelection {
  mode: string;
  selected_tests: SelectedTest[];
  selected_count: number;
  total_tests: number;
  reduction_percent: number;
  fallback_used: boolean;
  warnings: string[];
  rationale: string;
}

export interface Selection {
  coverage_available: boolean;
  total_tests_discovered: number;
  measured_tests: number;
  coverage_collected_at: string | null;
  safe: ModeSelection | null;
  optimized: ModeSelection | null;
  warnings: string[];
  notes: string[];
}

export interface AnalysisDetail extends AnalysisSummary {
  changed_files: ChangedFile[];
  changed_entities: Record<string, unknown>[];
  impact: Impact | null;
  selection: Selection | null;
}

export interface AnalysisList {
  analyses: AnalysisSummary[];
  total: number;
}

export interface RunAnalysisResult {
  analysis: AnalysisDetail;
  graph_stats: GraphStats;
}

export interface DiscoveredTest {
  node_id: string;
  file_path: string;
  name: string;
  class_name: string | null;
  line_start: number;
  line_end: number;
  module_name: string;
}

export interface DiscoveredTests {
  repository_id: string;
  tests: DiscoveredTest[];
  total: number;
}

export interface CoverageSnapshot {
  id: string;
  repository_id: string;
  status: string;
  collected_at: string;
  duration_ms: number | null;
  total_tests: number;
  measured_tests: number;
  covered_files: number;
  error_message: string | null;
  warnings: string[];
}

export interface CoverageCollectResult {
  snapshot: CoverageSnapshot;
  execution: TestExecution;
  merged_with_previous: boolean;
}

export interface TestResultItem {
  test_id: string;
  status: string;
  duration_ms: number | null;
}

export interface TestExecution {
  status: string;
  exit_code: number | null;
  test_ids: string[];
  total_tests: number;
  passed: number;
  failed: number;
  errors: number;
  skipped: number;
  duration_ms: number;
  timed_out: boolean;
  results: TestResultItem[];
  stdout_tail: string;
  stderr_tail: string;
  warnings: string[];
  command: string[];
}

export type TestMode = "full" | "safe" | "optimized" | "custom";

export interface TestRun {
  id: string;
  repository_id: string;
  analysis_id: string | null;
  mode: string;
  status: string;
  exit_code: number | null;
  total_tests: number;
  passed: number;
  failed: number;
  errors: number;
  skipped: number;
  duration_ms: number | null;
  timed_out: boolean;
  created_at: string;
  execution: TestExecution;
  coverage_snapshot_id: string | null;
  warnings: string[];
}

export interface TestRunHistory {
  runs: TestRun[];
  total: number;
}

export interface Benchmark {
  id: string;
  repository_id: string;
  analysis_id: string | null;
  dataset_name: string | null;
  mode: string;
  base_ref: string | null;
  head_ref: string | null;
  total_tests: number;
  selected_tests: number;
  full_duration_ms: number | null;
  selected_duration_ms: number | null;
  analysis_duration_ms: number | null;
  reduction_percent: number | null;
  selection_precision: number | null;
  selection_recall: number | null;
  metrics: Record<string, unknown> | null;
  notes: Record<string, unknown> | null;
  error_message: string | null;
  created_at: string;
}

export interface BenchmarkDetail extends Benchmark {
  full_run: TestExecution | null;
  selected_run: TestExecution | null;
}

export interface BenchmarkList {
  benchmarks: Benchmark[];
  total: number;
}

export interface DashboardStats {
  repositories: number;
  analyses: number;
  completed_analyses: number;
  benchmark_runs: number;
  test_runs: number;
  coverage_snapshots: number;
  total_tracked_tests: number;
  average_analysis_ms: number | null;
  average_selection_reduction: number | null;
  recent_analyses: AnalysisSummary[];
  recent_benchmarks: Benchmark[];
}

export interface GitStatus {
  repository_id: string;
  is_git_repository: boolean;
}

// ──────────────────────────── Copilot ────────────────────────────

export interface CopilotStatus {
  ai_enabled: boolean;
  provider: string;
  model: string;
  base_url: string;
  key_configured: boolean;
  retrieval: string;
  max_context_chars: number;
  retrieval_top_k: number;
  max_history_messages: number;
  setup: string;
}

export interface CopilotEvidence {
  id: string;
  kind: string;
  title: string;
  content: string;
  file_path: string;
  line_start: number;
  line_end: number;
  reason: string;
  score: number;
}

export interface CopilotMessage {
  id: string;
  conversation_id: string;
  role: string;
  content: string;
  intent: string | null;
  model: string | null;
  ai_enabled: boolean;
  evidence: CopilotEvidence[];
  follow_ups: string[];
  warnings: string[];
  error: string | null;
  latency_ms: number | null;
  created_at: string;
}

export interface CopilotChatResponse {
  conversation_id: string;
  message: CopilotMessage;
  ai_enabled: boolean;
  intent: string;
  evidence: CopilotEvidence[];
  follow_ups: string[];
  warnings: string[];
  model: string | null;
  latency_ms: number;
}

export interface CopilotConversationSummary {
  id: string;
  repository_id: string;
  title: string;
  message_count: number;
  last_message_preview: string;
  created_at: string;
  updated_at: string;
}

export interface CopilotConversationList {
  conversations: CopilotConversationSummary[];
  total: number;
}

export interface CopilotConversationDetail {
  conversation: CopilotConversationSummary;
  messages: CopilotMessage[];
}

export interface GitCommit {
  sha: string;
  short_sha: string;
  author: string;
  committed_at: string;
  subject: string;
}

export interface GitRefs {
  repo_path: string;
  is_repository: boolean;
  commit_count: number;
  current_branch: string;
  commits: GitCommit[];
  branches: string[];
  root_commit: string;
  head_commit: string;
  dirty: boolean;
  staged_files: number;
  unstaged_files: number;
  untracked_files: number;
  recommended_base: string;
  recommended_head: string;
  warnings: string[];
  error: string | null;
}

export interface RepositoryFile {
  path: string;
  content: string;
  line_count: number;
  size_bytes: number;
  truncated: boolean;
  language: string;
  start_line: number | null;
  end_line: number | null;
}
