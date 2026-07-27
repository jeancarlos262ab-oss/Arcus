"""Warm GitHub App client factory for Fetch PR and Reporter Lambdas."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, cast

from arcus.config import get_settings
from arcus.github.api import GitHubClient
from arcus.github.app_auth import GitHubAppAuthenticator
from arcus.secrets import CachedSecretProvider, SecretsManagerClient


@lru_cache(maxsize=1)
def github_client() -> GitHubClient:
    """Create one cached GitHub client using the private-key secret."""

    raw_app_id = os.getenv("GITHUB_APP_ID", "").strip()
    secret_arn = os.getenv("GITHUB_APP_PRIVATE_KEY_SECRET_ARN", "").strip()
    if not raw_app_id or not secret_arn:
        raise ValueError("GitHub App ID and private-key secret ARN are required")
    try:
        app_id = int(raw_app_id)
    except ValueError as error:
        raise ValueError("GITHUB_APP_ID must be an integer") from error

    import boto3

    boto3_module = cast(Any, boto3)
    secrets_client = cast(SecretsManagerClient, boto3_module.client("secretsmanager"))
    private_key = CachedSecretProvider(
        secrets_client,
        secret_arn,
        ttl_seconds=300,
        field_names=("private_key", "github_app_private_key", "pem", "secret"),
    )
    api_base_url = os.getenv("GITHUB_API_BASE_URL", "https://api.github.com")
    authenticator = GitHubAppAuthenticator(
        app_id,
        private_key,
        api_base_url=api_base_url,
    )
    settings = get_settings()
    return GitHubClient(
        authenticator,
        api_base_url=api_base_url,
        max_changed_files=settings.max_changed_files,
        max_diff_bytes=settings.max_diff_bytes,
        max_repository_archive_bytes=settings.max_repository_archive_bytes,
    )
