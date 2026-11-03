"""
Pydantic schemas for API request/response serialization.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ──────────────────────────── Repository ────────────────────────────


class RepositoryScanRequest(BaseModel):
    """Request body for scanning a repository."""

    path: str = Field(..., description="Absolute path to the local repository")

    @field_validator("path")
    @classmethod
    def validate_path(cls, v: str) -> str:
        p = Path(v).resolve()
        if not p.exists():
            raise ValueError(f"Path does not exist: {v}")
        if not p.is_dir():
            raise ValueError(f"Path is not a directory: {v}")
        return str(p)


class CodeEntityResponse(BaseModel):
    """A discovered code entity."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    qualified_name: str
    entity_type: str
    file_path: str
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    docstring: Optional[str] = None
    decorators: Optional[list[str]] = None


class RepositoryResponse(BaseModel):
    """Repository summary response."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    path: str
    name: str
    status: str
    total_files: int = 0
    total_functions: int = 0
    total_classes: int = 0
    total_dependencies: int = 0
    last_scanned_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    scan_error: Optional[str] = None


class RepositoryDetailResponse(RepositoryResponse):
    """Repository detail response with entities and scan evidence."""

    entities: list[CodeEntityResponse] = []
    is_git_repository: bool = False
    scan_stats: dict[str, Any] = Field(default_factory=dict)


class ScanResultResponse(BaseModel):
    """Response returned after a scan operation."""

    repository: RepositoryResponse
    files_discovered: int
    functions_discovered: int
    classes_discovered: int
    methods_discovered: int
    dependencies_discovered: int = 0
    directories_explored: int = 0
    files_parsed: int = 0
    files_skipped: int = 0
    files_with_errors: int = 0
    imports_discovered: int = 0
    parse_errors: list[str] = []
    scan_duration_ms: float
    warnings: list[str] = []


# ──────────────────────────── Graph ────────────────────────────


class GraphNodeResponse(BaseModel):
    id: str
    name: str
    qualified_name: str
    type: str
    file_path: str
    line_start: int = 0
    line_end: int = 0
    module_name: str = ""
    is_test: bool = False
    parent_id: Optional[str] = None
    key: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphEdgeResponse(BaseModel):
    source: str
    target: str
    type: str
    line: int = 0
    confidence: float = 0.9
    reason: str = ""


class GraphStatsResponse(BaseModel):
    nodes: int = 0
    edges: int = 0
    node_types: dict[str, int] = Field(default_factory=dict)
    edge_types: dict[str, int] = Field(default_factory=dict)
    test_nodes: int = 0
    unresolved_imports: int = 0


class GraphResponse(BaseModel):
    repo_path: str
    nodes: list[GraphNodeResponse]
    edges: list[GraphEdgeResponse]
    stats: GraphStatsResponse
    warnings: list[str] = []
    unresolved_imports: list[dict[str, Any]] = []


# ──────────────────────────── Analysis ────────────────────────────


class AnalysisRequest(BaseModel):
    """Request body for starting an impact analysis."""

    base_ref: str = Field(default="HEAD~1", description="Git ref to compare against")
    head_ref: str = Field(
        default="WORKING",
        description="Git ref to compare against the base, or WORKING for the working tree",
    )
    include_tests: bool = Field(
        default=False, description="Include test nodes in the impact graph traversal"
    )

    @field_validator("base_ref", "head_ref")
    @classmethod
    def non_empty_ref(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Git refs cannot be empty")
        return value


class ImpactEntryResponse(BaseModel):
    node_id: str
    name: str
    qualified_name: str
    type: str
    file_path: str
    line_start: int = 0
    line_end: int = 0
    impact_type: str
    score: float
    depth: int = 0
    reason: str = ""
    path: list[dict[str, Any]] = []
    edge_types: list[str] = []
    confidence: float = 1.0
    is_deleted: bool = False
    is_test: bool = False


class ImpactSummaryResponse(BaseModel):
    changed_file_count: int = 0
    changed_entity_count: int = 0
    direct_count: int = 0
    indirect_count: int = 0
    total_affected: int = 0
    affected_file_count: int = 0
    max_depth: int = 0
    by_type: dict[str, int] = Field(default_factory=dict)
    truncated: bool = False
    excluded_test_nodes: int = 0


class ImpactResponse(BaseModel):
    repo_path: str
    changed_files: list[dict[str, Any]] = []
    changed_entities: list[dict[str, Any]] = []
    direct_impacts: list[ImpactEntryResponse] = []
    indirect_impacts: list[ImpactEntryResponse] = []
    summary: ImpactSummaryResponse = Field(default_factory=ImpactSummaryResponse)
    warnings: list[str] = []
    methodology: str = ""


class SelectedTestResponse(BaseModel):
    test_id: str
    file_path: str
    name: str
    class_name: Optional[str] = None
    score: float
    reasons: list[str] = []
    matched_direct: list[str] = []
    matched_indirect: list[str] = []
    matched_files: list[str] = []
    source: str
    previously_failed: bool = False


class ModeSelectionResponse(BaseModel):
    mode: str
    selected_tests: list[SelectedTestResponse] = []
    selected_count: int
    total_tests: int
    reduction_percent: float
    fallback_used: bool
    warnings: list[str] = []
    rationale: str = ""


class SelectionResponse(BaseModel):
    coverage_available: bool
    total_tests_discovered: int
    measured_tests: int = 0
    coverage_collected_at: Optional[str] = None
    safe: Optional[ModeSelectionResponse] = None
    optimized: Optional[ModeSelectionResponse] = None
    warnings: list[str] = []
    notes: list[str] = []


class AnalysisResponse(BaseModel):
    """Analysis summary response."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    repository_id: str
    status: str
    base_ref: Optional[str] = None
    head_ref: Optional[str] = None
    total_changed_files: int = 0
    total_affected_entities: int = 0
    analysis_duration_ms: Optional[float] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None


