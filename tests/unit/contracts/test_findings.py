"""Unit tests for finding and fix contracts."""

from __future__ import annotations

from uuid import UUID

import pytest
from pydantic import ValidationError

from arcus.contracts import Finding, FindingType, FixConfidence, Severity


@pytest.fixture
def finding_payload() -> dict[str, object]:
    """Return a representative finding payload for validation tests."""

    return {
        "id": "223e4567-e89b-42d3-a456-426614174001",
        "agent": "bug_hunter",
        "type": "logic_bug",
        "severity": "high",
        "file": "src/config.py",
        "line_start": 22,
        "line_end": 24,
        "title": "Retry backoff can exceed the configured maximum",
        "rationale": "The calculated delay is not capped for large attempts.",
        "evidence_refs": ["src/config.py:22", "src/review.py:11"],
        "fix": {
            "description": "Clamp the calculated delay.",
            "suggested_diff": "@@ -22 +22 @@\n- return 2**attempt\n+ return min(2**attempt, 30.0)",
            "confidence": "high",
        },
    }


@pytest.mark.contract
def test_finding_validates_and_serializes_to_step_functions_json(
    finding_payload: dict[str, object],
) -> None:
    """A valid finding should round-trip through JSON-compatible serialization."""

    finding = Finding.model_validate(finding_payload)

    assert finding.id == UUID("223e4567-e89b-42d3-a456-426614174001")
    assert finding.type is FindingType.LOGIC_BUG
    assert finding.severity is Severity.HIGH
    assert finding.fix is not None
    assert finding.fix.confidence is FixConfidence.HIGH

    serialized = finding.model_dump(mode="json")
    assert serialized["id"] == "223e4567-e89b-42d3-a456-426614174001"
    assert serialized["fix"]["confidence"] == "high"


@pytest.mark.contract
def test_finding_rejects_unknown_fields(finding_payload: dict[str, object]) -> None:
    """A typo in a shared field must fail at the contract boundary."""

    finding_payload["unexpected"] = "schema drift"

    with pytest.raises(ValidationError):
        Finding.model_validate(finding_payload)


@pytest.mark.contract
def test_finding_rejects_inverted_source_range(
    finding_payload: dict[str, object],
) -> None:
    """A finding cannot point to an end line before its start line."""

    finding_payload["line_start"] = 30
    finding_payload["line_end"] = 20

    with pytest.raises(ValidationError, match="line_end"):
        Finding.model_validate(finding_payload)
