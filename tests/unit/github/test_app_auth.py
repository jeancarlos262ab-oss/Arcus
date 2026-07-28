"""Unit coverage for GitHub App JWT auth and per-repo installation checks."""

from __future__ import annotations

from collections.abc import Mapping
from urllib.error import HTTPError

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from arcus.errors import PermanentError
from arcus.github.app_auth import GitHubAppAuthenticator, HttpResponse
from arcus.secrets import CachedSecretProvider

_TEST_PRIVATE_KEY_PEM = (
    rsa.generate_private_key(public_exponent=65537, key_size=2048)
    .private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    .decode("ascii")
)


class StaticSecretClient:
    """Serve one fixed private key without any Secrets Manager I/O."""

    def get_secret_value(self, *, SecretId: str) -> Mapping[str, object]:  # noqa: N803
        return {"SecretString": _TEST_PRIVATE_KEY_PEM}


def _authenticator(transport: object) -> GitHubAppAuthenticator:
    provider = CachedSecretProvider(StaticSecretClient(), "test-key-arn")
    return GitHubAppAuthenticator(
        123456,
        provider,
        transport=transport,  # type: ignore[arg-type]
        clock=lambda: 1_700_000_000.0,
    )


class RecordingTransport:
    """Return one queued outcome (a response or a raised exception)."""

    def __init__(self, outcome: HttpResponse | Exception) -> None:
        self._outcome = outcome
        self.last_url: str | None = None

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        body: bytes | None = None,
        max_response_bytes: int = 1_048_576,
    ) -> HttpResponse:
        self.last_url = url
        assert headers["Authorization"].startswith("Bearer ")
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome


def test_installed_repository_returns_true() -> None:
    """A 200 from GitHub's installation-lookup endpoint means the App is installed."""

    transport = RecordingTransport(HttpResponse(status=200, headers={}, body=b"{}"))
    authenticator = _authenticator(transport)

    assert authenticator.is_installed_on_repository("octocat/hello-world") is True
    assert transport.last_url is not None
    assert transport.last_url.endswith("/repos/octocat/hello-world/installation")


def test_uninstalled_repository_returns_false() -> None:
    """A 404 from GitHub means the App is not installed on that repository."""

    not_found = PermanentError(
        "GitHub rejected the request with status 404",
        code="github_request_rejected",
    )
    transport = RecordingTransport(not_found)
    authenticator = _authenticator(transport)

    assert authenticator.is_installed_on_repository("octocat/private-repo") is False


def test_other_permanent_errors_are_not_swallowed() -> None:
    """A non-404 permanent failure must surface, not be treated as 'not installed'."""

    forbidden = PermanentError(
        "GitHub rejected the request with status 401",
        code="github_request_rejected",
    )
    transport = RecordingTransport(forbidden)
    authenticator = _authenticator(transport)

    with pytest.raises(PermanentError, match="401"):
        authenticator.is_installed_on_repository("octocat/hello-world")


def test_malformed_repo_name_is_rejected_before_any_request() -> None:
    """A repo name without exactly one 'owner/name' slash must fail fast."""

    transport = RecordingTransport(HTTPError("url", 404, "msg", {}, None))
    authenticator = _authenticator(transport)

    with pytest.raises(ValueError, match="owner/repo"):
        authenticator.is_installed_on_repository("not-a-repo")
    assert transport.last_url is None