class AnalysisDetailResponse(AnalysisResponse):
    changed_files: list[dict[str, Any]] = []
    changed_entities: list[dict[str, Any]] = []
    impact: Optional[ImpactResponse] = None
    selection: Optional[SelectionResponse] = None


class AnalysisListResponse(BaseModel):
    analyses: list[AnalysisResponse] = []
    total: int = 0


class DiscoveredTestResponse(BaseModel):
    node_id: str
    file_path: str
    name: str
    class_name: Optional[str] = None
    line_start: int = 0
    line_end: int = 0
    module_name: str = ""


class DiscoveredTestsResponse(BaseModel):
    repository_id: str
    tests: list[DiscoveredTestResponse] = []
    total: int = 0


class RunAnalysisResponse(BaseModel):
    analysis: AnalysisDetailResponse
    graph_stats: GraphStatsResponse


# ──────────────────────────── Coverage ────────────────────────────


class CoverageSnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    repository_id: str
    status: str
    collected_at: datetime
    duration_ms: Optional[float] = None
    total_tests: int = 0
    measured_tests: int = 0
    covered_files: int = 0
    error_message: Optional[str] = None
    warnings: list[str] = []


class CoverageCollectRequest(BaseModel):
    test_ids: Optional[list[str]] = Field(
        default=None,
        description="Optional subset of test IDs. Omit to measure the full suite.",
    )
    confirm: bool = Field(
        default=False,
        description="Must be true: test code is executed in a subprocess.",
    )
    timeout_seconds: Optional[int] = Field(default=None, ge=1, le=3600)


class CoverageCollectResponse(BaseModel):
    snapshot: CoverageSnapshotResponse
    execution: "TestExecutionResponse"
    merged_with_previous: bool = False


# ──────────────────────────── Test execution ────────────────────────────


TestMode = Literal["full", "safe", "optimized", "custom"]


class TestRunRequest(BaseModel):
    mode: TestMode = Field(default="optimized")
    test_ids: Optional[list[str]] = Field(
        default=None, description="Required when mode=custom"
    )
    confirm: bool = Field(
        default=False,
        description="Explicit confirmation that repository test code will be executed.",
    )
    collect_coverage: bool = Field(
        default=False,
        description="Collect per-test coverage for this run and merge it into the repository snapshot.",
    )
    timeout_seconds: Optional[int] = Field(default=None, ge=1, le=3600)


class TestResultItem(BaseModel):
    test_id: str
    status: str
    duration_ms: Optional[float] = None


class TestExecutionResponse(BaseModel):
    status: str
    exit_code: Optional[int] = None
    test_ids: list[str] = []
    total_tests: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    duration_ms: float = 0
    timed_out: bool = False
    results: list[TestResultItem] = []
    stdout_tail: str = ""
    stderr_tail: str = ""
    warnings: list[str] = []
    command: list[str] = []


class TestRunResponse(BaseModel):
    id: str
    repository_id: str
    analysis_id: Optional[str] = None
    mode: str
    status: str
    exit_code: Optional[int] = None
    total_tests: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    duration_ms: Optional[float] = None
    timed_out: bool = False
    created_at: datetime
    execution: TestExecutionResponse
    coverage_snapshot_id: Optional[str] = None
    warnings: list[str] = []


class TestRunHistoryResponse(BaseModel):
    runs: list[TestRunResponse] = []
    total: int = 0


