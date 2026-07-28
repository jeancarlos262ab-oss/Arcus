"""Moto integration coverage for per-user dashboard state."""

from __future__ import annotations

import boto3
import pytest
from moto import mock_aws

from arcus.storage.users import UserProfile, UserStore

REGION = "us-east-1"
TABLE_NAME = "arcus-test-review-history"


def _create_table(client: object) -> None:
    client.create_table(  # type: ignore[attr-defined]
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


@mock_aws
def test_saved_profile_round_trips_identity_and_token() -> None:
    """A logged-in user's profile must be readable back exactly as saved."""

    client = boto3.client("dynamodb", region_name=REGION)
    _create_table(client)
    store = UserStore(TABLE_NAME, client=client)

    store.save_profile(
        UserProfile(
            github_user_id=42,
            github_login="octocat",
            github_user_token="gho_abc123",
            avatar_url="https://x.test/a.png",
        ),
        now_epoch=1_700_000_000,
    )

    profile = store.get_profile(42)
    assert profile is not None
    assert profile.github_login == "octocat"
    assert profile.github_user_token == "gho_abc123"
    assert profile.avatar_url == "https://x.test/a.png"


@mock_aws
def test_missing_profile_returns_none() -> None:
    """A user who never logged in must read back as absent, not raise."""

    client = boto3.client("dynamodb", region_name=REGION)
    _create_table(client)
    store = UserStore(TABLE_NAME, client=client)

    assert store.get_profile(999) is None


@mock_aws
def test_watchlist_round_trips_and_deduplicates() -> None:
    """A saved watchlist must return the same repos, without duplicates."""

    client = boto3.client("dynamodb", region_name=REGION)
    _create_table(client)
    store = UserStore(TABLE_NAME, client=client)

    saved = store.save_watchlist(
        42,
        ["octocat/repo-a", "octocat/repo-b", "octocat/repo-a"],
        now_epoch=1_700_000_000,
    )

    assert saved == ["octocat/repo-a", "octocat/repo-b"]
    assert store.get_watchlist(42) == ["octocat/repo-a", "octocat/repo-b"]


@mock_aws
def test_watchlist_defaults_to_empty_for_a_new_user() -> None:
    """A user with no saved selection must read back an empty list, not an error."""

    client = boto3.client("dynamodb", region_name=REGION)
    _create_table(client)
    store = UserStore(TABLE_NAME, client=client)

    assert store.get_watchlist(1) == []


@mock_aws
def test_watchlist_rejects_malformed_repository_names() -> None:
    """A repo name without exactly one 'owner/name' slash must be rejected."""

    client = boto3.client("dynamodb", region_name=REGION)
    _create_table(client)
    store = UserStore(TABLE_NAME, client=client)

    with pytest.raises(ValueError, match="owner/name"):
        store.save_watchlist(42, ["not-a-repo"], now_epoch=1_700_000_000)


@mock_aws
def test_watchlist_rejects_too_many_repositories() -> None:
    """A watchlist over the configured cap must be rejected before writing."""

    client = boto3.client("dynamodb", region_name=REGION)
    _create_table(client)
    store = UserStore(TABLE_NAME, client=client)
    too_many = [f"octocat/repo-{i}" for i in range(101)]

    with pytest.raises(ValueError, match="cannot exceed"):
        store.save_watchlist(42, too_many, now_epoch=1_700_000_000)


@mock_aws
def test_profiles_and_watchlists_are_isolated_per_user() -> None:
    """One user's saved data must never leak into another user's reads."""

    client = boto3.client("dynamodb", region_name=REGION)
    _create_table(client)
    store = UserStore(TABLE_NAME, client=client)

    store.save_profile(
        UserProfile(github_user_id=1, github_login="alice", github_user_token="t1"),
        now_epoch=1_700_000_000,
    )
    store.save_profile(
        UserProfile(github_user_id=2, github_login="bob", github_user_token="t2"),
        now_epoch=1_700_000_000,
    )
    store.save_watchlist(1, ["alice/repo"], now_epoch=1_700_000_000)
    store.save_watchlist(2, ["bob/repo"], now_epoch=1_700_000_000)

    assert store.get_profile(1).github_login == "alice"  # type: ignore[union-attr]
    assert store.get_profile(2).github_login == "bob"  # type: ignore[union-attr]
    assert store.get_watchlist(1) == ["alice/repo"]
    assert store.get_watchlist(2) == ["bob/repo"]
