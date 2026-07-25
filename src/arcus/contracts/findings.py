"""Finding and Fix models for code review analysis."""
from typing import Literal

from pydantic import BaseModel, Field

ConfidenceLevel = Literal["high", "medium", "low"]
SeverityLevel = Literal["high", "medium", "low"]
FindingType = Literal["logic_bug", "security", "inconsistency", "convention_violation"]


class Fix(BaseModel):
    """Suggested code fix for a finding."""

    description: str
    suggested_diff: str
    confidence: ConfidenceLevel


class Finding(BaseModel):
    """A single code review finding (bug, security issue, etc.)."""

    id: str
    agent: str
    type: FindingType
    severity: SeverityLevel
    file: str
    line_start: int
    line_end: int
    title: str
    rationale: str
    evidence_refs: list[str] = Field(default_factory=list)
    fix: Fix | None = None
