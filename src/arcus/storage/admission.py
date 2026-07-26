"""Atomic DynamoDB admission control for webhook-triggered review executions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal, Protocol, cast
from uuid import UUID

from botocore.exceptions import ClientError

from arcus.contracts import PipelineEnvelope
from arcus.github.webhook import PullRequestEvent

ALL_REPOSITORIES = "*"
ALL_INSTALLATIONS: Literal["*"] = "*"
type InstallationAllowlistEntry = int | Literal["*"]


class DynamoDBClient(Protocol):
    """Low-level DynamoDB operations required for atomic admission."""

    def transact_write_items(
        self,
        *,
        TransactItems: list[dict[str, object]],
        ClientRequestToken: str,
    ) -> Mapping[str, object]:
        """Commit deduplication and quota counters in one transaction."""
        ...

    def get_item(
        self,
        *,
        TableName: str,
        Key: Mapping[str, Mapping[str, str]],
        ConsistentRead: bool,
    ) -> Mapping[str, object]:
        """Read a claim used to classify a cancelled transaction."""
        ...


@dataclass(frozen=True, slots=True)
class AdmissionPolicy:
    """Fail-closed allowlists and bounded webhook usage windows."""

    allowed_repositories: frozenset[str]
    allowed_installation_ids: frozenset[InstallationAllowlistEntry]
    reviews_per_repository_day: int
    reviews_per_installation_hour: int
    item_ttl_seconds: int

    def __post_init__(self) -> None:
        """Reject policies that accidentally disable a hard cost boundary."""

        if not self.allowed_repositories:
            raise ValueError("at least one allowed repository is required")
        if (
            ALL_REPOSITORIES in self.allowed_repositories
            and len(self.allowed_repositories) != 1
        ):
            raise ValueError("the all-repositories wildcard must be used alone")
        if not self.allowed_installation_ids:
            raise ValueError("at least one allowed installation ID is required")
        if (
            ALL_INSTALLATIONS in self.allowed_installation_ids
            and len(self.allowed_installation_ids) != 1
        ):
            raise ValueError("the all-installations wildcard must be used alone")
        if any(
            isinstance(value, bool)
            or (isinstance(value, int) and value < 1)
            or (not isinstance(value, int) and value != ALL_INSTALLATIONS)
            for value in self.allowed_installation_ids
        ):
            raise ValueError("installation entries must be positive IDs or '*'")
        if self.reviews_per_repository_day < 1:
            raise ValueError("repository daily quota must be at least 1")
        if self.reviews_per_installation_hour < 1:
            raise ValueError("installation hourly quota must be at least 1")
        if self.item_ttl_seconds < 1:
            raise ValueError("admission TTL must be at least 1 second")

    def allows(self, event: PullRequestEvent) -> bool:
        """Apply repository and installation admission before spending quota."""

        repository_allowed = (
            ALL_REPOSITORIES in self.allowed_repositories
            or event.repo_full_name in self.allowed_repositories
        )
        installation_allowed = (
            ALL_INSTALLATIONS in self.allowed_installation_ids
            or event.installation_id in self.allowed_installation_ids
        )
        return repository_allowed and installation_allowed


@dataclass(frozen=True, slots=True)
class ExecutionClaim:
    """Persisted identity and exact Step Functions input for one review."""

    pipeline_run_id: UUID
    created_at: datetime
    execution_input: str


class AdmissionStatus(StrEnum):
    """Outcome of an atomic admission transaction."""

    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"
    QUOTA_EXCEEDED = "quota_exceeded"


@dataclass(frozen=True, slots=True)
class AdmissionResult:
    """Admission outcome and reusable execution identity when available."""

    status: AdmissionStatus
    claim: ExecutionClaim | None = None


class DynamoAdmissionStore:
    """Claim deliveries and increment both quota windows atomically."""

    def __init__(
        self,
        client: DynamoDBClient,
        table_name: str,
        policy: AdmissionPolicy,
    ) -> None:
        """Create a store over one Arcus review-history table."""

        self._client = client
        self._table_name = table_name
        self._policy = policy

    @property
    def policy(self) -> AdmissionPolicy:
        """Expose the immutable policy for pre-transaction allowlist checks."""

        return self._policy

    def claim(
        self,
        event: PullRequestEvent,
        delivery_id: str,
        candidate: ExecutionClaim,
    ) -> AdmissionResult:
        """Atomically deduplicate and consume repository/installation quotas."""

        now = candidate.created_at.astimezone(UTC)
        ttl = int(now.timestamp()) + self._policy.item_ttl_seconds
        claim_pk = f"REPO#{event.repo_full_name}"
        claim_sk = f"DEDUP#{event.pr_number}#{event.commit_sha}"
        delivery_pk = f"DELIVERY#{delivery_id}"
        day = now.strftime("%Y-%m-%d")
        hour = now.strftime("%Y-%m-%dT%H")

        transaction: list[dict[str, object]] = [
            {
                "Put": {
                    "TableName": self._table_name,
                    "Item": {
                        "pk": {"S": delivery_pk},
                        "sk": {"S": "CLAIM"},
                        "item_type": {"S": "delivery"},
                        "claim_pk": {"S": claim_pk},
                        "claim_sk": {"S": claim_sk},
                        "ttl": {"N": str(ttl)},
                    },
                    "ConditionExpression": "attribute_not_exists(pk)",
                }
            },
            {
                "Put": {
                    "TableName": self._table_name,
                    "Item": {
                        "pk": {"S": claim_pk},
                        "sk": {"S": claim_sk},
                        "item_type": {"S": "dedup"},
                        "pipeline_run_id": {"S": str(candidate.pipeline_run_id)},
                        "status": {"S": "in_progress"},
                        "created_at": {"S": candidate.created_at.isoformat()},
                        "execution_input": {"S": candidate.execution_input},
                        "ttl": {"N": str(ttl)},
                    },
                    "ConditionExpression": "attribute_not_exists(pk)",
                }
            },
            self._quota_update(
                pk=claim_pk,
                sk=f"QUOTA#DAY#{day}",
                item_type="repository_daily_quota",
                limit=self._policy.reviews_per_repository_day,
                ttl=ttl,
            ),
            self._quota_update(
                pk=f"INSTALLATION#{event.installation_id}",
                sk=f"QUOTA#HOUR#{hour}",
                item_type="installation_hourly_quota",
                limit=self._policy.reviews_per_installation_hour,
                ttl=ttl,
            ),
        ]

        try:
            self._client.transact_write_items(
                TransactItems=transaction,
                ClientRequestToken=str(candidate.pipeline_run_id),
            )
        except ClientError as error:
            if _client_error_code(error) != "TransactionCanceledException":
                raise
            duplicate = self._load_duplicate(claim_pk, claim_sk, delivery_pk)
            if duplicate is not None:
                return AdmissionResult(AdmissionStatus.DUPLICATE, duplicate)

            response = cast(Mapping[str, object], error.response)
            raw_reasons = response.get("CancellationReasons")
            if not isinstance(raw_reasons, list):
                raise
            reasons = cast(list[object], raw_reasons)
            quota_exceeded = False
            for index in (2, 3):
                if index >= len(reasons):
                    continue
                raw_reason = reasons[index]
                if not isinstance(raw_reason, Mapping):
                    continue
                reason = cast(Mapping[str, object], raw_reason)
                if reason.get("Code") == "ConditionalCheckFailed":
                    quota_exceeded = True
                    break
            if quota_exceeded:
                return AdmissionResult(AdmissionStatus.QUOTA_EXCEEDED)
            raise

        return AdmissionResult(AdmissionStatus.ACCEPTED, candidate)

    def _quota_update(
        self,
        *,
        pk: str,
        sk: str,
        item_type: str,
        limit: int,
        ttl: int,
    ) -> dict[str, object]:
        """Build one transactional bounded counter update."""

        return {
            "Update": {
                "TableName": self._table_name,
                "Key": {"pk": {"S": pk}, "sk": {"S": sk}},
                "UpdateExpression": (
                    "SET #count = if_not_exists(#count, :zero) + :one, "
                    "#ttl = :ttl, #item_type = :item_type"
                ),
                "ConditionExpression": "attribute_not_exists(#count) OR #count < :limit",
                "ExpressionAttributeNames": {
                    "#count": "count",
                    "#ttl": "ttl",
                    "#item_type": "item_type",
                },
                "ExpressionAttributeValues": {
                    ":zero": {"N": "0"},
                    ":one": {"N": "1"},
                    ":limit": {"N": str(limit)},
                    ":ttl": {"N": str(ttl)},
                    ":item_type": {"S": item_type},
                },
            }
        }

    def _load_duplicate(
        self,
        claim_pk: str,
        claim_sk: str,
        delivery_pk: str,
    ) -> ExecutionClaim | None:
        """Resolve either logical-claim or delivery-ID duplication."""

        logical_claim = self._load_claim(claim_pk, claim_sk)
        if logical_claim is not None:
            return logical_claim

        delivery = self._get_item(delivery_pk, "CLAIM")
        if delivery is None:
            return None
        original_pk = _string_attribute(delivery, "claim_pk")
        original_sk = _string_attribute(delivery, "claim_sk")
        if original_pk is None or original_sk is None:
            raise ValueError("persisted delivery claim is malformed")
        return self._load_claim(original_pk, original_sk)

    def _load_claim(self, pk: str, sk: str) -> ExecutionClaim | None:
        """Validate one persisted execution claim before it is reused."""

        item = self._get_item(pk, sk)
        if item is None:
            return None
        raw_run_id = _string_attribute(item, "pipeline_run_id")
        execution_input = _string_attribute(item, "execution_input")
        created_at = _string_attribute(item, "created_at")
        if raw_run_id is None or execution_input is None or created_at is None:
            raise ValueError("persisted execution claim is malformed")

        run_id = UUID(raw_run_id)
        envelope = PipelineEnvelope.model_validate_json(execution_input)
        if envelope.pipeline_run_id != run_id:
            raise ValueError("persisted execution claim has inconsistent identifiers")
        return ExecutionClaim(
            pipeline_run_id=run_id,
            created_at=datetime.fromisoformat(created_at),
            execution_input=execution_input,
        )

    def _get_item(self, pk: str, sk: str) -> Mapping[str, object] | None:
        """Read one low-level DynamoDB item consistently."""

        response = self._client.get_item(
            TableName=self._table_name,
            Key={"pk": {"S": pk}, "sk": {"S": sk}},
            ConsistentRead=True,
        )
        raw_item = response.get("Item")
        if not isinstance(raw_item, Mapping):
            return None
        return cast(Mapping[str, object], raw_item)


def _string_attribute(item: Mapping[str, object], name: str) -> str | None:
    """Read one string from a low-level DynamoDB attribute map."""

    raw_attribute = item.get(name)
    if not isinstance(raw_attribute, Mapping):
        return None
    attribute = cast(Mapping[str, object], raw_attribute)
    value = attribute.get("S")
    return value if isinstance(value, str) else None


def _client_error_code(error: ClientError) -> str:
    """Extract one stable DynamoDB error code."""

    raw_error = cast(Mapping[str, object], error.response).get("Error")
    if not isinstance(raw_error, Mapping):
        return "unknown"
    code = cast(Mapping[str, object], raw_error).get("Code")
    return code if isinstance(code, str) else "unknown"
