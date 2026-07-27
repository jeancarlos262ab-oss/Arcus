"""Moto integration coverage for the read-only dashboard API."""

from __future__ import annotations

import json
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

from arcus.contracts import PipelineEnvelope
from arcus.entrypoints.dashboard_api import _get_handler, lambda_handler

REGION = "us-east-1"
TABLE_NAME = "arcus-test-review-history"
BUCKET_NAME = "arcus-test-context-artifacts"
API_KEY = "integration-dashboard-api-key"
FIXTURE = Path(__file__).parents[2] / "fixtures" / "envelopes" / "reporter.json"
GRAPH_FIXTURE = (
    Path(__file__).parents[2] / "fixtures" / "graphs" / "example_repo_graph.json"
)


def _event(
    path: str,
    *,
    query: dict[str, str] | None = None,
    api_key: str | None = API_KEY,
) -> dict[str, object]:
    headers: dict[str, str] = {}
    if api_key is not None:
        headers["x-api-key"] = api_key
    return {
        "rawPath": path,
        "headers": headers,
        "queryStringParameters": query or {},
    }


@pytest.fixture(autouse=True)
def _clear_handler_cache() -> None:
    _get_handler.cache_clear()
    yield
    _get_handler.cache_clear()


def _configure_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dynamodb = boto3.client("dynamodb", region_name=REGION)
    dynamodb.create_table(
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

    s3 = boto3.client("s3", region_name=REGION)
    s3.create_bucket(Bucket=BUCKET_NAME)
    s3.put_object(
        Bucket=BUCKET_NAME,
        Key="graphs/acme/widgets/main.json",
        Body=GRAPH_FIXTURE.read_bytes(),
        ContentType="application/json",
    )

    secrets = boto3.client("secretsmanager", region_name=REGION)
    secret_arn = secrets.create_secret(
        Name="arcus-test-dashboard-api-key",
        SecretString=API_KEY,
    )["ARN"]

    envelope = PipelineEnvelope.model_validate_json(FIXTURE.read_text(encoding="utf-8"))
    from arcus.storage.history import ReviewHistoryStore

    ReviewHistoryStore(TABLE_NAME, client=dynamodb).put(envelope)

    monkeypatch.setenv("AWS_REGION", REGION)
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)
    monkeypatch.setenv("DDB_REVIEW_TABLE", TABLE_NAME)
    monkeypatch.setenv("S3_ARTIFACT_BUCKET", BUCKET_NAME)
    monkeypatch.setenv("DASHBOARD_API_KEY_SECRET_ARN", secret_arn)


@mock_aws
def test_repos_endpoint_lists_repositories_with_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_backend(monkeypatch)

    response = lambda_handler(_event("/repos"), None)

    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["repos"] == ["acme/widgets"]


@mock_aws
def test_reviews_endpoint_shapes_the_persisted_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_backend(monkeypatch)

    response = lambda_handler(_event("/reviews", query={"repo": "acme/widgets"}), None)

    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    runs = body["runs"]
    assert len(runs) == 1
    run = runs[0]
    assert run["repo_full_name"] == "acme/widgets"
    assert run["pr_title"] == "Add configurable retry policy"
    assert run["author"] == "octocat"
    assert run["findings_summary"]["total"] == 2
    assert run["findings_summary"]["by_severity"]["high"] == 1
    assert run["findings_summary"]["by_severity"]["medium"] == 1
    assert run["agent_status"]["report"] == "ok"
    assert run["duration_s"] >= 0
    # Fixes produced by Fix Suggester must be merged onto the original findings.
    assert all(f["fix"] is not None for f in run["findings"])


@mock_aws
def test_graph_endpoint_returns_the_persisted_repository_graph(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_backend(monkeypatch)

    response = lambda_handler(_event("/graph", query={"repo": "acme/widgets"}), None)

    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["repo"] == "acme/widgets"
    assert len(body["nodes"]) > 0


@mock_aws
def test_graph_endpoint_returns_404_for_unknown_repository(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_backend(monkeypatch)

    response = lambda_handler(_event("/graph", query={"repo": "acme/missing"}), None)

    assert response["statusCode"] == 404


@mock_aws
def test_missing_repo_query_param_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_backend(monkeypatch)

    response = lambda_handler(_event("/reviews"), None)

    assert response["statusCode"] == 400


@mock_aws
def test_missing_or_invalid_api_key_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_backend(monkeypatch)

    missing = lambda_handler(_event("/repos", api_key=None), None)
    invalid = lambda_handler(_event("/repos", api_key="wrong-key"), None)

    assert missing["statusCode"] == 401
    assert invalid["statusCode"] == 401


@mock_aws
def test_unknown_path_returns_404(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_backend(monkeypatch)

    response = lambda_handler(_event("/unknown"), None)

    assert response["statusCode"] == 404
