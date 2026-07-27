"""Moto integration coverage for idempotent review-history writes."""

from __future__ import annotations

from pathlib import Path

import boto3
from moto import mock_aws

from arcus.contracts import PipelineEnvelope
from arcus.storage.history import ReviewHistoryStore

REGION = "us-east-1"
TABLE_NAME = "arcus-test-review-history"
FIXTURE = Path(__file__).parents[2] / "fixtures" / "envelopes" / "reporter.json"


@mock_aws
def test_repeated_review_write_replaces_the_same_deterministic_row() -> None:
    """Retries for one PR commit must not create duplicate history records."""

    client = boto3.client("dynamodb", region_name=REGION)
    client.create_table(
        TableName=TABLE_NAME,
        KeySchema=[
            {"AttributeName": "pk", "KeyType": "HASH"},
            {"AttributeName": "sk", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "pk", "AttributeType": "S"},
            {"AttributeName": "sk", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    envelope = PipelineEnvelope.model_validate_json(FIXTURE.read_text(encoding="utf-8"))
    store = ReviewHistoryStore(TABLE_NAME, client=client)

    store.put(envelope)
    store.put(envelope)

    items = client.scan(TableName=TABLE_NAME)["Items"]
    review_items = [item for item in items if item["item_type"]["S"] == "review"]
    repo_index_items = [
        item for item in items if item["item_type"]["S"] == "repo_index"
    ]
    assert len(review_items) == 1
    assert review_items[0]["pk"]["S"] == "REPO#acme/widgets"
    assert review_items[0]["sk"]["S"] == "REVIEW#42#abc123def4567890"
    assert review_items[0]["status"]["S"] == "ok"
    assert len(repo_index_items) == 1
    assert repo_index_items[0]["sk"]["S"] == "REPO#acme/widgets"


@mock_aws
def test_list_repositories_and_reviews_reflect_persisted_history() -> None:
    """The read-only dashboard API relies on these bounded query helpers."""

    client = boto3.client("dynamodb", region_name=REGION)
    client.create_table(
        TableName=TABLE_NAME,
        KeySchema=[
            {"AttributeName": "pk", "KeyType": "HASH"},
            {"AttributeName": "sk", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "pk", "AttributeType": "S"},
            {"AttributeName": "sk", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    envelope = PipelineEnvelope.model_validate_json(FIXTURE.read_text(encoding="utf-8"))
    store = ReviewHistoryStore(TABLE_NAME, client=client)
    store.put(envelope)

    repositories = store.list_repositories()
    assert repositories == ["acme/widgets"]

    reviews = store.list_reviews("acme/widgets")
    assert len(reviews) == 1
    assert reviews[0].envelope.pipeline_run_id == envelope.pipeline_run_id
    assert reviews[0].completed_at is not None

    assert store.list_reviews("acme/other") == []
