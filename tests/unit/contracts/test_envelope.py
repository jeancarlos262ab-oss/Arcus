"""Contract tests for the cross-agent pipeline envelope."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from arcus.contracts import (
    AgentError,
    AgentFindingsSection,
    AgentStatus,
    PipelineEnvelope,
    PullRequestMetadata,
)

FIXTURE_DIR = Path(__file__).parents[2] / "fixtures" / "envelopes"


@pytest.mark.contract
@pytest.mark.parametrize("fixture_path", sorted(FIXTURE_DIR.glob("*.json")))
def test_every_stage_fixture_is_a_valid_pipeline_envelope(fixture_path: Path) -> None:
    """Every stage must preserve the complete shared envelope schema."""

    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    envelope = PipelineEnvelope.model_validate(payload)

    assert envelope.pr.repo_full_name == "acme/widgets"
    assert envelope.pr.pr_number == 42
    assert envelope.context.status in AgentStatus


@pytest.mark.contract
def test_envelope_has_safe_defaults_for_a_new_pipeline() -> None:
    """Webhook code can create an initial envelope without inventing stage dicts."""

    envelope = PipelineEnvelope(
        pipeline_run_id="123e4567-e89b-42d3-a456-426614174000",
        created_at="2026-07-21T10:00:00Z",
        pr=PullRequestMetadata(
            repo_full_name="acme/widgets",
            pr_number=42,
            commit_sha="abc123def4567890",
            installation_id=123456,
        ),
    )

    assert envelope.context.status is AgentStatus.PENDING
    assert envelope.consistency.findings == []
    assert envelope.report.comment_url is None


@pytest.mark.contract
def test_failed_stage_requires_structured_error() -> None:
    """A degraded stage must explain its failure to the reporter."""

    with pytest.raises(ValidationError, match="must include an error"):
        AgentFindingsSection(status=AgentStatus.FAILED)

    failed = AgentFindingsSection(
        status=AgentStatus.FAILED,
        error=AgentError(
            code="bedrock_invalid_response", message="Fixture response was malformed"
        ),
    )
    assert failed.error is not None
    assert failed.error.code == "bedrock_invalid_response"


@pytest.mark.contract
def test_non_failed_stage_cannot_carry_an_error() -> None:
    """Error data must not be silently attached to an apparently successful stage."""

    with pytest.raises(ValidationError, match="only failed stages"):
        AgentFindingsSection(
            status=AgentStatus.OK,
            error=AgentError(code="unexpected", message="The status is inconsistent"),
        )


@pytest.mark.contract
def test_envelope_round_trips_through_json_serialization() -> None:
    """The model dump must be accepted by the next Lambda's model validator."""

    payload = json.loads((FIXTURE_DIR / "reporter.json").read_text(encoding="utf-8"))
    envelope = PipelineEnvelope.model_validate(payload)
    round_tripped = PipelineEnvelope.model_validate(envelope.model_dump(mode="json"))

    assert round_tripped.pipeline_run_id == envelope.pipeline_run_id
    assert round_tripped.report.comment_url == envelope.report.comment_url
    assert len(round_tripped.fixes.findings) == 2
