"""Unit tests for GitHub webhook verification and parsing."""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
from typing import cast

import pytest

from arcus.github.webhook import (
    WebhookPayloadError,
    parse_pull_request_event,
    verify_signature,
)

FIXTURE_PATH = (
    Path(__file__).parents[2] / "fixtures" / "webhooks" / "pull_request_opened.json"
)


def _fixture_payload() -> dict[str, object]:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return cast(dict[str, object], payload)


def test_verify_signature_uses_the_raw_body() -> None:
    body = b'{"action":"opened"}'
    secret = "test-webhook-secret"
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    assert verify_signature(body, f"sha256={digest}", secret)
    assert not verify_signature(body + b" ", f"sha256={digest}", secret)


@pytest.mark.parametrize("signature", [None, "", "sha1=invalid", "sha256=invalid"])
def test_invalid_or_missing_signature_is_rejected(signature: str | None) -> None:
    assert not verify_signature(b"payload", signature, "secret")


def test_parse_pull_request_fixture() -> None:
    event = parse_pull_request_event("pull_request", _fixture_payload())

    assert event is not None
    assert event.action == "opened"
    assert event.repo_full_name == "acme/widgets"
    assert event.pr_number == 42
    assert event.commit_sha == "abc123def4567890"
    assert event.installation_id == 123456


def test_unsupported_event_or_action_is_ignored() -> None:
    payload = _fixture_payload()

    assert parse_pull_request_event("issues", payload) is None
    payload["action"] = "closed"
    assert parse_pull_request_event("pull_request", payload) is None


def test_relevant_malformed_event_is_rejected() -> None:
    payload = _fixture_payload()
    payload["pull_request"] = {}

    with pytest.raises(WebhookPayloadError, match="head must be an object"):
        parse_pull_request_event("pull_request", payload)
