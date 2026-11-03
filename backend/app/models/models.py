"""
SQLAlchemy models for IMPACTMAP.
Represents repositories, analyses, code entities, and their relationships.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    DateTime,
    Text,
    ForeignKey,
    JSON,
    Enum as SAEnum,
)
from sqlalchemy.orm import relationship
import enum

from app.core.database import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class RepoStatus(str, enum.Enum):
    PENDING = "pending"
    SCANNING = "scanning"
    SCANNED = "scanned"
    ERROR = "error"


class AnalysisStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"


class EntityType(str, enum.Enum):
    FILE = "file"
    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"


class Repository(Base):
    """Represents a scanned code repository."""

    __tablename__ = "repositories"

    id = Column(String, primary_key=True, default=generate_uuid)
    path = Column(String, nullable=False, unique=True)
    name = Column(String, nullable=False)
    status = Column(SAEnum(RepoStatus), default=RepoStatus.PENDING, nullable=False)

    total_files = Column(Integer, default=0)
    total_functions = Column(Integer, default=0)
    total_classes = Column(Integer, default=0)
    total_dependencies = Column(Integer, default=0)

    last_scanned_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    scan_error = Column(Text, nullable=True)
    metadata_ = Column("metadata", JSON, nullable=True)

    # Relationships
    entities = relationship("CodeEntity", back_populates="repository", cascade="all, delete-orphan")
    analyses = relationship("Analysis", back_populates="repository", cascade="all, delete-orphan")


class CodeEntity(Base):
    """Represents a discovered code entity (file, function, class, method)."""

    __tablename__ = "code_entities"

    id = Column(String, primary_key=True, default=generate_uuid)
    repository_id = Column(String, ForeignKey("repositories.id"), nullable=False)

    name = Column(String, nullable=False)
    qualified_name = Column(String, nullable=False)  # e.g., "module.submodule.ClassName.method"
    entity_type = Column(SAEnum(EntityType), nullable=False)
    file_path = Column(String, nullable=False)  # Relative to repo root
    line_start = Column(Integer, nullable=True)
    line_end = Column(Integer, nullable=True)

    # For classes and methods
    parent_entity_id = Column(String, ForeignKey("code_entities.id"), nullable=True)

    # Metadata
    docstring = Column(Text, nullable=True)
    decorators = Column(JSON, nullable=True)  # List of decorator names
    imports = Column(JSON, nullable=True)  # List of import strings

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    repository = relationship("Repository", back_populates="entities")
    parent = relationship("CodeEntity", remote_side=[id], backref="children")


class Analysis(Base):
    """Represents an impact analysis run."""

    __tablename__ = "analyses"

    id = Column(String, primary_key=True, default=generate_uuid)
    repository_id = Column(String, ForeignKey("repositories.id"), nullable=False)

    status = Column(SAEnum(AnalysisStatus), default=AnalysisStatus.PENDING, nullable=False)
    base_ref = Column(String, nullable=True)  # Git ref to compare against
    head_ref = Column(String, nullable=True)  # Current state ref

    # Results
    changed_files = Column(JSON, nullable=True)
    changed_entities = Column(JSON, nullable=True)
    impact_results = Column(JSON, nullable=True)
    test_recommendations = Column(JSON, nullable=True)

    # Stats
    total_changed_files = Column(Integer, default=0)
    total_affected_entities = Column(Integer, default=0)
    analysis_duration_ms = Column(Float, nullable=True)

    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    repository = relationship("Repository", back_populates="analyses")


class CoverageSnapshot(Base):
    """A test-to-code coverage mapping collected with Coverage.py contexts."""

    __tablename__ = "coverage_snapshots"

    id = Column(String, primary_key=True, default=generate_uuid)
    repository_id = Column(String, ForeignKey("repositories.id"), nullable=False)

    status = Column(String, default="completed", nullable=False)  # completed | partial | error
    collected_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    duration_ms = Column(Float, nullable=True)

    total_tests = Column(Integer, default=0)
    measured_tests = Column(Integer, default=0)
    covered_files = Column(Integer, default=0)
    data = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    warnings = Column(JSON, nullable=True)


class TestRun(Base):
    """A measured execution of the full, safe, or optimized test suite."""

    __tablename__ = "test_runs"

    id = Column(String, primary_key=True, default=generate_uuid)
    repository_id = Column(String, ForeignKey("repositories.id"), nullable=False)
    analysis_id = Column(String, ForeignKey("analyses.id"), nullable=True)

    mode = Column(String, nullable=False)  # full | safe | optimized | custom
    status = Column(String, nullable=False)  # completed | timeout | error
    exit_code = Column(Integer, nullable=True)

    test_ids = Column(JSON, nullable=True)
    total_tests = Column(Integer, default=0)
    passed = Column(Integer, default=0)
    failed = Column(Integer, default=0)
    errors = Column(Integer, default=0)
    skipped = Column(Integer, default=0)

    duration_ms = Column(Float, nullable=True)
    timed_out = Column(Integer, default=0)
    results = Column(JSON, nullable=True)
    stdout_tail = Column(Text, nullable=True)
    stderr_tail = Column(Text, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class CopilotConversation(Base):
    """A repository-scoped Copilot chat thread."""

    __tablename__ = "copilot_conversations"

    id = Column(String, primary_key=True, default=generate_uuid)
    repository_id = Column(String, ForeignKey("repositories.id"), nullable=False)
    title = Column(String, nullable=False, default="New conversation")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    messages = relationship(
        "CopilotMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="CopilotMessage.created_at",
    )


class CopilotMessage(Base):
    """One user or assistant message, including its evidence trail."""

    __tablename__ = "copilot_messages"

    id = Column(String, primary_key=True, default=generate_uuid)
    conversation_id = Column(
        String, ForeignKey("copilot_conversations.id"), nullable=False
    )
    role = Column(String, nullable=False)  # user | assistant
    content = Column(Text, nullable=False, default="")
    intent = Column(String, nullable=True)
    model = Column(String, nullable=True)
    ai_enabled = Column(Integer, default=0)
    evidence = Column(JSON, nullable=False, default=list)
    follow_ups = Column(JSON, nullable=False, default=list)
    warnings = Column(JSON, nullable=False, default=list)
    error = Column(Text, nullable=True)
    latency_ms = Column(Float, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    conversation = relationship("CopilotConversation", back_populates="messages")


class BenchmarkRun(Base):
    """A measured comparison of the full suite against a selected suite."""

    __tablename__ = "benchmarks"

    id = Column(String, primary_key=True, default=generate_uuid)
    repository_id = Column(String, ForeignKey("repositories.id"), nullable=False)
    analysis_id = Column(String, ForeignKey("analyses.id"), nullable=True)

    dataset_name = Column(String, nullable=True)
    mode = Column(String, nullable=False)  # safe | optimized
    base_ref = Column(String, nullable=True)
    head_ref = Column(String, nullable=True)

    total_tests = Column(Integer, default=0)
    selected_tests = Column(Integer, default=0)

    full_duration_ms = Column(Float, nullable=True)
    selected_duration_ms = Column(Float, nullable=True)
    analysis_duration_ms = Column(Float, nullable=True)

    reduction_percent = Column(Float, nullable=True)
    selection_precision = Column(Float, nullable=True)
    selection_recall = Column(Float, nullable=True)

    metrics = Column(JSON, nullable=True)
    notes = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
