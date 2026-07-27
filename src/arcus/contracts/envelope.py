"""Authoritative contract passed between every pipeline stage."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from arcus.contracts.findings import Finding


class AgentStatus(StrEnum):
    """Lifecycle state shared by every pipeline section."""

    PENDING = "pending"
    OK = "ok"
    FAILED = "failed"
    SKIPPED = "skipped"


class AgentError(BaseModel):
    """Structured error retained when a stage degrades gracefully."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)


class PullRequestMetadata(BaseModel):
    """Bounded pull-request metadata carried between Lambda functions."""

    model_config = ConfigDict(extra="forbid")

    repo_full_name: str = Field(min_length=3, pattern=r"^[^/]+/[^/]+$")
    pr_number: int = Field(gt=0)
    pr_title: str = ""
    author: str = ""
    commit_sha: str = Field(min_length=7)
    base_commit_sha: str = Field(min_length=7)
    installation_id: int = Field(gt=0)
    changed_files: list[str] = Field(default_factory=list)
    diff_ref: str | None = None


class ContextConventions(BaseModel):
    """Repository conventions supplied as bounded model context."""

    model_config = ConfigDict(extra="forbid")

    naming: str = "snake_case"
    error_handling: str = "custom_exceptions"
    test_framework: str = "pytest"
    notes: list[str] = Field(default_factory=list)


class StageSection(BaseModel):
    """Common lifecycle and error invariants for a pipeline stage."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    status: AgentStatus = AgentStatus.PENDING
    error: AgentError | None = None

    @model_validator(mode="after")
    def validate_error_state(self) -> StageSection:
        """Keep status and error data consistent at every boundary."""

        if self.status is AgentStatus.FAILED and self.error is None:
            raise ValueError("failed stages must include an error")
        if self.status is not AgentStatus.FAILED and self.error is not None:
            raise ValueError("only failed stages may include an error")
        return self


class ContextSection(StageSection):
    """Persisted repository graph and conventions used during analysis."""

    graph_ref: str | None = None
    graph_version: str | None = None
    relevant_subgraph_ref: str | None = None
    conventions: ContextConventions | None = None
    ran_diff_only: bool = False


class AgentFindingsSection(StageSection):
    """Findings emitted or enriched by one analysis stage."""

    findings: list[Finding] = Field(default_factory=list)


class ReportSection(StageSection):
    """Final GitHub comment and compact review summary."""

    comment_url: str | None = None
    summary: str | None = None


class PipelineEnvelope(BaseModel):
    """The complete, validated object passed through Step Functions."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    pipeline_run_id: UUID
    created_at: datetime
    pr: PullRequestMetadata
    context: ContextSection = Field(default_factory=ContextSection)
    consistency: AgentFindingsSection = Field(default_factory=AgentFindingsSection)
    bugs: AgentFindingsSection = Field(default_factory=AgentFindingsSection)
    fixes: AgentFindingsSection = Field(default_factory=AgentFindingsSection)
    report: ReportSection = Field(default_factory=ReportSection)
