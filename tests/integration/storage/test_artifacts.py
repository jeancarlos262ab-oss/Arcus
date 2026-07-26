"""Moto integration coverage for the production S3 artifact boundary."""

from __future__ import annotations

import boto3
import pytest
from moto import mock_aws

from arcus.storage.artifacts import S3ArtifactStore

REGION = "us-east-1"
BUCKET_NAME = "arcus-test-context-artifacts"


@mock_aws
def test_s3_artifact_round_trip_enforces_bucket_and_size_bounds() -> None:
    """Production S3 reads must remain bounded and scoped to one configured bucket."""

    client = boto3.client("s3", region_name=REGION)
    client.create_bucket(Bucket=BUCKET_NAME)
    store = S3ArtifactStore(BUCKET_NAME, client=client, max_artifact_bytes=64)

    reference = store.put_text("prs/acme/widgets/42/diff.patch", "+ safe change")

    assert reference == f"s3://{BUCKET_NAME}/prs/acme/widgets/42/diff.patch"
    assert store.get_text(reference) == "+ safe change"
    with pytest.raises(ValueError, match="unexpected bucket"):
        store.get_text("s3://other-bucket/prs/acme/widgets/42/diff.patch")
    with pytest.raises(ValueError, match="configured byte limit"):
        store.put_text("oversized.txt", "x" * 65)
