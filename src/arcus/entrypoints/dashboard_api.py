"""Lambda entrypoint serving read-only dashboard data over HTTP.

The dashboard SPA is a pure consumer of DynamoDB review history and S3 graph
artifacts. This handler never writes; it validates a shared API key, routes
one of three bounded GET requests, and shapes the persisted
``PipelineEnvelope`` into the JSON the dashboard already expects.
"""

from __future__ import annotations

import hmac
import json
import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, cast

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from arcus.contracts import Finding, PipelineEnvelope, RepoGraph
from arcus.secrets import CachedSecretProvider, SecretsManagerClient
from arcus.storage.artifacts import S3ArtifactStore
from arcus.storage.history import ReviewHistoryStore, ReviewRecord

logger = logging.getLogger(__name__)

_AGENT_SECTIONS = ("context", "consistency", "bugs", "fixes", "report")
_NOT_FOUND_ERROR_CODES = frozenset({"NoSuchKey", "404"})


@dataclass(frozen=True, slots=True)
class DashboardApiSettings:
    """Validated runtime configuration for the read-only dashboard API."""

    review_table_name: str
    artifact_bucket_name: str
    api_key_secret_arn: str
    secret_cache_ttl_seconds: int = 300
    max_reviews_per_repo: int = 200

    def __post_init__(self) -> None:
        """Reject settings that would silently disable a hard limit."""

        if self.secret_cache_ttl_seconds < 1:
            raise ValueError("secret cache TTL must be at least 1 second")
        if self.max_reviews_per_repo < 1:
            raise ValueError("max_reviews_per_repo must be at least 1")

    @classmethod
    def from_environment(cls) -> DashboardApiSettings:
        """Load resource identifiers required to serve read-only requests."""

        return cls(
            review_table_name=_required_environment("DDB_REVIEW_TABLE"),
            artifact_bucket_name=_required_environment("S3_ARTIFACT_BUCKET"),
            api_key_secret_arn=_required_environment("DASHBOARD_API_KEY_SECRET_ARN"),
        )


class DashboardApiHandler:
    """Serve repositories, reviews, and context graphs to the dashboard SPA."""

    def __init__(
        self,
        *,
        settings: DashboardApiSettings,
        history_store: ReviewHistoryStore,
        artifact_store: S3ArtifactStore,
        api_key_provider: CachedSecretProvider,
    ) -> None:
        """Create a handler with injectable AWS boundaries for deterministic tests."""

        self._settings = settings
        self._history = history_store
        self._artifacts = artifact_store
        self._api_key_provider = api_key_provider

    def handle(self, event: Mapping[str, object]) -> dict[str, object]:
        """Authenticate and route one bounded read-only API Gateway request."""

        try:
            expected_key = self._api_key_provider.get()
        except (BotoCoreError, ClientError, ValueError):
            logger.exception("dashboard_api_key_lookup_failed")
            return _response(500, {"message": "dashboard API is not configured"})

        provided_key = _headers(event).get("x-api-key", "")
        if not provided_key or not hmac.compare_digest(provided_key, expected_key):
            logger.warning("dashboard_api_key_rejected")
            return _response(401, {"message": "invalid or missing API key"})

        path = _request_path(event)
        query = _query_params(event)
        try:
            if path == "/repos":
                return self._list_repos()
            if path == "/reviews":
                return self._list_reviews(query)
            if path == "/graph":
                return self._get_graph(query)
        except _ClientRequestError as error:
            return _response(error.status_code, {"message": error.message})
        except (BotoCoreError, ClientError):
            logger.exception("dashboard_api_backend_failed", extra={"path": path})
            return _response(500, {"message": "unable to read dashboard data"})

        return _response(404, {"message": "not found"})

    def _list_repos(self) -> dict[str, object]:
        """Return every repository with at least one persisted review."""

        return _response(200, {"repos": self._history.list_repositories()})

    def _list_reviews(self, query: Mapping[str, str]) -> dict[str, object]:
        """Return one repository's reviews, most recent first."""

        repo = _required_query_param(query, "repo")
        records = self._history.list_reviews(
            repo, limit=self._settings.max_reviews_per_repo
        )
        return _response(200, {"runs": [_review_run(record) for record in records]})

    def _get_graph(self, query: Mapping[str, str]) -> dict[str, object]:
        """Return the persisted repository-wide context graph."""

        repo = _required_query_param(query, "repo")
        graph_ref = self._artifacts.reference(f"graphs/{repo}/main.json")
        try:
            graph = RepoGraph.model_validate(self._artifacts.get_json(graph_ref))
        except ValueError as error:
            raise _ClientRequestError(404, "graph not found for repository") from error
        except ClientError as error:
            error_code = error.response.get("Error", {}).get("Code")
            if error_code in _NOT_FOUND_ERROR_CODES:
                raise _ClientRequestError(
                    404, "graph not found for repository"
                ) from error
            raise
        return _response(200, graph.model_dump(mode="json"))


