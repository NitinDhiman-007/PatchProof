"""Pydantic schemas for request and response validation."""

import re
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class HealthResponse(BaseModel):
    """Basic health check response."""

    status: str = Field(default="ok", description="Application health status")
    version: str = Field(description="Application version")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Current UTC timestamp",
    )


class SystemStatusResponse(BaseModel):
    """Detailed system status response."""

    status: str = Field(default="operational", description="System operational state")
    version: str = Field(description="Application version")
    environment: str = Field(description="Running environment")
    database: str = Field(description="Database connectivity status ('connected' or 'disconnected')")
    bharatcode_configured: bool = Field(description="Whether BharatCode API credentials are configured")
    repositories_count: int = Field(default=0, description="Total registered repositories")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Current UTC timestamp",
    )


class GitUrlRegistrationRequest(BaseModel):
    """Request schema for registering a repository via Git URL."""

    git_url: str = Field(
        ...,
        min_length=8,
        max_length=512,
        description="Public HTTPS URL of the Git repository",
        examples=["https://github.com/psf/requests"],
    )
    default_branch: str | None = Field(
        default="main",
        min_length=1,
        max_length=100,
        description="Default branch name",
    )

    @field_validator("git_url")
    @classmethod
    def validate_url_syntax(cls, v: str) -> str:
        clean = v.strip()
        # Disallow command injection flags and unsafe shell metacharacters
        if any(c in clean for c in [";", "&", "|", "`", "$", "<", ">", "\n", "\r"]):
            raise ValueError("Git URL contains invalid or potentially dangerous characters.")

        if clean.startswith("-"):
            raise ValueError("Git URL cannot start with hyphen/flag indicators.")

        # Accept standard https/http Git host formats
        git_pattern = re.compile(
            r"^(https?:\/\/)[\w\.\-]+(\:[0-9]+)?\/[A-Za-z0-9_.\-]+\/[A-Za-z0-9_.\-]+(?:\.git)?\/?$"
        )
        if not git_pattern.match(clean):
            raise ValueError("Invalid Git URL format. Must be an HTTP(S) URL (e.g. https://github.com/owner/repo).")

        return clean


class RepositoryResponse(BaseModel):
    """Repository schema returned to client."""

    id: str
    name: str
    source_type: str = Field(description="'git' or 'zip'")
    git_url: str | None = None
    default_branch: str | None = None
    file_count: int = 0
    detected_language: str = "unknown"
    status: str = "active"
    created_at: str


class ZipMetadataRequest(BaseModel):
    """Metadata-only validation request for uploaded ZIP archive."""

    filename: str = Field(..., min_length=1, max_length=255)
    file_size_bytes: int = Field(..., gt=0)
    file_count: int = Field(default=0, ge=0)
    top_level_directories: list[str] = Field(default_factory=list)


class ZipValidationResponse(BaseModel):
    """Response returned after inspecting ZIP archive metadata."""

    is_valid: bool
    message: str
    repository: RepositoryResponse | None = None
    filename: str
    file_size_bytes: int
    total_files: int = 0
    top_level_directories: list[str] = Field(default_factory=list)
    detected_language: str = "unknown"
    errors: list[str] = Field(default_factory=list)


class BugAnalysisRequest(BaseModel):
    """Request schema to start bug analysis."""

    repository_id: str = Field(..., description="ID of the registered repository")
    bug_description: str = Field(
        ...,
        min_length=10,
        max_length=10000,
        description="Detailed description of the observed bug or error traceback",
    )
    issue_url: str | None = Field(
        default=None,
        max_length=512,
        description="Optional link to GitHub Issue or bug tracker",
    )
    stack_trace: str | None = Field(
        default=None,
        max_length=20000,
        description="Optional execution traceback or error log",
    )


class BugAnalysisResponse(BaseModel):
    """Response schema for a bug analysis record."""

    id: str
    repository_id: str
    bug_description: str
    issue_url: str | None = None
    stack_trace: str | None = None
    status: str = Field(description="'pending', 'analyzing', 'completed', 'failed'")
    summary: str | None = None
    root_cause_json: str | None = None
    reproduction_test_code: str | None = None
    reproduction_test_path: str | None = None
    baseline_reproduced: bool = False
    patch_diff: str | None = None
    patch_status: str = "none"
    verification_verdict: str = "PENDING"
    evidence_report_json: str | None = None
    created_at: str
    updated_at: str


