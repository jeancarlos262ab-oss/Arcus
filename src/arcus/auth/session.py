"""Signed, stateless dashboard sessions carried in an HttpOnly cookie.

A session identifies one logged-in GitHub user (their numeric account ID and
login) without storing anything server-side beyond what DynamoDB already
holds per user (see ``arcus.storage.users``). The signature prevents a
browser from forging or tampering with another user's identity; it is not a
place to store secrets, since JWTs are only base64-encoded, not encrypted.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from time import time

import jwt

_ALGORITHM = "HS256"
_ISSUER = "arcus-dashboard"


class SessionError(Exception):
    """A session cookie was missing, malformed, expired, or forged."""


@dataclass(frozen=True, slots=True)
class SessionPayload:
    """The identity carried by one signed dashboard session."""

    github_user_id: int
    github_login: str


class SessionSigner:
    """Issue and verify short-lived HS256 session tokens for the dashboard."""

    def __init__(
        self,
        secret: str,
        *,
        ttl_seconds: int = 12 * 60 * 60,
        clock: Callable[[], float] = time,
    ) -> None:
        """Create a signer bound to one rotating session secret.

        Args:
            secret: Shared HMAC secret read from Secrets Manager. Never a
                per-user value; rotating it invalidates every open session.
            ttl_seconds: How long an issued session remains valid.
            clock: Injectable time source for deterministic tests.
        """

        if not secret.strip():
            raise ValueError("session secret cannot be empty")
        if ttl_seconds < 1:
            raise ValueError("session TTL must be at least 1 second")
        self._secret = secret
        self._ttl_seconds = ttl_seconds
        self._clock = clock

    def issue(self, payload: SessionPayload) -> str:
        """Sign one session token for a successfully authenticated user."""

        now = datetime.fromtimestamp(self._clock(), tz=UTC)
        claims = {
            "iss": _ISSUER,
            "iat": now,
            "exp": now + timedelta(seconds=self._ttl_seconds),
            "sub": str(payload.github_user_id),
            "login": payload.github_login,
        }
        return jwt.encode(claims, self._secret, algorithm=_ALGORITHM)

    def verify(self, token: str) -> SessionPayload:
        """Validate a session token and return the identity it carries."""

        if not token.strip():
            raise SessionError("session token is empty")
        try:
            claims = jwt.decode(
                token,
                self._secret,
                algorithms=[_ALGORITHM],
                issuer=_ISSUER,
                # Expiry is checked manually below against the injected clock
                # (tests and warm Lambdas must not depend on wall-clock time).
                options={
                    "require": ["exp", "iat", "sub", "login"],
                    "verify_exp": False,
                },
            )
        except jwt.PyJWTError as error:
            raise SessionError("session token is invalid or expired") from error

        expires_at = claims.get("exp")
        if not isinstance(expires_at, int | float) or self._clock() >= expires_at:
            raise SessionError("session token is invalid or expired")

        subject = claims.get("sub")
        login = claims.get("login")
        if not isinstance(subject, str) or not subject.isdigit():
            raise SessionError("session token has an invalid subject")
        if not isinstance(login, str) or not login:
            raise SessionError("session token has an invalid login")
        return SessionPayload(github_user_id=int(subject), github_login=login)
