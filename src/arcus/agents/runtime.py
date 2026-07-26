"""Warm runtime factories shared by deployed agent Lambdas."""

from __future__ import annotations

import os
from functools import lru_cache

from arcus.bedrock.client import BedrockClient
from arcus.config import Settings, get_settings
from arcus.storage.artifacts import S3ArtifactStore
from arcus.storage.history import ReviewHistoryStore


@lru_cache(maxsize=1)
def settings() -> Settings:
    """Return the validated process-wide runtime settings."""

    return get_settings()


@lru_cache(maxsize=1)
def artifacts() -> S3ArtifactStore:
    """Create one bounded S3 artifact store per warm process."""

    bucket_name = _required_environment("S3_ARTIFACT_BUCKET")
    return S3ArtifactStore(bucket_name, max_artifact_bytes=settings().max_diff_bytes)


@lru_cache(maxsize=1)
def model() -> BedrockClient:
    """Create one Converse client per warm process."""

    return BedrockClient(settings=settings())


@lru_cache(maxsize=1)
def history() -> ReviewHistoryStore:
    """Create one idempotent review-history store per warm process."""

    return ReviewHistoryStore(_required_environment("DDB_REVIEW_TABLE"))


def _required_environment(name: str) -> str:
    """Read one non-empty resource name from the Lambda environment."""

    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"{name} cannot be empty")
    return value
