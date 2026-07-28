"""Lambda entrypoint for GitHub OAuth login and per-user dashboard state.

Separate from ``dashboard_api.py`` (shared API-key read access to review
history) and from the GitHub App used by the pipeline. This handler lets one
human log in with their own GitHub account, see their own repositories, and
save which of those repositories they want to watch in the dashboard.

Routes:
    GET  /auth/login     -> 302 redirect to GitHub's consent screen
    GET  /auth/callback  -> exchanges the OAuth code, sets the session cookie
    POST /auth/logout    -> clears the session cookie
    GET  /me             -> the logged-in user's identity
    GET  /me/repos       -> the logged-in user's own GitHub repositories
    GET  /me/watchlist   -> the logged-in user's saved repository selection
    PUT  /me/watchlist    -> replaces the logged-in user's repository selection
"""

from __future__ import annotations

import json
import logging
import os
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from time import time
from typing import Any, cast

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from arcus.auth import (
    GitHubOAuthClient,
    SessionError,
    SessionPayload,
    SessionSigner,
    build_authorize_url,
)
from arcus.errors import PermanentError
from arcus.secrets import CachedSecretProvider, SecretsManagerClient
from arcus.storage.users import UserProfile, UserStore

logger = logging.getLogger(__name__)

_SESSION_COOKIE = "arcus_session"
_STATE_COOKIE = "arcus_oauth_state"


@dataclass(frozen=True, slots=True)
class AuthApiSettings:
    """Validated runtime configuration for the GitHub login API."""

    review_table_name: str
    github_client_id: str
    github_client_secret_arn: str
    session_secret_arn: str
    dashboard_base_url: str
    redirect_uri: str
    secret_cache_ttl_seconds: int = 300
    session_ttl_seconds: int = 12 * 60 * 60

    def __post_init__(self) -> None:
        """Reject settings that would silently disable a hard limit."""

        if self.secret_cache_ttl_seconds < 1:
            raise ValueError("secret cache TTL must be at least 1 second")
        if self.session_ttl_seconds < 1:
            raise ValueError("session TTL must be at least 1 second")

    @classmethod
    def from_environment(cls) -> AuthApiSettings:
        """Load resource identifiers required to serve the login flow."""

        return cls(
            review_table_name=_required_environment("DDB_REVIEW_TABLE"),
            github_client_id=_required_environment("GITHUB_OAUTH_CLIENT_ID"),
            github_client_secret_arn=_required_environment(
                "GITHUB_OAUTH_CLIENT_SECRET_ARN"
            ),
            session_secret_arn=_required_environment("SESSION_SECRET_ARN"),
            dashboard_base_url=_required_environment("DASHBOARD_BASE_URL").rstrip("/"),
            redirect_uri=_required_environment("OAUTH_REDIRECT_URI"),
            secret_cache_ttl_seconds=_positive_int_environment(
                "SECRET_CACHE_TTL_SECONDS", 300
            ),
            session_ttl_seconds=_positive_int_environment(
                "SESSION_TTL_SECONDS", 12 * 60 * 60
            ),
        )