class _ClientRequestError(Exception):
    """A request could not be served because of caller-supplied input."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def _review_run(record: ReviewRecord) -> dict[str, object]:
    """Shape one persisted envelope into the dashboard's ``ReviewRun`` schema."""

    envelope = record.envelope
    findings = _merged_findings(envelope)
    by_severity = {"high": 0, "medium": 0, "low": 0}
    by_type: dict[str, int] = {}
    for finding in findings:
        by_severity[finding.severity.value] += 1
        by_type[finding.type.value] = by_type.get(finding.type.value, 0) + 1

    duration_s = max(0.0, (record.completed_at - envelope.created_at).total_seconds())
    return {
        "pipeline_run_id": str(envelope.pipeline_run_id),
        "repo_full_name": envelope.pr.repo_full_name,
        "pr_number": envelope.pr.pr_number,
        "pr_title": envelope.pr.pr_title,
        "author": envelope.pr.author,
        "commit_sha": envelope.pr.commit_sha,
        "created_at": envelope.created_at.isoformat(),
        "agent_status": {
            name: cast(Any, getattr(envelope, name)).status.value
            for name in _AGENT_SECTIONS
        },
        "findings_summary": {
            "total": len(findings),
            "by_severity": by_severity,
            "by_type": by_type,
        },
        "comment_url": envelope.report.comment_url,
        "ran_diff_only": envelope.context.ran_diff_only,
        "duration_s": round(duration_s, 1),
        "findings": [_finding_json(finding) for finding in findings],
    }


def _merged_findings(envelope: PipelineEnvelope) -> list[Finding]:
    """Combine consistency/bug findings with any fix produced by Fix Suggester."""

    fixes_by_id = {finding.id: finding.fix for finding in envelope.fixes.findings}
    combined = [*envelope.consistency.findings, *envelope.bugs.findings]
    return [
        finding.model_copy(update={"fix": fixes_by_id.get(finding.id, finding.fix)})
        for finding in combined
    ]


def _finding_json(finding: Finding) -> dict[str, object]:
    """Serialize one finding using the same field names as the shared contract."""

    return cast(dict[str, object], finding.model_dump(mode="json"))


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


def _request_path(event: Mapping[str, object]) -> str:
    """Read the normalised HTTP API v2 request path."""

    raw_path = event.get("rawPath")
    if isinstance(raw_path, str) and raw_path:
        return raw_path.rstrip("/") or "/"
    return "/"


def _query_params(event: Mapping[str, object]) -> dict[str, str]:
    """Read HTTP API v2 query-string parameters."""

    raw_params = event.get("queryStringParameters")
    if not isinstance(raw_params, Mapping):
        return {}
    typed_params = cast(Mapping[object, object], raw_params)
    return {
        key: value
        for key, value in typed_params.items()
        if isinstance(key, str) and isinstance(value, str)
    }


def _required_query_param(query: Mapping[str, str], name: str) -> str:
    """Read one required, non-empty query-string parameter."""

    value = query.get(name, "").strip()
    if not value:
        raise _ClientRequestError(400, f"query parameter '{name}' is required")
    return value


def _response(status_code: int, body: Mapping[str, object]) -> dict[str, object]:
    """Create the small JSON response expected by API Gateway."""

    return {
        "statusCode": status_code,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body, separators=(",", ":")),
    }


def _required_environment(name: str) -> str:
    """Read one non-empty resource identifier from the Lambda environment."""

    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"{name} cannot be empty")
    return value


def lambda_handler(event: Mapping[str, object], _context: object) -> dict[str, object]:
    """AWS Lambda entrypoint reusing clients and the secret cache when warm."""

    return _get_handler().handle(event)


@lru_cache(maxsize=1)
def _get_handler() -> DashboardApiHandler:
    """Build one warm-process handler so AWS clients and the API key are reused."""

    settings = DashboardApiSettings.from_environment()
    boto3_module = cast(Any, boto3)
    retry_config = Config(retries={"mode": "adaptive", "total_max_attempts": 3})
    dynamodb_client = boto3_module.client("dynamodb", config=retry_config)
    s3_client = boto3_module.client("s3", config=retry_config)
    secrets_client = cast(SecretsManagerClient, boto3_module.client("secretsmanager"))
    return DashboardApiHandler(
        settings=settings,
        history_store=ReviewHistoryStore(
            settings.review_table_name, client=dynamodb_client
        ),
        artifact_store=S3ArtifactStore(settings.artifact_bucket_name, client=s3_client),
        api_key_provider=CachedSecretProvider(
            secrets_client,
            settings.api_key_secret_arn,
            ttl_seconds=settings.secret_cache_ttl_seconds,
            field_names=("api_key", "dashboard_api_key", "secret"),
        ),
    )
