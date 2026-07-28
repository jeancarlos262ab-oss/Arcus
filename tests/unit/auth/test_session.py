"""Unit coverage for signed, stateless dashboard sessions."""

from __future__ import annotations

import jwt
import pytest

from arcus.auth.session import SessionError, SessionPayload, SessionSigner


def test_issued_session_round_trips_the_identity() -> None:
    """A freshly issued token must verify back to the exact identity signed."""

    signer = SessionSigner("test-secret", clock=lambda: 1_700_000_000.0)
    token = signer.issue(SessionPayload(github_user_id=42, github_login="octocat"))

    payload = signer.verify(token)

    assert payload.github_user_id == 42
    assert payload.github_login == "octocat"


def test_expired_session_is_rejected() -> None:
    """A token past its TTL must fail verification, not silently succeed."""

    clock_value = [1_700_000_000.0]
    signer = SessionSigner("test-secret", ttl_seconds=60, clock=lambda: clock_value[0])
    token = signer.issue(SessionPayload(github_user_id=1, github_login="a"))

    clock_value[0] += 61

    with pytest.raises(SessionError):
        signer.verify(token)


def test_session_signed_with_a_different_secret_is_rejected() -> None:
    """A forged or rotated-secret token must never be treated as valid."""

    issuer = SessionSigner("secret-one", clock=lambda: 1_700_000_000.0)
    verifier = SessionSigner("secret-two", clock=lambda: 1_700_000_000.0)
    token = issuer.issue(SessionPayload(github_user_id=1, github_login="a"))

    with pytest.raises(SessionError):
        verifier.verify(token)


def test_empty_token_is_rejected() -> None:
    """An empty or missing cookie value must fail closed, not raise unrelated errors."""

    signer = SessionSigner("test-secret")

    with pytest.raises(SessionError):
        signer.verify("")


def test_token_missing_required_claims_is_rejected() -> None:
    """A token missing the login claim must be rejected even if otherwise signed correctly."""

    secret = "test-secret"
    malformed = jwt.encode(
        {
            "iss": "arcus-dashboard",
            "iat": 1_700_000_000,
            "exp": 1_700_100_000,
            "sub": "1",
        },
        secret,
        algorithm="HS256",
    )
    signer = SessionSigner(secret)

    with pytest.raises(SessionError):
        signer.verify(malformed)


def test_signer_rejects_invalid_construction_arguments() -> None:
    """Construction-time validation must catch empty secrets and non-positive TTLs."""

    with pytest.raises(ValueError, match="secret"):
        SessionSigner("")
    with pytest.raises(ValueError, match="TTL"):
        SessionSigner("secret", ttl_seconds=0)
