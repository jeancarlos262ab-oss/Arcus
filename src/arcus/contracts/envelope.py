"""Pipeline envelope and related data structures for inter-agent communication."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from arcus.contracts.findings import Finding

StatusValue = Literal["ok", "failed", "skipped"]


class ErrorDetail(BaseModel):
    """Error information for failed stages."""

    code: str
    message: str


class PRDetails(BaseModel):
    """GitHub pull request details."""

    repo_full_name: str
    pr_number: int
    commit_sha: str
    installation_id: int
    changed_files: list[str] = Field(default_factory=list)
    diff_ref: str


class ContextConventions(BaseModel):
    """Code conventions detected or configured for the repository."""

    naming: str = "snake_case"
    error_handling: str = "custom exceptions"
    notes: list[str] = Field(default_factory=list)


class ContextSection(BaseModel):
    """Context section: code graph and conventions for the PR."""

    status: StatusValue
    graph_ref: str | None = None
    graph_version: str | None = None
    relevant_subgraph_ref: str | None = None
    conventions: ContextConventions = Field(default_factory=ContextConventions)
    error: ErrorDetail | None = None


class ConsistencySection(BaseModel):
    """Consistency checking results: convention violations, etc."""

    status: StatusValue
    findings: list[Finding] = Field(default_factory=list)
    error: ErrorDetail | None = None


class BugsSection(BaseModel):
    """Bug hunting results: logic bugs, security issues, etc."""

    status: StatusValue
    findings: list[Finding] = Field(default_factory=list)
    error: ErrorDetail | None = None


class FixesSection(BaseModel):
    """Fix suggestion results: remedies for findings."""

    status: StatusValue
    findings: list[Finding] = Field(default_factory=list)
    error: ErrorDetail | None = None


class ReportSection(BaseModel):
    """Report section: final comment and summary."""

    status: StatusValue
    comment_url: str | None = None
    summary: str | None = None
    error: ErrorDetail | None = None


class PipelineEnvelope(BaseModel):
    """
    The unified data structure passed through the entire pipeline.

    Each agent reads what it needs and appends its results to its section.
    No agent overwrites another's work.
    """

    pipeline_run_id: str
    created_at: datetime
    pr: PRDetails
    context: ContextSection
    consistency: ConsistencySection
    bugs: BugsSection
    fixes: FixesSection
    report: ReportSection
