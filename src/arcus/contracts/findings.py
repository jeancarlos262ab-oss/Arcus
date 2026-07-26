"""Validated findings exchanged between analysis agents."""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FindingType(StrEnum):
    """Supported categories emitted by analysis agents."""

    LOGIC_BUG = "logic_bug"
    SECURITY = "security"
    INCONSISTENCY = "inconsistency"
    CONVENTION_VIOLATION = "convention_violation"


class Severity(StrEnum):
    """Finding impact used for report ordering and summary metrics."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class FixConfidence(StrEnum):
    """Confidence that a proposed fix addresses its finding safely."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class FindingAgent(StrEnum):
    """Agents allowed to originate findings."""

    CONSISTENCY_CHECKER = "consistency_checker"
    BUG_HUNTER = "bug_hunter"


class FixSuggestion(BaseModel):
    """A concrete, reviewable change proposed for an existing finding."""

    model_config = ConfigDict(extra="forbid")

    description: str = Field(min_length=1)
    suggested_diff: str = Field(min_length=1)
    confidence: FixConfidence


class FixAssignment(BaseModel):
    """A fix assigned to one finding already present in the envelope."""

    model_config = ConfigDict(extra="forbid")

    finding_id: UUID
    fix: FixSuggestion


class FixBatch(BaseModel):
    """Bounded set of fixes returned by one model invocation."""

    model_config = ConfigDict(extra="forbid")

    fixes: list[FixAssignment] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def validate_unique_finding_ids(self) -> FixBatch:
        """Prevent ambiguous duplicate assignments in generated output."""

        identifiers = [assignment.finding_id for assignment in self.fixes]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("fix assignments must use unique finding IDs")
        return self


class Finding(BaseModel):
    """A validated code-review issue tied to a source range."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    agent: FindingAgent
    type: FindingType
    severity: Severity
    file: str = Field(min_length=1)
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    title: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    evidence_refs: list[str] = Field(default_factory=list)
    fix: FixSuggestion | None = None

    @model_validator(mode="after")
    def validate_source_range(self) -> Finding:
        """Reject ranges that cannot identify a real source span."""

        if self.line_end < self.line_start:
            raise ValueError("line_end must be greater than or equal to line_start")
        return self
