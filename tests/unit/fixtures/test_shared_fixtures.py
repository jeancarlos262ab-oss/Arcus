"""Smoke tests ensuring shared fixtures remain available to every workstream."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).parents[2] / "fixtures"


@pytest.mark.contract
def test_webhook_fixture_contains_the_event_boundary_fields() -> None:
    """The webhook fixture carries the values needed to build an envelope."""

    payload = json.loads(
        (FIXTURE_DIR / "webhooks" / "pull_request_opened.json").read_text(
            encoding="utf-8"
        )
    )

    assert payload["action"] == "opened"
    assert payload["repository"]["full_name"] == "acme/widgets"
    assert payload["pull_request"]["head"]["sha"] == "abc123def4567890"
    assert payload["installation"]["id"] == 123456


@pytest.mark.contract
def test_pr_fixture_contains_diff_reference_and_changed_files() -> None:
    """The PR fixture keeps large diffs out of the envelope while retaining a pointer."""

    payload = json.loads(
        (FIXTURE_DIR / "prs" / "example_pr.json").read_text(encoding="utf-8")
    )
    diff = (FIXTURE_DIR / "prs" / "example.diff.patch").read_text(encoding="utf-8")

    assert payload["diff_ref"].startswith("s3://arcus-dev-context-artifacts/")
    assert payload["changed_files"] == ["src/config.py", "tests/test_config.py"]
    assert diff.startswith("diff --git")


@pytest.mark.contract
@pytest.mark.parametrize(
    "fixture_path", sorted((FIXTURE_DIR / "bedrock").glob("*.json"))
)
def test_bedrock_fixtures_have_converse_response_shape(fixture_path: Path) -> None:
    """Mocked Bedrock fixtures should be usable without a network call."""

    payload = json.loads(fixture_path.read_text(encoding="utf-8"))

    message = payload["output"]["message"]
    assert message["role"] == "assistant"
    assert isinstance(message["content"][0]["text"], str)
    assert payload["stopReason"] == "end_turn"