class AuthApiHandler:
    """Route the GitHub OAuth login flow and per-user watchlist reads/writes."""

    def __init__(
        self,
        *,
        settings: AuthApiSettings,
        oauth_client: GitHubOAuthClient,
        session_signer: SessionSigner,
        user_store: UserStore,
        clock: Any = time,
        state_factory: Any = lambda: secrets.token_urlsafe(24),
    ) -> None:
        """Create a handler with injectable boundaries for deterministic tests."""

        self._settings = settings
        self._oauth = oauth_client
        self._sessions = session_signer
        self._users = user_store
        self._clock = clock
        self._state_factory = state_factory

    def handle(self, event: Mapping[str, object]) -> dict[str, object]:
        """Route one bounded API Gateway request for the login flow."""

        method = _http_method(event)
        path = _request_path(event)
        try:
            if method == "GET" and path == "/auth/login":
                return self._start_login()
            if method == "GET" and path == "/auth/callback":
                return self._finish_login(event)
            if method == "POST" and path == "/auth/logout":
                return self._logout()
            if method == "GET" and path == "/me":
                return self._me(event)
            if method == "GET" and path == "/me/repos":
                return self._my_repos(event)
            if method == "GET" and path == "/me/watchlist":
                return self._get_watchlist(event)
            if method == "PUT" and path == "/me/watchlist":
                return self._put_watchlist(event)
        except _ClientRequestError as error:
            return _json_response(error.status_code, {"message": error.message})
        except (BotoCoreError, ClientError):
            logger.exception("auth_api_backend_failed", extra={"path": path})
            return _json_response(500, {"message": "unable to complete the request"})

        return _json_response(404, {"message": "not found"})

    def _start_login(self) -> dict[str, object]:
        """Redirect the browser to GitHub's own consent screen."""

        state = self._state_factory()
        authorize_url = build_authorize_url(
            self._settings.github_client_id,
            redirect_uri=self._settings.redirect_uri,
            state=state,
        )
        return {
            "statusCode": 302,
            "headers": {"location": authorize_url},
            "cookies": [_state_cookie(state, ttl_seconds=600)],
            "body": "",
        }

    def _finish_login(self, event: Mapping[str, object]) -> dict[str, object]:
        """Exchange the OAuth code, persist the user, and set the session cookie."""

        query = _query_params(event)
        code = query.get("code", "")
        returned_state = query.get("state", "")
        cookies = _cookies(event)
        expected_state = cookies.get(_STATE_COOKIE, "")
        if not expected_state or returned_state != expected_state:
            raise _ClientRequestError(400, "invalid or expired OAuth state")

        try:
            user_token = self._oauth.exchange_code_for_token(
                code, redirect_uri=self._settings.redirect_uri
            )
            github_user = self._oauth.fetch_authenticated_user(user_token)
        except PermanentError as error:
            logger.warning("oauth_login_failed", extra={"error_code": error.code})
            raise _ClientRequestError(
                400, "GitHub login could not be completed"
            ) from error

        now = int(self._clock())
        self._users.save_profile(
            UserProfile(
                github_user_id=github_user.id,
                github_login=github_user.login,
                github_user_token=user_token,
                avatar_url=github_user.avatar_url,
            ),
            now_epoch=now,
        )
        session_token = self._sessions.issue(
            SessionPayload(
                github_user_id=github_user.id, github_login=github_user.login
            )
        )
        return {
            "statusCode": 302,
            "headers": {"location": self._settings.dashboard_base_url},
            "cookies": [
                _session_cookie(
                    session_token, ttl_seconds=self._settings.session_ttl_seconds
                ),
                _clear_cookie(_STATE_COOKIE),
            ],
            "body": "",
        }

    def _logout(self) -> dict[str, object]:
        """Clear the session cookie; GitHub's own authorization is untouched."""

        return {
            "statusCode": 204,
            "headers": {},
            "cookies": [_clear_cookie(_SESSION_COOKIE)],
            "body": "",
        }

    def _me(self, event: Mapping[str, object]) -> dict[str, object]:
        """Return the logged-in user's identity."""

        session = self._require_session(event)
        return _json_response(
            200,
            {"github_user_id": session.github_user_id, "login": session.github_login},
        )

    def _my_repos(self, event: Mapping[str, object]) -> dict[str, object]:
        """Return the repositories the logged-in user can see on GitHub."""

        session = self._require_session(event)
        profile = self._users.get_profile(session.github_user_id)
        if profile is None:
            raise _ClientRequestError(401, "session is no longer valid")
        repositories = self._oauth.fetch_user_repositories(profile.github_user_token)
        return _json_response(
            200,
            {
                "repos": [
                    {"full_name": repo.full_name, "private": repo.private}
                    for repo in repositories
                ]
            },
        )

    def _get_watchlist(self, event: Mapping[str, object]) -> dict[str, object]:
        """Return the repositories the logged-in user chose to watch."""

        session = self._require_session(event)
        repos = self._users.get_watchlist(session.github_user_id)
        return _json_response(200, {"repos": repos})

    def _put_watchlist(self, event: Mapping[str, object]) -> dict[str, object]:
        """Replace the logged-in user's saved repository selection."""

        session = self._require_session(event)
        body = _json_body(event)
        raw_repos = body.get("repos")
        if not isinstance(raw_repos, list) or not all(
            isinstance(repo, str) for repo in raw_repos
        ):
            raise _ClientRequestError(400, "body must be {'repos': string[]}")
        try:
            saved = self._users.save_watchlist(
                session.github_user_id,
                cast(list[str], raw_repos),
                now_epoch=int(self._clock()),
            )
        except ValueError as error:
            raise _ClientRequestError(400, str(error)) from error
        return _json_response(200, {"repos": saved})

    def _require_session(self, event: Mapping[str, object]) -> SessionPayload:
        """Validate the session cookie or reject the request as unauthenticated."""

        token = _cookies(event).get(_SESSION_COOKIE, "")
        try:
            return self._sessions.verify(token)
        except SessionError as error:
            raise _ClientRequestError(401, "not logged in") from error


