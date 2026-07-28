"""Unit coverage for the GitHub OAuth user-login adapter."""

from __future__ import annotations

import json
from collections.abc import Mapping

import pytest

from arcus.auth.oauth import GitHubOAuthClient, build_authorize_url
from arcus.errors import PermanentError
from arcus.github.app_auth import HttpResponse
from arcus.secrets import CachedSecretProvider


class StaticSecretClient:
    """Serve one fixed client secret without any Secrets Manager I/O."""

    def get_secret_value(self, *, SecretId: str) -> Mapping[str, object]:
        assert SecretId == "test-secret-arn"
        return {"SecretString": "oauth-client-secret"}


def _secret_provider() -> CachedSecretProvider:
    return CachedSecretProvider(StaticSecretClient(), "test-secret-arn")


class QueueTransport:
    """Serve bounded raw responses through the real OAuth client parser."""

    def __init__(self, responses: list[HttpResponse]) -> None:
        self._responses = responses
        self.requests: list[tuple[str, str, bytes | None]] = []

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        body: bytes | None = None,
        max_response_bytes: int = 1_048_576,
    ) -> HttpResponse:
        self.requests.append((method, url, body))
        if not self._responses:
            raise AssertionError("unexpected GitHub request")
        return self._responses.pop(0)


def _response(payload: object) -> HttpResponse:
    return HttpResponse(status=200, headers={}, body=json.dumps(payload).encode())


def test_authorize_url_includes_client_id_redirect_and_state() -> None:
    """The consent URL must carry every parameter GitHub requires to redirect back."""

    url = build_authorize_url(
        "client-123", redirect_uri="https://dashboard.test/auth/callback", state="xyz"
    )

    assert url.startswith("https://github.com/login/oauth/authorize?")
    assert "client_id=client-123" in url
    assert "state=xyz" in url
    assert "redirect_uri=https%3A%2F%2Fdashboard.test%2Fauth%2Fcallback" in url


def test_authorize_url_rejects_empty_client_id_or_state() -> None:
    """Construction-time validation must catch missing required parameters."""

    with pytest.raises(ValueError):
        build_authorize_url("", redirect_uri="https://x.test", state="s")
    with pytest.raises(ValueError):
        build_authorize_url("client", redirect_uri="https://x.test", state="")


def test_code_exchange_returns_the_access_token() -> None:
    """A successful token exchange must hand back the bare access token string."""

    transport = QueueTransport([_response({"access_token": "gho_abc123"})])
    client = GitHubOAuthClient("client-123", _secret_provider(), transport=transport)

    token = client.exchange_code_for_token(
        "one-time-code", redirect_uri="https://dashboard.test/auth/callback"
    )

    assert token == "gho_abc123"
    method, url, body = transport.requests[0]
    assert method == "POST"
    assert url == "https://github.com/login/oauth/access_token"
    assert body is not None
    assert b"client_secret=oauth-client-secret" in body


def test_code_exchange_surfaces_a_github_error_response() -> None:
    """A GitHub-reported OAuth error must fail loudly instead of returning empty."""

    transport = QueueTransport([_response({"error": "bad_verification_code"})])
    client = GitHubOAuthClient("client-123", _secret_provider(), transport=transport)

    with pytest.raises(PermanentError, match="bad_verification_code"):
        client.exchange_code_for_token("expired-code", redirect_uri="https://x.test")


def test_code_exchange_rejects_an_empty_code() -> None:
    """A missing authorization code must fail before any network call."""

    client = GitHubOAuthClient(
        "client-123", _secret_provider(), transport=QueueTransport([])
    )

    with pytest.raises(PermanentError, match="code"):
        client.exchange_code_for_token("", redirect_uri="https://x.test")


def test_fetch_authenticated_user_parses_identity() -> None:
    """The logged-in user's id and login must be read from GitHub's /user response."""

    transport = QueueTransport(
        [
            _response(
                {"id": 42, "login": "octocat", "avatar_url": "https://x.test/a.png"}
            )
        ]
    )
    client = GitHubOAuthClient("client-123", _secret_provider(), transport=transport)

    user = client.fetch_authenticated_user("user-token")

    assert user.id == 42
    assert user.login == "octocat"
    assert user.avatar_url == "https://x.test/a.png"
    assert transport.requests[0][1] == "https://api.github.com/user"


def test_fetch_user_repositories_paginates_and_stops_on_a_short_page() -> None:
    """Repository reads must follow GitHub pagination until a short page ends it."""

    first_page = [
        {"full_name": f"octocat/repo-{i}", "private": False} for i in range(100)
    ]
    second_page = [{"full_name": "octocat/repo-100", "private": True}]
    transport = QueueTransport([_response(first_page), _response(second_page)])
    client = GitHubOAuthClient("client-123", _secret_provider(), transport=transport)

    repos = client.fetch_user_repositories("user-token", max_repositories=500)

    assert len(repos) == 101
    assert repos[-1].full_name == "octocat/repo-100"
    assert repos[-1].private is True


def test_fetch_user_repositories_respects_the_max_cap() -> None:
    """A configured repository cap must bound the result even mid-page."""

    page = [{"full_name": f"octocat/repo-{i}", "private": False} for i in range(100)]
    transport = QueueTransport([_response(page)])
    client = GitHubOAuthClient("client-123", _secret_provider(), transport=transport)

    repos = client.fetch_user_repositories("user-token", max_repositories=5)

    assert len(repos) == 5
