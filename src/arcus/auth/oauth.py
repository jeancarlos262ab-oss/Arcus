"""GitHub OAuth login: authorization URL, code exchange, and user reads.

This is deliberately separate from ``arcus.github.app_auth``: that module
authenticates as the GitHub App itself (installation tokens, used by the
review pipeline). This module authenticates as one human GitHub *user*
(OAuth user-to-server tokens), used only so the dashboard can show that
person their own repositories. Neither module can act on the other's behalf.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast
from urllib.parse import urlencode

from arcus.errors import PermanentError
from arcus.github.app_auth import HttpTransport, UrlLibTransport
from arcus.secrets import CachedSecretProvider

_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
_TOKEN_URL = "https://github.com/login/oauth/access_token"
_API_BASE_URL = "https://api.github.com"
_SCOPE = "read:user repo"


@dataclass(frozen=True, slots=True)
class GitHubUser:
    """The minimal identity read back after a successful OAuth login."""

    id: int
    login: str
    avatar_url: str | None


@dataclass(frozen=True, slots=True)
class GitHubRepository:
    """One repository the logged-in user can see, as shown in the dashboard."""

    full_name: str
    private: bool


def build_authorize_url(client_id: str, *, redirect_uri: str, state: str) -> str:
    """Build the GitHub consent-screen URL that starts the login flow.

    Args:
        client_id: Public OAuth App client ID (not a secret).
        redirect_uri: Must exactly match a callback URL registered on the
            OAuth App, or GitHub rejects the request.
        state: Opaque, unguessable value round-tripped through GitHub and
            checked on callback to prevent cross-site request forgery.
    """

    if not client_id.strip():
        raise ValueError("client_id cannot be empty")
    if not state.strip():
        raise ValueError("state cannot be empty")
    query = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": _SCOPE,
            "state": state,
        }
    )
    return f"{_AUTHORIZE_URL}?{query}"


class GitHubOAuthClient:
    """Exchange one authorization code for a user token, then read identity."""

    def __init__(
        self,
        client_id: str,
        client_secret_provider: CachedSecretProvider,
        *,
        transport: HttpTransport | None = None,
    ) -> None:
        """Create a client that never persists the OAuth client secret itself."""

        if not client_id.strip():
            raise ValueError("client_id cannot be empty")
        self._client_id = client_id
        self._client_secret_provider = client_secret_provider
        self._transport = transport or UrlLibTransport()

    def exchange_code_for_token(self, code: str, *, redirect_uri: str) -> str:
        """Exchange a one-time authorization code for a user access token."""

        if not code.strip():
            raise PermanentError(
                "OAuth callback is missing the authorization code",
                code="oauth_missing_code",
            )
        body = urlencode(
            {
                "client_id": self._client_id,
                "client_secret": self._client_secret_provider.get(),
                "code": code,
                "redirect_uri": redirect_uri,
            }
        ).encode()
        response = self._transport.request(
            "POST",
            _TOKEN_URL,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "arcus-dashboard",
            },
            body=body,
        )
        payload = _json_object(response.body)
        error = payload.get("error")
        if isinstance(error, str) and error:
            raise PermanentError(
                f"GitHub rejected the OAuth code exchange: {error}",
                code="oauth_exchange_rejected",
            )
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise PermanentError(
                "GitHub OAuth response omitted access_token",
                code="oauth_invalid_response",
            )
        return token

    def fetch_authenticated_user(self, user_token: str) -> GitHubUser:
        """Read the logged-in user's own public identity."""

        response = self._transport.request(
            "GET", f"{_API_BASE_URL}/user", headers=_user_headers(user_token)
        )
        payload = _json_object(response.body)
        user_id = payload.get("id")
        login = payload.get("login")
        avatar_url = payload.get("avatar_url")
        if not isinstance(user_id, int) or not isinstance(login, str) or not login:
            raise PermanentError(
                "GitHub /user response was malformed",
                code="oauth_invalid_response",
            )
        return GitHubUser(
            id=user_id,
            login=login,
            avatar_url=avatar_url if isinstance(avatar_url, str) else None,
        )

    def fetch_user_repositories(
        self, user_token: str, *, max_repositories: int = 200
    ) -> list[GitHubRepository]:
        """Read repositories the logged-in user can see, most recently used first."""

        if max_repositories < 1:
            raise ValueError("max_repositories must be at least 1")
        repositories: list[GitHubRepository] = []
        page = 1
        while len(repositories) < max_repositories:
            response = self._transport.request(
                "GET",
                f"{_API_BASE_URL}/user/repos"
                f"?per_page=100&page={page}&sort=updated&affiliation=owner,collaborator",
                headers=_user_headers(user_token),
            )
            raw_items = _json_array(response.body)
            for raw_item in raw_items:
                if len(repositories) >= max_repositories:
                    break
                if not isinstance(raw_item, Mapping):
                    continue
                item = cast(Mapping[str, object], raw_item)
                full_name = item.get("full_name")
                private = item.get("private")
                if isinstance(full_name, str) and full_name:
                    repositories.append(
                        GitHubRepository(
                            full_name=full_name,
                            private=bool(private) if private is not None else False,
                        )
                    )
            if len(raw_items) < 100:
                break
            page += 1
        return repositories


def _user_headers(user_token: str) -> dict[str, str]:
    """Build the standard headers for a user-to-server GitHub API call."""

    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {user_token}",
        "User-Agent": "arcus-dashboard",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _json_object(body: bytes) -> Mapping[str, object]:
    """Parse one untrusted GitHub JSON object."""

    payload: object = json.loads(body.decode("utf-8"))
    if not isinstance(payload, Mapping):
        raise PermanentError(
            "GitHub response must be an object", code="oauth_invalid_response"
        )
    return cast(Mapping[str, object], payload)


def _json_array(body: bytes) -> list[object]:
    """Parse one untrusted GitHub JSON array."""

    payload: object = json.loads(body.decode("utf-8"))
    if not isinstance(payload, list):
        raise PermanentError(
            "GitHub response must be an array", code="oauth_invalid_response"
        )
    return cast(list[object], payload)
