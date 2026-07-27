"""Idempotent DynamoDB persistence and bounded reads for review envelopes."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol, cast

from botocore.config import Config
from pydantic import ValidationError

from arcus.contracts import PipelineEnvelope

logger = logging.getLogger(__name__)

_REPO_INDEX_PK = "REPOS"


class DynamoDBClient(Protocol):
    """Minimal low-level DynamoDB history interface."""

    def put_item(
        self,
        *,
        TableName: str,
        Item: Mapping[str, Mapping[str, str]],
    ) -> Mapping[str, object]:
        """Upsert one deterministic review key."""
        ...

    def query(
        self,
        *,
        TableName: str,
        KeyConditionExpression: str,
        ExpressionAttributeValues: Mapping[str, Mapping[str, str]],
    ) -> Mapping[str, object]:
        """Read one bounded page of items sharing a partition key."""
        ...


@dataclass(frozen=True, slots=True)
class ReviewRecord:
    """One persisted review envelope plus its derived completion time."""

    envelope: PipelineEnvelope
    completed_at: datetime


class ReviewHistoryStore:
    """Persist one row per repository, PR, and commit without duplicates."""

    def __init__(
        self,
        table_name: str,
        *,
        client: DynamoDBClient | None = None,
        ttl_seconds: int = 90 * 24 * 60 * 60,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        """Create an idempotent store over the shared history table."""

        if not table_name.strip():
            raise ValueError("history table name cannot be empty")
        if ttl_seconds < 1:
            raise ValueError("history TTL must be at least 1 second")
        self._table_name = table_name
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        if client is None:
            import boto3

            boto3_module = cast(Any, boto3)
            raw_client = boto3_module.client(
                "dynamodb",
                config=Config(retries={"mode": "adaptive", "total_max_attempts": 3}),
            )
            self._client = cast(DynamoDBClient, raw_client)
        else:
            self._client = client

    def put(self, envelope: PipelineEnvelope) -> None:
        """Upsert the deterministic review row produced by Reporter."""

        completed_at = self._clock()
        payload = json.dumps(envelope.model_dump(mode="json"), separators=(",", ":"))
        ttl = int(envelope.created_at.timestamp()) + self._ttl_seconds
        repo_pk = f"REPO#{envelope.pr.repo_full_name}"
        self._client.put_item(
            TableName=self._table_name,
            Item={
                "pk": {"S": repo_pk},
                "sk": {
                    "S": (f"REVIEW#{envelope.pr.pr_number}#{envelope.pr.commit_sha}")
                },
                "item_type": {"S": "review"},
                "pipeline_run_id": {"S": str(envelope.pipeline_run_id)},
                "status": {"S": envelope.report.status.value},
                "payload": {"S": payload},
                "completed_at": {"S": completed_at.isoformat()},
                "ttl": {"N": str(ttl)},
            },
        )
        # Lightweight repo registry: lets the read-only dashboard API discover
        # which repositories have history without scanning the whole table.
        self._client.put_item(
            TableName=self._table_name,
            Item={
                "pk": {"S": _REPO_INDEX_PK},
                "sk": {"S": f"REPO#{envelope.pr.repo_full_name}"},
                "item_type": {"S": "repo_index"},
                "ttl": {"N": str(ttl)},
            },
        )

    def list_repositories(self) -> list[str]:
        """Return every repository that has at least one persisted review."""

        response = self._client.query(
            TableName=self._table_name,
            KeyConditionExpression="pk = :pk",
            ExpressionAttributeValues={":pk": {"S": _REPO_INDEX_PK}},
        )
        repositories: list[str] = []
        for item in _items(response):
            sk = _string_attribute(item, "sk")
            if sk is not None and sk.startswith("REPO#"):
                repositories.append(sk[len("REPO#") :])
        return sorted(repositories)

    def list_reviews(
        self, repo_full_name: str, *, limit: int = 200
    ) -> list[ReviewRecord]:
        """Return one repository's reviews, most recent first, bounded by limit."""

        if limit < 1:
            raise ValueError("limit must be at least 1")
        response = self._client.query(
            TableName=self._table_name,
            KeyConditionExpression="pk = :pk AND begins_with(sk, :prefix)",
            ExpressionAttributeValues={
                ":pk": {"S": f"REPO#{repo_full_name}"},
                ":prefix": {"S": "REVIEW#"},
            },
        )
        records = [
            record
            for record in (_to_record(item) for item in _items(response))
            if record
        ]
        records.sort(key=lambda record: record.envelope.created_at, reverse=True)
        return records[:limit]


def _items(response: Mapping[str, object]) -> list[Mapping[str, object]]:
    """Extract the low-level item list from a DynamoDB query response."""

    raw_items = response.get("Items")
    if not isinstance(raw_items, list):
        return []
    return [item for item in raw_items if isinstance(item, Mapping)]


def _to_record(item: Mapping[str, object]) -> ReviewRecord | None:
    """Validate one persisted review row, skipping malformed history rows.

    Rows written before a contract change (e.g. a newly required field on
    ``PullRequestMetadata``) can fail validation against the current schema.
    Such rows are logged and skipped rather than failing the whole read, so
    one legacy row never takes down the dashboard for an entire repository.
    """

    payload = _string_attribute(item, "payload")
    completed_at_raw = _string_attribute(item, "completed_at")
    if payload is None:
        return None
    try:
        envelope = PipelineEnvelope.model_validate_json(payload)
    except ValidationError:
        logger.warning(
            "history_row_schema_mismatch",
            extra={
                "pk": _string_attribute(item, "pk"),
                "sk": _string_attribute(item, "sk"),
            },
        )
        return None
    completed_at = (
        datetime.fromisoformat(completed_at_raw)
        if completed_at_raw is not None
        else envelope.created_at
    )
    return ReviewRecord(envelope=envelope, completed_at=completed_at)


def _string_attribute(item: Mapping[str, object], name: str) -> str | None:
    """Read one string from a low-level DynamoDB attribute map."""

    raw_attribute = item.get(name)
    if not isinstance(raw_attribute, Mapping):
        return None
    attribute = cast(Mapping[str, object], raw_attribute)
    value = attribute.get("S")
    return value if isinstance(value, str) else None
