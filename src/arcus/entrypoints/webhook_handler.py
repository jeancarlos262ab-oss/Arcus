"""Lambda entrypoint that admits bounded, signed GitHub PR events."""

from __future__ import annotations

import base64
import json
import logging
import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any, Protocol, cast
from uuid import UUID, uuid4

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from arcus.contracts import PipelineEnvelope, PullRequestMetadata
from arcus.github.webhook import (
    PullRequestEvent,
    WebhookPayloadError,
    parse_pull_request_event,
    verify_signature,
)
from arcus.secrets import CachedSecretProvider, SecretsManagerClient
from arcus.storage.admission import (
    ALL_INSTALLATIONS,
    ALL_REPOSITORIES,
    AdmissionPolicy,
    AdmissionResult,
    AdmissionStatus,
    DynamoAdmissionStore,
    DynamoDBClient,
    ExecutionClaim,
    InstallationAllowlistEntry,
)

logger = logging.getLogger(__name__)
_DELIVERY_ID_PATTERN = re.compile(r"^[A-Za-z0-9-]{1,128}$")
_DEFAULT_ALLOWED_REPOSITORY = ALL_REPOSITORIES
_DEFAULT_ALLOWED_INSTALLATION = ALL_INSTALLATIONS


class AdmissionStore(Protocol):
    """Admission boundary used by the webhook handler."""

    @property
    def policy(self) -> AdmissionPolicy:
        """Return the active fail-closed admission policy."""
        ...

    def claim(
        self,
        event: PullRequestEvent,
        delivery_id: str,
        candidate: ExecutionClaim,
    ) -> AdmissionResult:
        """Atomically deduplicate and consume bounded quotas."""
        ...


class StepFunctionsClient(Protocol):
    """Minimal Step Functions interface used by the webhook handler."""

    def start_execution(
        self,
        *,
        stateMachineArn: str,
        name: str,
        input: str,
    ) -> Mapping[str, object]:
        """Start one Standard workflow execution."""
        ...


class WebhookBodyTooLargeError(WebhookPayloadError):
    """Raised before secret or persistence I/O for an oversized delivery."""


@dataclass(frozen=True, slots=True)
class WebhookSettings:
    """Validated runtime controls required to admit a webhook delivery."""

    review_table_name: str
    state_machine_arn: str
    webhook_secret_arn: str
    allowed_repositories: frozenset[str] = field(
        default_factory=lambda: frozenset({_DEFAULT_ALLOWED_REPOSITORY})
    )
    allowed_installation_ids: frozenset[InstallationAllowlistEntry] = field(
        default_factory=lambda: frozenset({_DEFAULT_ALLOWED_INSTALLATION})
    )
    reviews_per_repository_day: int = 10
    reviews_per_installation_hour: int = 5
    admission_ttl_seconds: int = 90 * 24 * 60 * 60
    max_body_bytes: int = 1_048_576
    secret_cache_ttl_seconds: int = 300

    def __post_init__(self) -> None:
        """Validate all hard limits at cold start."""

        AdmissionPolicy(
            allowed_repositories=self.allowed_repositories,
            allowed_installation_ids=self.allowed_installation_ids,
            reviews_per_repository_day=self.reviews_per_repository_day,
            reviews_per_installation_hour=self.reviews_per_installation_hour,
            item_ttl_seconds=self.admission_ttl_seconds,
        )
        if self.max_body_bytes < 1:
            raise ValueError("MAX_WEBHOOK_BODY_BYTES must be at least 1")
        if self.secret_cache_ttl_seconds < 1:
            raise ValueError("SECRET_CACHE_TTL_SECONDS must be at least 1")

    @property
    def admission_policy(self) -> AdmissionPolicy:
        """Build the immutable policy consumed by the DynamoDB adapter."""

        return AdmissionPolicy(
            allowed_repositories=self.allowed_repositories,
            allowed_installation_ids=self.allowed_installation_ids,
            reviews_per_repository_day=self.reviews_per_repository_day,
            reviews_per_installation_hour=self.reviews_per_installation_hour,
            item_ttl_seconds=self.admission_ttl_seconds,
        )

    @classmethod
    def from_environment(cls) -> WebhookSettings:
        """Load identifiers, allowlists, and quotas without reading secrets."""

        return cls(
            review_table_name=_required_environment("DDB_REVIEW_TABLE"),
            state_machine_arn=_required_environment("STATE_MACHINE_ARN"),
            webhook_secret_arn=_first_required_environment(
                "GITHUB_SECRET_ARN", "WEBHOOK_SECRET_ARN"
            ),
            allowed_repositories=_repository_allowlist(
                os.getenv("ALLOWED_REPOSITORIES", _DEFAULT_ALLOWED_REPOSITORY)
            ),
            allowed_installation_ids=_installation_allowlist(
                os.getenv("ALLOWED_INSTALLATION_IDS", _DEFAULT_ALLOWED_INSTALLATION)
            ),
            reviews_per_repository_day=_positive_environment_int(
                "REVIEWS_PER_REPOSITORY_DAY", 10
            ),
            reviews_per_installation_hour=_positive_environment_int(
                "REVIEWS_PER_INSTALLATION_HOUR", 5
            ),
            admission_ttl_seconds=_positive_environment_int(
                "ADMISSION_TTL_SECONDS", 90 * 24 * 60 * 60
            ),
            max_body_bytes=_positive_environment_int(
                "MAX_WEBHOOK_BODY_BYTES", 1_048_576
            ),
            secret_cache_ttl_seconds=_positive_environment_int(
                "SECRET_CACHE_TTL_SECONDS", 300
            ),
        )