class WorkflowEventResponse(BaseModel):
    """Audit trail event from LangGraph workflow execution."""

    id: str
    analysis_id: str
    step_name: str
    status: str
    message: str
    details_json: str | None = None
    created_at: str


class RootCauseResponse(BaseModel):
    """Structured root cause analysis grounded in repository source code."""

    analysis_id: str
    problem_summary: str
    suspected_root_cause: str
    affected_files: list[dict[str, Any]] = Field(default_factory=list)
    explanation: str
    confidence_score: float = 0.5
    confidence_explanation: str
    proposed_correction_strategy: str


class ReproductionTestResponse(BaseModel):
    """Generated regression test attempting to reproduce the bug."""

    analysis_id: str
    test_path: str
    test_code: str
    baseline_reproduced: bool
    baseline_summary: dict[str, Any] | None = None


class ProposedPatchResponse(BaseModel):
    """Proposed minimal unified diff patch and applicability audit."""

    analysis_id: str
    patch_diff: str
    patch_status: str
    summary: str | None = None
    rationale: str | None = None
    affected_files: list[str] = Field(default_factory=list)
    is_valid: bool = True
    validation_error: str | None = None


class PatchApprovalRequest(BaseModel):
    """Human approval or rejection request for a proposed patch."""

    status: str = Field(..., pattern="^(approved|rejected)$", description="'approved' or 'rejected'")
    comment: str | None = Field(default=None, max_length=1000)


class PatchApprovalResponse(BaseModel):
    """Result of human review on proposed patch."""

    analysis_id: str
    patch_status: str
    message: str
    updated_at: str


class ModelStatusResponse(BaseModel):
    """BharatCode model endpoint connectivity and authentication status."""

    configured: bool
    reachable: bool
    model: str
    base_url: str
    message: str
    response_sample: str | None = None


class ErrorResponse(BaseModel):
    """Standardized error response."""

    error: str
    detail: str
    timestamp: str


class VerificationRunRequest(BaseModel):
    """Request schema to trigger an isolated verification run."""

    repository_id: str = Field(..., description="ID of the registered repository to test")
    command: str = Field(
        default="pytest",
        description="Allowlisted command preset ('pytest', 'pytest_verbose', 'pytest_quiet')",
    )
    run_ruff: bool = Field(default=True, description="Whether to execute Ruff static analysis")


class VerificationRunResponse(BaseModel):
    """Response schema summarizing a verification run."""

    id: str
    repository_id: str
    repository_name: str | None = None
    command: str
    status: str = Field(description="'pending', 'running', 'passed', 'failed', 'timed_out', 'error'")
    exit_code: int | None = None
    duration_seconds: float = 0.0
    tests_passed: int = 0
    tests_failed: int = 0
    tests_skipped: int = 0
    tests_errors: int = 0
    ruff_passed: bool = True
    error_message: str | None = None
    created_at: str
    completed_at: str | None = None


class VerificationLogsResponse(BaseModel):
    """Execution stdout and stderr streams for a verification run."""

    run_id: str
    status: str
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    error_message: str | None = None


class VerificationReportResponse(BaseModel):
    """Full evidence report with cryptographic SHA-256 integrity hash from isolated sandbox execution."""

    run_id: str
    repository_id: str
    repository_name: str
    status: str = Field(description="'passed', 'failed', 'timed_out', 'error'")
    execution_environment: str
    command: str
    exit_code: int | None = None
    duration_seconds: float = 0.0
    tests_passed: int = 0
    tests_failed: int = 0
    tests_skipped: int = 0
    tests_errors: int = 0
    ruff_passed: bool = True
    ruff_issues: list[str] = Field(default_factory=list)
    ruff_exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    infrastructure_error: str | None = None
    verification_summary: str
    integrity_hash: str | None = None
    created_at: str
    completed_at: str | None = None
