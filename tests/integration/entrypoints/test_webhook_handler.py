"""Moto integration coverage for atomic webhook admission and idempotency."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

from arcus.contracts import PipelineEnvelope
from arcus.entrypoints.webhook_handler import _get_handler, lambda_handler

FIXTURE_PATH = (
    Path(__file__).parents[2] / "fixtures" / "webhooks" / "pull_request_opened.json"
)
REGION = "us-east-1"
TABLE_NAME = "arcus-test-review-history"
WEBHOOK_SECRET = "integration-webhook-secret"
DELIVERY_ID = "11111111-2222-3333-4444-555555555555"


def _signed_event(
    *,
    delivery_id: str = DELIVERY_ID,
    commit_sha: str = "abc123def4567890",
) -> dict[str, object]:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    payload["pull_request"]["head"]["sha"] = commit_sha
    body = json.dumps(payload, separators=(",", ":"))
    signature = hmac.new(
        WEBHOOK_SECRET.encode(), body.encode(), hashlib.sha256
    ).hexdigest()
    return {
        "headers": {
            "X-GitHub-Event": "pull_request",
            "X-GitHub-Delivery": delivery_id,
            "X-Hub-Signature-256": f"sha256={signature}",
        },
        "body": body,
        "isBase64Encoded": False,
    }


@mock_aws
def test_signed_delivery_atomically_consumes_quota_and_starts_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dynamodb = boto3.resource("dynamodb", region_name=REGION)
    table = dynamodb.create_table(
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

    secrets = boto3.client("secretsmanager", region_name=REGION)
    secret_arn = secrets.create_secret(
        Name="arcus-test-webhook-secret",
        SecretString=WEBHOOK_SECRET,
    )["ARN"]

    step_functions = boto3.client("stepfunctions", region_name=REGION)
    state_machine_arn = step_functions.create_state_machine(
        name="arcus-test-pr-pipeline",
        definition=json.dumps(
            {"StartAt": "Done", "States": {"Done": {"Type": "Succeed"}}}
        ),
        roleArn="arn:aws:iam::123456789012:role/arcus-test-step-functions",
        type="STANDARD",
    )["stateMachineArn"]

    monkeypatch.setenv("AWS_REGION", REGION)
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)
    monkeypatch.setenv("DDB_REVIEW_TABLE", TABLE_NAME)
    monkeypatch.setenv("STATE_MACHINE_ARN", state_machine_arn)
    monkeypatch.setenv("GITHUB_SECRET_ARN", secret_arn)
    monkeypatch.setenv("ALLOWED_REPOSITORIES", "acme/widgets")
    monkeypatch.setenv("ALLOWED_INSTALLATION_IDS", "123456")
    monkeypatch.setenv("REVIEWS_PER_REPOSITORY_DAY", "1")
    monkeypatch.setenv("REVIEWS_PER_INSTALLATION_HOUR", "1")
    _get_handler.cache_clear()

    try:
        first_response = lambda_handler(_signed_event(), None)
        assert first_response["statusCode"] == 202
        first_body = json.loads(first_response["body"])

        claim = table.get_item(
            Key={"pk": "REPO#acme/widgets", "sk": "DEDUP#42#abc123def4567890"},
            ConsistentRead=True,
        )["Item"]
        assert claim["pipeline_run_id"] == first_body["pipeline_run_id"]
        assert claim["ttl"] > int(datetime.now(UTC).timestamp())
        envelope = PipelineEnvelope.model_validate_json(claim["execution_input"])
        assert envelope.pr.repo_full_name == "acme/widgets"
        assert envelope.pr.base_commit_sha == "def456abc1237890"

        day = datetime.now(UTC).strftime("%Y-%m-%d")
        hour = datetime.now(UTC).strftime("%Y-%m-%dT%H")
        repository_quota = table.get_item(
            Key={"pk": "REPO#acme/widgets", "sk": f"QUOTA#DAY#{day}"}
        )["Item"]
        installation_quota = table.get_item(
            Key={"pk": "INSTALLATION#123456", "sk": f"QUOTA#HOUR#{hour}"}
        )["Item"]
        assert repository_quota["count"] == 1
        assert installation_quota["count"] == 1

        duplicate_response = lambda_handler(_signed_event(), None)
        assert duplicate_response["statusCode"] == 202
        duplicate_body = json.loads(duplicate_response["body"])
        assert duplicate_body["pipeline_run_id"] == first_body["pipeline_run_id"]

        assert (
            table.get_item(Key={"pk": "REPO#acme/widgets", "sk": f"QUOTA#DAY#{day}"})[
                "Item"
            ]["count"]
            == 1
        )

        quota_response = lambda_handler(
            _signed_event(
                delivery_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                commit_sha="different-commit-sha",
            ),
            None,
        )
        assert quota_response["statusCode"] == 202
        assert json.loads(quota_response["body"])["message"] == "review quota reached"

        executions = step_functions.list_executions(stateMachineArn=state_machine_arn)[
            "executions"
        ]
        assert len(executions) == 1
    finally:
        _get_handler.cache_clear()