class WebhookHandler:
    """Verify, authorize, atomically limit, and start review workflows."""

    def __init__(
        self,
        *,
        settings: WebhookSettings | None = None,
        admission_store: AdmissionStore | None = None,
        secret_provider: CachedSecretProvider | None = None,
        secrets_client: SecretsManagerClient | None = None,
        step_functions_client: StepFunctionsClient | None = None,
        now: Callable[[], datetime] | None = None,
        run_id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        """Create a handler with injectable AWS boundaries for deterministic tests."""

        resolved_settings = settings or WebhookSettings.from_environment()
        self._settings = resolved_settings
        self._admission_store = admission_store or _default_admission_store(
            resolved_settings
        )
        self._secret_provider = secret_provider or CachedSecretProvider(
            secrets_client or _default_secrets_client(),
            resolved_settings.webhook_secret_arn,
            ttl_seconds=resolved_settings.secret_cache_ttl_seconds,
        )
        self._step_functions_client = (
            step_functions_client or _default_step_functions_client()
        )
        self._now = now or (lambda: datetime.now(UTC))
        self._run_id_factory = run_id_factory

    def handle(self, event: Mapping[str, object]) -> dict[str, object]:
        """Process one API Gateway delivery without exceeding configured budgets."""

        headers = _headers(event)
        raw_github_event = headers.get("x-github-event")
        github_event = (
            raw_github_event
            if raw_github_event in {"ping", "pull_request"}
            else "missing"
            if raw_github_event is None
            else "other"
        )
        request_context = {
            "github_event": github_event,
            "delivery_id_present": bool(headers.get("x-github-delivery")),
        }
        logger.info("webhook_received", extra=request_context)

        signature = headers.get("x-hub-signature-256")
        if not signature:
            logger.warning(
                "webhook_signature_missing",
                extra={
                    **request_context,
                    "signature_present": False,
                    "signature_format_valid": False,
                },
            )
            return _response(401, {"message": "invalid webhook signature"})

        try:
            body = _raw_body(event, max_bytes=self._settings.max_body_bytes)
        except WebhookBodyTooLargeError as error:
            logger.warning(
                "webhook_body_rejected",
                extra={
                    **request_context,
                    "reason": "body_too_large",
                    "error_type": type(error).__name__,
                },
            )
            return _response(413, {"message": str(error)})
        except WebhookPayloadError as error:
            logger.warning(
                "webhook_body_rejected",
                extra={
                    **request_context,
                    "reason": "invalid_body",
                    "error_type": type(error).__name__,
                },
            )
            return _response(400, {"message": str(error)})

        try:
            secret = self._secret_provider.get()
        except (BotoCoreError, ClientError, ValueError) as error:
            logger.exception(
                "webhook_secret_lookup_failed",
                extra={
                    **request_context,
                    "error_type": type(error).__name__,
                },
            )
            return _response(500, {"message": "webhook configuration unavailable"})

        signature_format_valid = (
            re.fullmatch(r"sha256=[0-9A-Fa-f]{64}", signature.strip()) is not None
        )
        if not verify_signature(body, signature, secret):
            logger.warning(
                (
                    "webhook_signature_mismatch"
                    if signature_format_valid
                    else "webhook_signature_malformed"
                ),
                extra={
                    **request_context,
                    "signature_present": True,
                    "signature_format_valid": signature_format_valid,
                },
            )
            return _response(401, {"message": "invalid webhook signature"})

        logger.info(
            "webhook_signature_verified",
            extra={**request_context, "body_size_bytes": len(body)},
        )

        try:
            payload = _json_payload(body)
        except (UnicodeDecodeError, json.JSONDecodeError, WebhookPayloadError) as error:
            logger.warning(
                "webhook_payload_rejected",
                extra={
                    **request_context,
                    "reason": "invalid_json",
                    "error_type": type(error).__name__,
                },
            )
            return _response(400, {"message": str(error)})

        raw_action = payload.get("action")
        github_action = (
            raw_action
            if isinstance(raw_action, str) and raw_action in {"opened", "synchronize"}
            else "missing"
            if raw_action is None
            else "other"
        )
        event_context = {**request_context, "github_action": github_action}
        try:
            parsed_event = parse_pull_request_event(
                headers.get("x-github-event"), payload
            )
        except WebhookPayloadError as error:
            logger.warning(
                "webhook_payload_rejected",
                extra={
                    **event_context,
                    "reason": "invalid_pull_request_payload",
                    "error_type": type(error).__name__,
                },
            )
            return _response(400, {"message": str(error)})

        if parsed_event is None:
            logger.info("webhook_event_ignored", extra=event_context)
            return _response(202, {"message": "event ignored"})

        delivery_id = headers.get("x-github-delivery", "")
        if not _DELIVERY_ID_PATTERN.fullmatch(delivery_id):
            logger.warning("webhook_delivery_id_rejected", extra=event_context)
            return _response(400, {"message": "invalid or missing GitHub delivery ID"})

        pr_id = f"{parsed_event.repo_full_name}#{parsed_event.pr_number}"
        delivery_context = {
            **event_context,
            "delivery_id": delivery_id,
            "repo": parsed_event.repo_full_name,
            "pr_id": pr_id,
            "pr_number": parsed_event.pr_number,
            "installation_id": parsed_event.installation_id,
        }
        logger.info("webhook_event_validated", extra=delivery_context)

        if not self._admission_store.policy.allows(parsed_event):
            logger.warning("webhook_not_allowed", extra=delivery_context)
            return _response(202, {"message": "event ignored by admission policy"})

        candidate_claim = _build_execution_claim(
            parsed_event,
            self._run_id_factory(),
            _as_utc(self._now()),
        )
        try:
            admission = self._admission_store.claim(
                parsed_event, delivery_id, candidate_claim
            )
        except (BotoCoreError, ClientError, ValueError) as error:
            logger.exception(
                "webhook_admission_failed",
                extra={
                    **delivery_context,
                    "correlation_id": str(candidate_claim.pipeline_run_id),
                    "error_type": type(error).__name__,
                },
            )
            return _response(500, {"message": "unable to record webhook"})

        admission_context = {
            **delivery_context,
            "admission_status": admission.status.value,
        }
        logger.info("webhook_admission_resolved", extra=admission_context)

        if admission.status is AdmissionStatus.QUOTA_EXCEEDED:
            logger.warning("webhook_quota_exceeded", extra=admission_context)
            return _response(202, {"message": "review quota reached"})

        execution_claim = admission.claim
        if execution_claim is None:
            logger.error("webhook_admission_missing_claim", extra=admission_context)
            return _response(500, {"message": "unable to record webhook"})

        pipeline_context = {
            **admission_context,
            "correlation_id": str(execution_claim.pipeline_run_id),
            "pipeline_run_id": str(execution_claim.pipeline_run_id),
            "state_machine_arn": self._settings.state_machine_arn,
        }
        logger.info("pipeline_start_requested", extra=pipeline_context)
        try:
            self._step_functions_client.start_execution(
                stateMachineArn=self._settings.state_machine_arn,
                name=str(execution_claim.pipeline_run_id),
                input=execution_claim.execution_input,
            )
        except ClientError as error:
            if _has_error_code(error, "ExecutionAlreadyExists"):
                logger.info("pipeline_execution_already_exists", extra=pipeline_context)
                return _duplicate_response(execution_claim)
            logger.exception(
                "pipeline_start_failed",
                extra={
                    **pipeline_context,
                    "error_type": type(error).__name__,
                },
            )
            return _response(500, {"message": "unable to start review pipeline"})
        except BotoCoreError as error:
            logger.exception(
                "pipeline_start_failed",
                extra={
                    **pipeline_context,
                    "error_type": type(error).__name__,
                },
            )
            return _response(500, {"message": "unable to start review pipeline"})

        logger.info("pipeline_started", extra=pipeline_context)
        if admission.status is AdmissionStatus.DUPLICATE:
            logger.info("webhook_duplicate_acknowledged", extra=pipeline_context)
            return _duplicate_response(execution_claim)
        return _response(
            202,
            {
                "message": "review pipeline started",
                "pipeline_run_id": str(execution_claim.pipeline_run_id),
            },
        )


def lambda_handler(event: Mapping[str, object], _context: object) -> dict[str, object]:
    """AWS Lambda entrypoint reusing clients and the secret cache when warm."""

    return _get_handler().handle(event)


@lru_cache(maxsize=1)
def _get_handler() -> WebhookHandler:
    """Build one warm-process handler so AWS clients and secrets are reused."""

    return WebhookHandler()


def _build_execution_claim(
    parsed_event: PullRequestEvent,
    pipeline_run_id: UUID,
    created_at: datetime,
) -> ExecutionClaim:
    """Build the persisted claim and byte-stable Step Functions input."""

    envelope = PipelineEnvelope(
        pipeline_run_id=pipeline_run_id,
        created_at=created_at,
        pr=PullRequestMetadata(
            repo_full_name=parsed_event.repo_full_name,
            pr_number=parsed_event.pr_number,
            commit_sha=parsed_event.commit_sha,
            installation_id=parsed_event.installation_id,
        ),
    )
    execution_input = json.dumps(
        envelope.model_dump(mode="json"), separators=(",", ":")
    )
    return ExecutionClaim(
        pipeline_run_id=pipeline_run_id,
        created_at=created_at,
        execution_input=execution_input,
    )


def _raw_body(event: Mapping[str, object], *, max_bytes: int) -> bytes:
    """Extract the exact signed bytes and reject oversized bodies immediately."""

    raw_body = event.get("body")
    if not isinstance(raw_body, str):
        raise WebhookPayloadError("request body must be a string")

    encoded = event.get("isBase64Encoded", False)
    if encoded is True:
        maximum_encoded_length = 4 * ((max_bytes + 2) // 3)
        if len(raw_body) > maximum_encoded_length:
            raise WebhookBodyTooLargeError("request body exceeds the configured limit")
        try:
            body = base64.b64decode(raw_body, validate=True)
        except ValueError as error:
            raise WebhookPayloadError("request body is not valid base64") from error
    elif encoded is False:
        body = raw_body.encode("utf-8")
    else:
        raise WebhookPayloadError("isBase64Encoded must be a boolean")

    if len(body) > max_bytes:
        raise WebhookBodyTooLargeError("request body exceeds the configured limit")
    return body


def _headers(event: Mapping[str, object]) -> dict[str, str]:
    """Normalise API Gateway's case-insensitive request headers."""

    raw_headers = event.get("headers")
    if not isinstance(raw_headers, Mapping):
        return {}
    typed_headers = cast(Mapping[object, object], raw_headers)
    return {
        key.lower(): value
        for key, value in typed_headers.items()
        if isinstance(key, str) and isinstance(value, str)
    }


def _json_payload(body: bytes) -> Mapping[str, object]:
    """Decode a verified body into a mapping before domain parsing."""

    payload = json.loads(body.decode("utf-8"))
    if not isinstance(payload, Mapping):
        raise WebhookPayloadError("request body must contain a JSON object")
    return cast(Mapping[str, object], payload)


def _has_error_code(error: ClientError, expected_code: str) -> bool:
    """Match one AWS service error code without hiding unrelated failures."""

    response = cast(Mapping[str, object], error.response)
    details = response.get("Error")
    if not isinstance(details, Mapping):
        return False
    return cast(Mapping[str, object], details).get("Code") == expected_code


def _duplicate_response(claim: ExecutionClaim) -> dict[str, object]:
    """Return an idempotent success that prevents GitHub redelivery."""

    return _response(
        202,
        {
            "message": "duplicate event ignored",
            "pipeline_run_id": str(claim.pipeline_run_id),
        },
    )


def _response(status_code: int, body: Mapping[str, object]) -> dict[str, object]:
    """Create the small JSON response expected by API Gateway."""

    return {
        "statusCode": status_code,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body, separators=(",", ":")),
    }


def _default_admission_store(settings: WebhookSettings) -> DynamoAdmissionStore:
    """Create an adaptive-retry DynamoDB client for idempotent transactions."""

    boto3_module = cast(Any, boto3)
    client = boto3_module.client(
        "dynamodb",
        config=Config(retries={"mode": "adaptive", "total_max_attempts": 3}),
    )
    return DynamoAdmissionStore(
        cast(DynamoDBClient, client),
        settings.review_table_name,
        settings.admission_policy,
    )


def _default_secrets_client() -> SecretsManagerClient:
    """Create the Secrets Manager client used by the deployed Lambda."""

    boto3_module = cast(Any, boto3)
    return cast(SecretsManagerClient, boto3_module.client("secretsmanager"))


def _default_step_functions_client() -> StepFunctionsClient:
    """Create the Step Functions client used by the deployed Lambda."""

    boto3_module = cast(Any, boto3)
    return cast(StepFunctionsClient, boto3_module.client("stepfunctions"))


def _required_environment(name: str) -> str:
    """Read one non-empty resource identifier from the Lambda environment."""

    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"{name} cannot be empty")
    return value


