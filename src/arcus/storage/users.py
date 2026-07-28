"""Per-user dashboard state: the GitHub user token and repo watchlist.

Reuses the shared ``ReviewHistoryTable`` with a distinct partition prefix
(``USER#{github_user_id}``) instead of a new table, matching the project's
single-table pattern. Nothing here is read by the review pipeline; it exists
only so the dashboard can show one logged-in person their own repositories
and remembered selection across sessions.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, cast

from botocore.config import Config

_PROFILE_SK = "PROFILE"
_WATCHLIST_SK = "WATCHLIST"
_MAX_WATCHLIST_REPOS = 100
_REPO_PATTERN_MAX_LENGTH = 200


class DynamoDBClient(Protocol):
    """Minimal low-level DynamoDB interface required by the user store."""

    def put_item(
        self,
        *,
        TableName: str,
        Item: Mapping[str, Mapping[str, object]],
    ) -> Mapping[str, object]:
        """Upsert one per-user item."""
        ...

    def get_item(
        self,
        *,
        TableName: str,
        Key: Mapping[str, Mapping[str, str]],
    ) -> Mapping[str, object]:
        """Read one per-user item."""
        ...


@dataclass(frozen=True, slots=True)
class UserProfile:
    """The minimal identity and credential persisted for one logged-in user."""

    github_user_id: int
    github_login: str
    github_user_token: str
    avatar_url: str | None = None


class UserStore:
    """Persist one GitHub user's token and repository watchlist."""

    def __init__(
        self,
        table_name: str,
        *,
        client: DynamoDBClient | None = None,
        ttl_seconds: int = 30 * 24 * 60 * 60,
    ) -> None:
        """Create a store over the shared review-history table."""

        if not table_name.strip():
            raise ValueError("user store table name cannot be empty")
        if ttl_seconds < 1:
            raise ValueError("user store TTL must be at least 1 second")
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

    def save_profile(self, profile: UserProfile, *, now_epoch: int) -> None:
        """Upsert the logged-in user's identity and GitHub access token.

        The token is overwritten on every login, so signing out and back in
        always refreshes it; nothing here revokes it on GitHub's side.
        """

        item: dict[str, Mapping[str, object]] = {
            "pk": {"S": _user_pk(profile.github_user_id)},
            "sk": {"S": _PROFILE_SK},
            "item_type": {"S": "user_profile"},
            "github_login": {"S": profile.github_login},
            "github_user_token": {"S": profile.github_user_token},
            "ttl": {"N": str(now_epoch + self._ttl_seconds)},
        }
        if profile.avatar_url:
            item["avatar_url"] = {"S": profile.avatar_url}
        self._client.put_item(TableName=self._table_name, Item=item)

    def get_profile(self, github_user_id: int) -> UserProfile | None:
        """Read one user's persisted identity and token, if still present."""

        response = self._client.get_item(
            TableName=self._table_name,
            Key={"pk": {"S": _user_pk(github_user_id)}, "sk": {"S": _PROFILE_SK}},
        )
        item = _item(response)
        if item is None:
            return None
        login = _string_attribute(item, "github_login")
        token = _string_attribute(item, "github_user_token")
        if login is None or token is None:
            return None
        return UserProfile(
            github_user_id=github_user_id,
            github_login=login,
            github_user_token=token,
            avatar_url=_string_attribute(item, "avatar_url"),
        )

    def get_watchlist(self, github_user_id: int) -> list[str]:
        """Read the repositories one user chose to see, in saved order."""

        response = self._client.get_item(
            TableName=self._table_name,
            Key={"pk": {"S": _user_pk(github_user_id)}, "sk": {"S": _WATCHLIST_SK}},
        )
        item = _item(response)
        if item is None:
            return []
        return _string_list_attribute(item, "repos")

    def save_watchlist(
        self, github_user_id: int, repos: list[str], *, now_epoch: int
    ) -> list[str]:
        """Replace one user's watchlist with a validated, deduplicated list."""

        if len(repos) > _MAX_WATCHLIST_REPOS:
            raise ValueError(
                f"watchlist cannot exceed {_MAX_WATCHLIST_REPOS} repositories"
            )
        deduplicated: list[str] = []
        seen: set[str] = set()
        for repo in repos:
            name = repo.strip()
            if not name or len(name) > _REPO_PATTERN_MAX_LENGTH:
                raise ValueError(f"invalid repository name: {repo!r}")
            if name.count("/") != 1:
                raise ValueError(f"repository must be owner/name: {repo!r}")
            if name not in seen:
                seen.add(name)
                deduplicated.append(name)

        self._client.put_item(
            TableName=self._table_name,
            Item={
                "pk": {"S": _user_pk(github_user_id)},
                "sk": {"S": _WATCHLIST_SK},
                "item_type": {"S": "user_watchlist"},
                "repos": {"L": [{"S": repo} for repo in deduplicated]},
                "ttl": {"N": str(now_epoch + self._ttl_seconds)},
            },
        )
        return deduplicated


def _user_pk(github_user_id: int) -> str:
    """Build the partition key scoping every item to one GitHub user."""

    return f"USER#{github_user_id}"


def _item(response: Mapping[str, object]) -> Mapping[str, object] | None:
    """Extract the low-level item from a DynamoDB get_item response."""

    raw_item = response.get("Item")
    if not isinstance(raw_item, Mapping):
        return None
    return cast(Mapping[str, object], raw_item)


def _string_attribute(item: Mapping[str, object], name: str) -> str | None:
    """Read one string from a low-level DynamoDB attribute map."""

    raw_attribute = item.get(name)
    if not isinstance(raw_attribute, Mapping):
        return None
    value = cast(Mapping[str, object], raw_attribute).get("S")
    return value if isinstance(value, str) else None


def _string_list_attribute(item: Mapping[str, object], name: str) -> list[str]:
    """Read one string list from a low-level DynamoDB list attribute."""

    raw_attribute = item.get(name)
    if not isinstance(raw_attribute, Mapping):
        return []
    raw_list = cast(Mapping[str, object], raw_attribute).get("L")
    if not isinstance(raw_list, list):
        return []
    values: list[str] = []
    for raw_entry in raw_list:
        if isinstance(raw_entry, Mapping):
            value = cast(Mapping[str, object], raw_entry).get("S")
            if isinstance(value, str):
                values.append(value)
    return values
