"""Unit tests for bounded webhook admission."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock
from uuid import UUID

import pytest
from botocore.exceptions import ClientError

from arcus.contracts import PipelineEnvelope
from arcus.entrypoints.webhook_handler import WebhookHandler, WebhookSettings
from arcus.github.webhook import PullRequestEvent
from arcus.storage.admission import (
    ALL_INSTALLATIONS,
    ALL_REPOSITORIES,
    AdmissionPolicy,
    AdmissionResult,
    AdmissionStatus,
    ExecutionClaim,
)

FIXTURE_PATH = (
    Path(__file__).parents[2] / "fixtures" / "webhooks" / "pull_request_opened.json"
)
WEBHOOK_SECRET = "test-webhook-secret"
RUN_ID = UUID("123e4567-e89b-42d3-a456-426614174000")
CREATED_AT = datetime(2026, 7, 24, 12, 0, tzinfo=UTC)


def _api_event(
    *,
    payload: dict[str, object] | None = None,
    action: str | None = None,
    github_event: str = "pull_request",
    delivery_id: str = "11111111-2222-3333-4444-555555555555",
    base64_encoded: bool = False,
) -> dict[str, object]:
    event_payload = payload if payload is not None else _load_fixture()
    if action is not None:
        event_payload["action"] = action
    body = json.dumps(event_payload, separators=(",", ":"))
    body_bytes = body.encode()
    signature = hmac.new(
        WEBHOOK_SECRET.encode(), body_bytes, hashlib.sha256
    ).hexdigest()
    return {
        "headers": {
            "X-GitHub-Event": github_event,
            "X-GitHub-Delivery": delivery_id,
            "X-Hub-Signature-256": f"sha256={signature}",
        },
        "body": base64.b64encode(body_bytes).decode() if base64_encoded else body,
        "isBase64Encoded": base64_encoded,
    }


def _load_fixture() -> dict[str, object]:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _settings() -> WebhookSettings:
    return WebhookSettings(
        review_table_name="arcus-dev-review-history",
        state_machine_arn=(
            "arn:aws:states:us-east-1:123456789012:stateMachine:arcus-dev-pr-pipeline"
        ),
        webhook_secret_arn=(
            "arn:aws:secretsmanager:us-east-1:123456789012:secret:arcus-webhook"
        ),
    )


def test_environment_accepts_all_repositories_wildcard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DDB_REVIEW_TABLE", "arcus-dev-review-history")
    monkeypatch.setenv("STATE_MACHINE_ARN", "test-state-machine-arn")
    monkeypatch.setenv("WEBHOOK_SECRET_ARN", "test-webhook-secret-arn")
    monkeypatch.setenv("ALLOWED_REPOSITORIES", ALL_REPOSITORIES)
    monkeypatch.setenv("ALLOWED_INSTALLATION_IDS", "123456")

    settings = WebhookSettings.from_environment()

    assert settings.allowed_repositories == frozenset({ALL_REPOSITORIES})


def test_environment_rejects_wildcard_mixed_with_explicit_repository(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DDB_REVIEW_TABLE", "arcus-dev-review-history")
    monkeypatch.setenv("STATE_MACHINE_ARN", "test-state-machine-arn")
    monkeypatch.setenv("WEBHOOK_SECRET_ARN", "test-webhook-secret-arn")
    monkeypatch.setenv("ALLOWED_REPOSITORIES", "*,acme/widgets")
    monkeypatch.setenv("ALLOWED_INSTALLATION_IDS", "123456")

    with pytest.raises(ValueError, match="wildcard.*used alone"):
        WebhookSettings.from_environment()


def test_environment_accepts_all_installations_wildcard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DDB_REVIEW_TABLE", "arcus-dev-review-history")
    monkeypatch.setenv("STATE_MACHINE_ARN", "test-state-machine-arn")
    monkeypatch.setenv("WEBHOOK_SECRET_ARN", "test-webhook-secret-arn")
    monkeypatch.setenv("ALLOWED_REPOSITORIES", "acme/widgets")
    monkeypatch.setenv("ALLOWED_INSTALLATION_IDS", ALL_INSTALLATIONS)

    settings = WebhookSettings.from_environment()

    assert settings.allowed_installation_ids == frozenset({ALL_INSTALLATIONS})


def test_environment_rejects_wildcard_mixed_with_explicit_installation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DDB_REVIEW_TABLE", "arcus-dev-review-history")
    monkeypatch.setenv("STATE_MACHINE_ARN", "test-state-machine-arn")
    monkeypatch.setenv("WEBHOOK_SECRET_ARN", "test-webhook-secret-arn")
    monkeypatch.setenv("ALLOWED_REPOSITORIES", "acme/widgets")
    monkeypatch.setenv("ALLOWED_INSTALLATION_IDS", "*,123456")

    with pytest.raises(ValueError, match="wildcard.*used alone"):
        WebhookSettings.from_environment()


def test_all_installations_still_requires_an_approved_repository() -> None:
    policy = AdmissionPolicy(
        allowed_repositories=frozenset({"acme/widgets"}),
        allowed_installation_ids=frozenset({ALL_INSTALLATIONS}),
        reviews_per_repository_day=10,
        reviews_per_installation_hour=5,
        item_ttl_seconds=3600,
    )
    event = PullRequestEvent(
        action="opened",
        repo_full_name="acme/widgets",
        pr_number=7,
        commit_sha="abc123",
        installation_id=999999,
    )

    assert policy.allows(event)
    assert not policy.allows(replace(event, repo_full_name="other/repository"))


def test_all_repositories_still_requires_an_approved_installation() -> None:
    policy = AdmissionPolicy(
        allowed_repositories=frozenset({ALL_REPOSITORIES}),
        allowed_installation_ids=frozenset({123456}),
        reviews_per_repository_day=10,
        reviews_per_installation_hour=5,
        item_ttl_seconds=3600,
    )
    event = PullRequestEvent(
        action="opened",
        repo_full_name="another-owner/another-repository",
        pr_number=7,
        commit_sha="abc123",
        installation_id=123456,
    )

    assert policy.allows(event)
    assert not policy.allows(replace(event, installation_id=999999))


def _handler(
    *,
    settings: WebhookSettings | None = None,
    admission_store: Mock | None = None,
    step_functions: Mock | None = None,
    run_id_factory: Callable[[], UUID] | None = None,
) -> tuple[WebhookHandler, Mock, Mock, Mock]:
    resolved_store = admission_store or Mock()
    if admission_store is None:
        resolved_store.policy = AdmissionPolicy(
            allowed_repositories=frozenset({"acme/widgets"}),
            allowed_installation_ids=frozenset({123456}),
            reviews_per_repository_day=10,
            reviews_per_installation_hour=5,
            item_ttl_seconds=3600,
        )
        resolved_store.claim.side_effect = lambda _event, _delivery, candidate: (
            AdmissionResult(AdmissionStatus.ACCEPTED, candidate)
        )
    resolved_step_functions = step_functions or Mock()
    secrets = Mock()
    secrets.get_secret_value.return_value = {"SecretString": WEBHOOK_SECRET}
    handler = WebhookHandler(
        settings=settings or _settings(),
        admission_store=resolved_store,
        secrets_client=secrets,
        step_functions_client=resolved_step_functions,
        now=lambda: CREATED_AT,
        run_id_factory=run_id_factory or (lambda: RUN_ID),
    )
    return handler, resolved_store, resolved_step_functions, secrets


def _client_error(code: str, operation: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": code}}, operation)


def _response_body(response: dict[str, object]) -> dict[str, object]:
    raw_body = response["body"]
    assert isinstance(raw_body, str)
    body = json.loads(raw_body)
    assert isinstance(body, dict)
    return body


@pytest.mark.parametrize("action", ["opened", "synchronize"])
def test_supported_action_claims_atomically_and_starts_pipeline(action: str) -> None:
    handler, store, step_functions, _ = _handler()

    response = handler.handle(_api_event(action=action))

    assert response["statusCode"] == 202
    assert _response_body(response)["pipeline_run_id"] == str(RUN_ID)
    store.claim.assert_called_once()
    _, delivery_id, claim = store.claim.call_args.args
    assert delivery_id == "11111111-2222-3333-4444-555555555555"
    assert isinstance(claim, ExecutionClaim)
    assert claim.created_at == CREATED_AT

    step_functions.start_execution.assert_called_once()
    start = step_functions.start_execution.call_args.kwargs
    assert start["name"] == str(RUN_ID)
    assert start["input"] == claim.execution_input
    envelope = PipelineEnvelope.model_validate_json(start["input"])
    assert envelope.pr.repo_full_name == "acme/widgets"
    assert envelope.pr.diff_ref is None
    assert envelope.context.status.value == "pending"
    assert envelope.report.status.value == "pending"


@pytest.mark.parametrize(
    "event",
    [
        {"headers": {"X-GitHub-Event": "pull_request"}},
        {"headers": {"X-GitHub-Event": "pull_request"}, "body": None},
        {
            "headers": {"X-GitHub-Event": "pull_request"},
            "body": "not-base64!",
            "isBase64Encoded": True,
        },
    ],
)
def test_missing_signature_returns_before_other_validation(
    event: dict[str, object],
) -> None:
    handler, store, step_functions, secrets = _handler()

    response = handler.handle(event)

    assert response["statusCode"] == 401
    store.claim.assert_not_called()
    step_functions.start_execution.assert_not_called()
    secrets.get_secret_value.assert_not_called()


def test_invalid_signature_has_no_paid_side_effects() -> None:
    handler, store, step_functions, _ = _handler()
    event = _api_event()
    event["headers"] = {
        "X-GitHub-Event": "pull_request",
        "X-GitHub-Delivery": "delivery-1",
        "X-Hub-Signature-256": "sha256=invalid",
    }

    response = handler.handle(event)

    assert response["statusCode"] == 401
    store.claim.assert_not_called()
    step_functions.start_execution.assert_not_called()


@pytest.mark.parametrize(
    ("github_event", "action"),
    [("pull_request", "closed"), ("pull_request", "labeled"), ("push", None)],
)
def test_irrelevant_event_is_accepted_without_admission(
    github_event: str, action: str | None
) -> None:
    handler, store, step_functions, _ = _handler()

    response = handler.handle(_api_event(github_event=github_event, action=action))

    assert response["statusCode"] == 202
    assert _response_body(response)["message"] == "event ignored"
    store.claim.assert_not_called()
    step_functions.start_execution.assert_not_called()


def test_relevant_event_requires_a_valid_delivery_id() -> None:
    handler, store, step_functions, _ = _handler()

    response = handler.handle(_api_event(delivery_id="bad delivery id"))

    assert response["statusCode"] == 400
    store.claim.assert_not_called()
    step_functions.start_execution.assert_not_called()


def test_allowlist_denial_is_acknowledged_without_consuming_quota() -> None:
    handler, store, step_functions, _ = _handler()
    store.policy = AdmissionPolicy(
        allowed_repositories=frozenset({"other/repository"}),
        allowed_installation_ids=frozenset({999}),
        reviews_per_repository_day=1,
        reviews_per_installation_hour=1,
        item_ttl_seconds=60,
    )

    response = handler.handle(_api_event())

    assert response["statusCode"] == 202
    assert "admission policy" in _response_body(response)["message"]
    store.claim.assert_not_called()
    step_functions.start_execution.assert_not_called()


def test_quota_exhaustion_returns_accepted_without_starting_pipeline() -> None:
    store = Mock()
    store.policy = _handler()[1].policy
    store.claim.return_value = AdmissionResult(AdmissionStatus.QUOTA_EXCEEDED)
    handler, _, step_functions, _ = _handler(admission_store=store)

    response = handler.handle(_api_event())

    assert response["statusCode"] == 202
    assert _response_body(response)["message"] == "review quota reached"
    step_functions.start_execution.assert_not_called()


def test_base64_body_is_verified_and_admitted() -> None:
    handler, store, step_functions, _ = _handler()

    response = handler.handle(_api_event(base64_encoded=True))

    assert response["statusCode"] == 202
    store.claim.assert_called_once()
    step_functions.start_execution.assert_called_once()


def test_oversized_body_is_rejected_before_secret_lookup() -> None:
    settings = replace(_settings(), max_body_bytes=10)
    handler, store, step_functions, secrets = _handler(settings=settings)

    response = handler.handle(_api_event())

    assert response["statusCode"] == 413
    secrets.get_secret_value.assert_not_called()
    store.claim.assert_not_called()
    step_functions.start_execution.assert_not_called()


def test_warm_handler_caches_webhook_secret() -> None:
    handler, _, _, secrets = _handler()

    first = handler.handle(_api_event(delivery_id="delivery-1"))
    second = handler.handle(_api_event(delivery_id="delivery-2"))

    assert first["statusCode"] == 202
    assert second["statusCode"] == 202
    secrets.get_secret_value.assert_called_once()


def test_duplicate_claim_reuses_original_execution_identity() -> None:
    original_claim: ExecutionClaim | None = None
    store = Mock()
    store.policy = _handler()[1].policy

    def claim_side_effect(
        _event: object, _delivery: str, candidate: ExecutionClaim
    ) -> AdmissionResult:
        nonlocal original_claim
        if original_claim is None:
            original_claim = candidate
            return AdmissionResult(AdmissionStatus.ACCEPTED, candidate)
        return AdmissionResult(AdmissionStatus.DUPLICATE, original_claim)

    store.claim.side_effect = claim_side_effect
    step_functions = Mock()
    step_functions.start_execution.side_effect = [
        _client_error("ServiceUnavailable", "StartExecution"),
        {"executionArn": "arn:execution"},
    ]
    run_ids = iter((RUN_ID, UUID("987fcdeb-51a2-43d7-8abc-1234567890ab")))
    handler, _, _, _ = _handler(
        admission_store=store,
        step_functions=step_functions,
        run_id_factory=lambda: next(run_ids),
    )

    first = handler.handle(_api_event(delivery_id="delivery-1"))
    second = handler.handle(_api_event(delivery_id="delivery-1"))

    assert first["statusCode"] == 500
    assert second["statusCode"] == 202
    assert _response_body(second)["pipeline_run_id"] == str(RUN_ID)
    assert step_functions.start_execution.call_args_list[0].kwargs == (
        step_functions.start_execution.call_args_list[1].kwargs
    )


def test_execution_already_exists_is_an_idempotent_success() -> None:
    step_functions = Mock()
    step_functions.start_execution.side_effect = _client_error(
        "ExecutionAlreadyExists", "StartExecution"
    )
    handler, _, _, _ = _handler(step_functions=step_functions)

    response = handler.handle(_api_event())

    assert response["statusCode"] == 202
    assert _response_body(response) == {
        "message": "duplicate event ignored",
        "pipeline_run_id": str(RUN_ID),
    }