def _first_required_environment(*names: str) -> str:
    """Read the first configured alias for a resource identifier."""

    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    raise ValueError(f"one of {', '.join(names)} must be configured")


def _positive_environment_int(name: str, default: int) -> int:
    """Read a positive integer environment limit."""

    raw_value = os.getenv(name, str(default)).strip()
    try:
        value = int(raw_value)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error
    if value < 1:
        raise ValueError(f"{name} must be at least 1")
    return value


def _repository_allowlist(raw_value: str) -> frozenset[str]:
    """Parse an explicit repository list or the all-repositories sentinel."""

    repositories = frozenset(
        value.strip() for value in raw_value.split(",") if value.strip()
    )
    if not repositories:
        raise ValueError("ALLOWED_REPOSITORIES cannot be empty")
    if ALL_REPOSITORIES in repositories:
        if len(repositories) != 1:
            raise ValueError("ALLOWED_REPOSITORIES wildcard '*' must be used alone")
        return repositories
    if any(repository.count("/") != 1 for repository in repositories):
        raise ValueError("ALLOWED_REPOSITORIES entries must be owner/repository or '*'")
    return repositories


def _installation_allowlist(
    raw_value: str,
) -> frozenset[InstallationAllowlistEntry]:
    """Parse explicit installation IDs or the all-installations sentinel."""

    raw_entries = frozenset(
        value.strip() for value in raw_value.split(",") if value.strip()
    )
    if not raw_entries:
        raise ValueError("ALLOWED_INSTALLATION_IDS cannot be empty")
    if ALL_INSTALLATIONS in raw_entries:
        if len(raw_entries) != 1:
            raise ValueError("ALLOWED_INSTALLATION_IDS wildcard '*' must be used alone")
        return frozenset({ALL_INSTALLATIONS})
    try:
        installation_ids = frozenset(int(value) for value in raw_entries)
    except ValueError as error:
        raise ValueError(
            "ALLOWED_INSTALLATION_IDS must contain positive IDs or '*'"
        ) from error
    if any(value < 1 for value in installation_ids):
        raise ValueError("ALLOWED_INSTALLATION_IDS must contain positive IDs or '*'")
    return installation_ids


def _as_utc(value: datetime) -> datetime:
    """Normalise an injected clock value to an aware UTC timestamp."""

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
