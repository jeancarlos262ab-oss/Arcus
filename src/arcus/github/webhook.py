"""Verification and parsing helpers for GitHub pull-request webhooks."""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast


class WebhookPayloadError(ValueError):
    """Raised when a signed webhook cannot be converted to a PR event."""


@dataclass(frozen=True, slots=True)
class PullRequestEvent:
    """Validated fields needed to start an Arcus pipeline execution."""

    action: str
    repo_full_name: str
    pr_number: int
    commit_sha: str
    base_commit_sha: str
    installation_id: int


def verify_signature(
    body: bytes,
    signature_header: str | None,
    secret: str,
) -> bool:
    """Verify GitHub's HMAC-SHA256 signature against the raw request body."""

    if not signature_header or not secret:
        return False

    algorithm, separator, signature = signature_header.strip().partition("=")
    if algorithm != "sha256" or separator != "=" or not signature:
        return False

    expected_signature = hmac.new(
        secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(signature, expected_signature)


def parse_pull_request_event(
    event_name: str | None,
    payload: Mapping[str, object],
) -> PullRequestEvent | None:
    """Parse a relevant GitHub event, returning ``None`` for ignored events.

    Signature verification happens before this function is called. An unsupported
    event type or action is intentionally treated as an ignored delivery, while a
    malformed relevant event raises ``WebhookPayloadError``.
    """

    if event_name is None or event_name.lower() != "pull_request":
        return None

    action = _required_string(payload, "action")
    if action not in {"opened", "synchronize"}:
        return None

    pull_request = _required_mapping(payload, "pull_request")
    repository = _required_mapping(payload, "repository")
    head = _required_mapping(pull_request, "head")
    base = _required_mapping(pull_request, "base")
    installation = _required_mapping(payload, "installation")

    repo_full_name = _required_string(repository, "full_name")
    if repo_full_name.count("/") != 1 or any(
        character.isspace() for character in repo_full_name
    ):
        raise WebhookPayloadError("repository.full_name must be owner/repository")

    pr_number = _required_positive_integer(pull_request, "number")
    commit_sha = _required_string(head, "sha")
    base_commit_sha = _required_string(base, "sha")
    installation_id = _required_positive_integer(installation, "id")

    return PullRequestEvent(
        action=action,
        repo_full_name=repo_full_name,
        pr_number=pr_number,
        commit_sha=commit_sha,
        base_commit_sha=base_commit_sha,
        installation_id=installation_id,
    )


def _required_mapping(
    container: Mapping[str, object], field_name: str
) -> Mapping[str, object]:
    """Read a nested JSON object from an untrusted payload."""

    value = container.get(field_name)
    if not isinstance(value, Mapping):
        raise WebhookPayloadError(f"{field_name} must be an object")
    return cast(Mapping[str, object], value)


def _required_string(container: Mapping[str, object], field_name: str) -> str:
    """Read a non-empty string from an untrusted payload."""

    value = container.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise WebhookPayloadError(f"{field_name} must be a non-empty string")
    return value.strip()


def _required_positive_integer(container: Mapping[str, object], field_name: str) -> int:
    """Read a positive JSON integer without accepting booleans."""

    value = container.get(field_name)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise WebhookPayloadError(f"{field_name} must be a positive integer")
    return value
