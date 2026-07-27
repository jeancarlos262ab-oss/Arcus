"""Idempotent DynamoDB persistence for completed review envelopes."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Protocol, cast

from botocore.config import Config

from arcus.contracts import PipelineEnvelope


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


class ReviewHistoryStore:
    """Persist one row per repository, PR, and commit without duplicates."""

    def __init__(
        self,
        table_name: str,
        *,
        client: DynamoDBClient | None = None,
        ttl_seconds: int = 90 * 24 * 60 * 60,
    ) -> None:
        """Create an idempotent store over the shared history table."""

        if not table_name.strip():
            raise ValueError("history table name cannot be empty")
        if ttl_seconds < 1:
            raise ValueError("history TTL must be at least 1 second")
        self._table_name = table_name
        self._ttl_seconds = ttl_seconds
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

        payload = json.dumps(envelope.model_dump(mode="json"), separators=(",", ":"))
        ttl = int(envelope.created_at.timestamp()) + self._ttl_seconds
        self._client.put_item(
            TableName=self._table_name,
            Item={
                "pk": {"S": f"REPO#{envelope.pr.repo_full_name}"},
                "sk": {
                    "S": (f"REVIEW#{envelope.pr.pr_number}#{envelope.pr.commit_sha}")
                },
                "item_type": {"S": "review"},
                "pipeline_run_id": {"S": str(envelope.pipeline_run_id)},
                "status": {"S": envelope.report.status.value},
                "payload": {"S": payload},
                "ttl": {"N": str(ttl)},
            },
        )