# ──────────────────────────── Benchmarks ────────────────────────────


class BenchmarkRequest(BaseModel):
    repository_id: str
    analysis_id: Optional[str] = Field(
        default=None,
        description="Reuse an existing analysis. When omitted a fresh analysis is created.",
    )
    base_ref: str = "HEAD~1"
    head_ref: str = "WORKING"
    mode: Literal["safe", "optimized"] = "optimized"
    dataset_name: Optional[str] = None
    confirm: bool = Field(
        default=False,
        description="Must be true: both the full and selected suites are executed.",
    )
    timeout_seconds: Optional[int] = Field(default=None, ge=1, le=7200)


class BenchmarkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    repository_id: str
    analysis_id: Optional[str] = None
    dataset_name: Optional[str] = None
    mode: str
    base_ref: Optional[str] = None
    head_ref: Optional[str] = None
    total_tests: int = 0
    selected_tests: int = 0
    full_duration_ms: Optional[float] = None
    selected_duration_ms: Optional[float] = None
    analysis_duration_ms: Optional[float] = None
    reduction_percent: Optional[float] = None
    selection_precision: Optional[float] = None
    selection_recall: Optional[float] = None
    metrics: Optional[dict[str, Any]] = None
    notes: Optional[dict[str, Any]] = None
    error_message: Optional[str] = None
    created_at: datetime


class BenchmarkDetailResponse(BenchmarkResponse):
    full_run: Optional[TestExecutionResponse] = None
    selected_run: Optional[TestExecutionResponse] = None


class BenchmarkListResponse(BaseModel):
    benchmarks: list[BenchmarkResponse] = []
    total: int = 0


# ──────────────────────────── Dashboard ────────────────────────────


class DashboardStatsResponse(BaseModel):
    repositories: int = 0
    analyses: int = 0
    completed_analyses: int = 0
    benchmark_runs: int = 0
    test_runs: int = 0
    coverage_snapshots: int = 0
    total_tracked_tests: int = 0
    average_analysis_ms: Optional[float] = None
    average_selection_reduction: Optional[float] = None
    recent_analyses: list[AnalysisResponse] = []
    recent_benchmarks: list[BenchmarkResponse] = []


# ──────────────────────────── Copilot ────────────────────────────


class CopilotStatusResponse(BaseModel):
    """Safe, credential-free description of Copilot configuration."""

    ai_enabled: bool = False
    provider: str = "openai-compatible"
    model: str = ""
    base_url: str = ""
    key_configured: bool = False
    retrieval: str = ""
    max_context_chars: int = 0
    retrieval_top_k: int = 0
    max_history_messages: int = 0
    setup: str = ""


class CopilotEvidenceResponse(BaseModel):
    id: str
    kind: str
    title: str
    content: str = ""
    file_path: str = ""
    line_start: int = 0
    line_end: int = 0
    reason: str = ""
    score: float = 0.0


class CopilotChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8_000)
    conversation_id: Optional[str] = None

    @field_validator("message")
    @classmethod
    def message_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Message cannot be empty")
        return value


class CopilotMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    conversation_id: str
    role: str
    content: str
    intent: Optional[str] = None
    model: Optional[str] = None
    ai_enabled: bool = False
    evidence: list[CopilotEvidenceResponse] = []
    follow_ups: list[str] = []
    warnings: list[str] = []
    error: Optional[str] = None
    latency_ms: Optional[float] = None
    created_at: datetime

    @field_validator("evidence", "follow_ups", "warnings", mode="before")
    @classmethod
    def none_to_empty_list(cls, value: Any) -> Any:
        """Historical user messages have NULL JSON columns; expose empty lists."""
        return value if value is not None else []


class CopilotChatResponse(BaseModel):
    conversation_id: str
    message: CopilotMessageResponse
    ai_enabled: bool = False
    intent: str = "general"
    evidence: list[CopilotEvidenceResponse] = []
    follow_ups: list[str] = []
    warnings: list[str] = []
    model: Optional[str] = None
    latency_ms: float = 0.0


class CopilotConversationSummary(BaseModel):
    id: str
    repository_id: str
    title: str
    message_count: int = 0
    last_message_preview: str = ""
    created_at: datetime
    updated_at: datetime


class CopilotConversationList(BaseModel):
    conversations: list[CopilotConversationSummary] = []
    total: int = 0


class CopilotConversationDetail(BaseModel):
    conversation: CopilotConversationSummary
    messages: list[CopilotMessageResponse] = []


# ──────────────────────────── Health ────────────────────────────


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "ok"
    version: str
    app_name: str


CoverageCollectResponse.model_rebuild()
