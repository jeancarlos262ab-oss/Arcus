"""GitHub App JWT and installation-token authentication."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from time import sleep, time
from typing import Any, Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

import jwt

from arcus.errors import PermanentError, TransientError
from arcus.secrets import CachedSecretProvider


@dataclass(frozen=True, slots=True)
class HttpResponse:
    """Bounded raw HTTP response returned by the GitHub transport."""

    status: int
    headers: Mapping[str, str]
    body: bytes


class HttpTransport(Protocol):
    """Mockable HTTP boundary shared by GitHub auth and API clients."""

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        body: bytes | None = None,
        max_response_bytes: int = 1_048_576,
    ) -> HttpResponse:
        """Execute one bounded GitHub request with provider-level retries."""
        ...


class _SafeRedirectHandler(HTTPRedirectHandler):
    """Allow bounded HTTPS redirects without forwarding cross-origin secrets."""

    max_redirections = 5

    def redirect_request(
        self,
        req: Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> Request | None:
        """Strip credentials across origins and reject plaintext redirect targets."""

        target = urlsplit(newurl)
        if target.scheme.lower() != "https":
            raise HTTPError(
                newurl,
                code,
                "GitHub redirect target must use HTTPS",
                headers,
                fp,
            )
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is None:
            return None
        source = urlsplit(req.full_url)
        if (source.scheme.lower(), source.netloc.lower()) != (
            target.scheme.lower(),
            target.netloc.lower(),
        ):
            redirected.remove_header("Authorization")
            redirected.remove_header("Cookie")
        return redirected


class UrlLibTransport:
    """Small GitHub transport with at most three Retry-After-aware attempts."""

    def __init__(
        self,
        *,
        max_attempts: int = 3,
        timeout_seconds: float = 5.0,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        """Create a transport with one explicit retry owner."""

        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self._max_attempts = max_attempts
        self._timeout_seconds = timeout_seconds
        self._sleep = sleeper
        self._opener = build_opener(_SafeRedirectHandler())

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        body: bytes | None = None,
        max_response_bytes: int = 1_048_576,
    ) -> HttpResponse:
        """Execute one request while respecting GitHub throttling responses."""

        for attempt in range(1, self._max_attempts + 1):
            request = Request(
                url,
                data=body,
                headers=dict(headers),
                method=method,
            )
            try:
                raw_response = self._opener.open(
                    request,
                    timeout=self._timeout_seconds,
                )
                with raw_response as response:
                    response_body = cast(bytes, response.read(max_response_bytes))
                    response_headers = {
                        str(key): str(value) for key, value in response.headers.items()
                    }
                    return HttpResponse(
                        status=int(response.status),
                        headers=response_headers,
                        body=response_body,
                    )
            except HTTPError as error:
                if (
                    error.code in {403, 429, 500, 502, 503, 504}
                    and attempt < self._max_attempts
                ):
                    retry_headers = {
                        str(key): str(value) for key, value in error.headers.items()
                    }
                    self._sleep(_retry_delay(retry_headers, attempt))
                    continue
                if error.code >= 500 or error.code in {403, 429}:
                    raise TransientError(
                        "GitHub request failed after retries",
                        code="github_transient",
                    ) from error
                raise PermanentError(
                    f"GitHub rejected the request with status {error.code}",
                    code="github_request_rejected",
                ) from error
            except URLError as error:
                if attempt < self._max_attempts:
                    self._sleep(float(attempt))
                    continue
                raise TransientError(
                    "GitHub transport failed after retries",
                    code="github_transport_error",
                ) from error

        raise RuntimeError("GitHub retry loop exited unexpectedly")


class GitHubAppAuthenticator:
    """Exchange a short-lived GitHub App JWT for installation tokens."""

    def __init__(
        self,
        app_id: int,
        private_key_provider: CachedSecretProvider,
        *,
        api_base_url: str = "https://api.github.com",
        transport: HttpTransport | None = None,
        clock: Callable[[], float] = time,
    ) -> None:
        """Create an authenticator without storing private keys in configuration."""

        if app_id < 1:
            raise ValueError("GitHub App ID must be positive")
        self._app_id = app_id
        self._private_key_provider = private_key_provider
        self._api_base_url = api_base_url.rstrip("/")
        self._transport = transport or UrlLibTransport()
        self._clock = clock
        self._cached_tokens: dict[int, tuple[str, float]] = {}

    def get_installation_token(self, installation_id: int) -> str:
        """Return a cached token or perform one authenticated token exchange."""

        now = self._clock()
        cached = self._cached_tokens.get(installation_id)
        if cached is not None and now < cached[1]:
            return cached[0]

        app_jwt = jwt.encode(
            {
                "iat": int(now) - 60,
                "exp": int(now) + 540,
                "iss": str(self._app_id),
            },
            self._private_key_provider.get(),
            algorithm="RS256",
        )
        response = self._transport.request(
            "POST",
            f"{self._api_base_url}/app/installations/{installation_id}/access_tokens",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {app_jwt}",
                "User-Agent": "arcus-pr-reviewer",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
            },
            body=b"{}",
        )
        payload = _json_object(response.body)
        token = payload.get("token")
        if not isinstance(token, str) or not token:
            raise PermanentError(
                "GitHub token response was malformed",
                code="github_invalid_token_response",
            )
        self._cached_tokens[installation_id] = (token, now + 50 * 60)
        return token


def _json_object(body: bytes) -> Mapping[str, object]:
    """Parse one untrusted GitHub JSON object."""

    payload: object = json.loads(body.decode("utf-8"))
    if not isinstance(payload, Mapping):
        raise PermanentError(
            "GitHub response must be an object",
            code="github_invalid_response",
        )
    return cast(Mapping[str, object], payload)


def _retry_delay(headers: Mapping[str, str], attempt: int) -> float:
    """Respect Retry-After while bounding malformed provider values."""

    raw_value = headers.get("Retry-After")
    if raw_value is not None:
        try:
            return min(3.0, max(0.0, float(raw_value)))
        except ValueError:
            pass
    return min(3.0, float(2 ** (attempt - 1)))