class _ClientRequestError(Exception):
    """A request could not be served because of caller-supplied input or state."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def _session_cookie(token: str, *, ttl_seconds: int) -> str:
    """Build the HttpOnly, cross-site session cookie set after login."""

    return (
        f"{_SESSION_COOKIE}={token}; Path=/; Max-Age={ttl_seconds}; "
        "HttpOnly; Secure; SameSite=None"
    )


def _state_cookie(state: str, *, ttl_seconds: int) -> str:
    """Build the short-lived CSRF state cookie used only during the OAuth hop."""

    return (
        f"{_STATE_COOKIE}={state}; Path=/; Max-Age={ttl_seconds}; "
        "HttpOnly; Secure; SameSite=None"
    )


def _clear_cookie(name: str) -> str:
    """Build a cookie header that immediately expires one named cookie."""

    return f"{name}=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=None"


def _http_method(event: Mapping[str, object]) -> str:
    """Read the HTTP method from an API Gateway HTTP API v2 event."""

    request_context = event.get("requestContext")
    if isinstance(request_context, Mapping):
        http = cast(Mapping[str, object], request_context).get("http")
        if isinstance(http, Mapping):
            method = cast(Mapping[str, object], http).get("method")
            if isinstance(method, str):
                return method.upper()
    return ""


def _request_path(event: Mapping[str, object]) -> str:
    """Read the normalised HTTP API v2 request path."""

    raw_path = event.get("rawPath")
    if isinstance(raw_path, str) and raw_path:
        return raw_path.rstrip("/") or "/"
    return "/"


def _query_params(event: Mapping[str, object]) -> dict[str, str]:
    """Read HTTP API v2 query-string parameters."""

    raw_params = event.get("queryStringParameters")
    if not isinstance(raw_params, Mapping):
        return {}
    typed_params = cast(Mapping[object, object], raw_params)
    return {
        key: value
        for key, value in typed_params.items()
        if isinstance(key, str) and isinstance(value, str)
    }


def _cookies(event: Mapping[str, object]) -> dict[str, str]:
    """Parse HTTP API v2's native ``cookies`` array into a name/value map."""

    raw_cookies = event.get("cookies")
    if not isinstance(raw_cookies, list):
        return {}
    parsed: dict[str, str] = {}
    for raw_cookie in raw_cookies:
        if not isinstance(raw_cookie, str) or "=" not in raw_cookie:
            continue
        name, _, value = raw_cookie.partition("=")
        parsed[name.strip()] = value.strip()
    return parsed


def _json_body(event: Mapping[str, object]) -> Mapping[str, object]:
    """Parse the request body as a JSON object, tolerating a missing body."""

    raw_body = event.get("body")
    if not isinstance(raw_body, str) or not raw_body.strip():
        return {}
    try:
        payload: object = json.loads(raw_body)
    except json.JSONDecodeError as error:
        raise _ClientRequestError(400, "request body must be valid JSON") from error
    if not isinstance(payload, Mapping):
        raise _ClientRequestError(400, "request body must be a JSON object")
    return cast(Mapping[str, object], payload)


def _json_response(status_code: int, body: Mapping[str, object]) -> dict[str, object]:
    """Create the small JSON response expected by API Gateway."""

    return {
        "statusCode": status_code,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body, separators=(",", ":")),
    }


def _required_environment(name: str) -> str:
    """Read one non-empty resource identifier from the Lambda environment."""

    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"{name} cannot be empty")
    return value


def _positive_int_environment(name: str, default: int) -> int:
    """Read one strictly positive integer setting from the Lambda environment."""

    raw_value = os.getenv(name, str(default)).strip()
    try:
        value = int(raw_value)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error
    if value < 1:
        raise ValueError(f"{name} must be at least 1")
    return value


def lambda_handler(event: Mapping[str, object], _context: object) -> dict[str, object]:
    """AWS Lambda entrypoint reusing clients and the secret cache when warm."""

    return _get_handler().handle(event)


@lru_cache(maxsize=1)
def _get_handler() -> AuthApiHandler:
    """Build one warm-process handler so AWS clients and secrets are reused."""

    settings = AuthApiSettings.from_environment()
    boto3_module = cast(Any, boto3)
    retry_config = Config(retries={"mode": "adaptive", "total_max_attempts": 3})
    dynamodb_client = boto3_module.client("dynamodb", config=retry_config)
    secrets_client = cast(SecretsManagerClient, boto3_module.client("secretsmanager"))

    client_secret_provider = CachedSecretProvider(
        secrets_client,
        settings.github_client_secret_arn,
        ttl_seconds=settings.secret_cache_ttl_seconds,
        field_names=("client_secret", "github_oauth_client_secret", "secret"),
    )
    session_secret_provider = CachedSecretProvider(
        secrets_client,
        settings.session_secret_arn,
        ttl_seconds=settings.secret_cache_ttl_seconds,
        field_names=("session_secret", "secret"),
    )
    return AuthApiHandler(
        settings=settings,
        oauth_client=GitHubOAuthClient(
            settings.github_client_id, client_secret_provider
        ),
        session_signer=SessionSigner(
            session_secret_provider.get(), ttl_seconds=settings.session_ttl_seconds
        ),
        user_store=UserStore(settings.review_table_name, client=dynamodb_client),
    )
