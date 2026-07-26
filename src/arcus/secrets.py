"""Small in-process Secrets Manager cache for warm Lambda environments."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from threading import Lock
from time import monotonic
from typing import Protocol, cast


class SecretsManagerClient(Protocol):
    """Minimal Secrets Manager interface used by cached secret providers."""

    def get_secret_value(self, *, SecretId: str) -> Mapping[str, object]:
        """Read a configured secret value."""
        ...


class CachedSecretProvider:
    """Cache a parsed secret for a bounded period inside one warm process."""

    def __init__(
        self,
        client: SecretsManagerClient,
        secret_arn: str,
        *,
        ttl_seconds: int = 300,
        field_names: tuple[str, ...] = (
            "webhook_secret",
            "github_webhook_secret",
            "secret",
        ),
        clock: Callable[[], float] = monotonic,
    ) -> None:
        """Create a thread-safe provider that tolerates periodic secret rotation."""

        if ttl_seconds < 1:
            raise ValueError("secret cache TTL must be at least 1 second")
        self._client = client
        self._secret_arn = secret_arn
        self._ttl_seconds = ttl_seconds
        self._field_names = field_names
        self._clock = clock
        self._lock = Lock()
        self._cached_value: str | None = None
        self._expires_at = 0.0

    def get(self) -> str:
        """Return the cached value or refresh it once after expiry."""

        now = self._clock()
        if self._cached_value is not None and now < self._expires_at:
            return self._cached_value
        with self._lock:
            now = self._clock()
            if self._cached_value is not None and now < self._expires_at:
                return self._cached_value
            value = _parse_secret_response(
                self._client.get_secret_value(SecretId=self._secret_arn),
                self._field_names,
            )
            self._cached_value = value
            self._expires_at = now + self._ttl_seconds
            return value


def _parse_secret_response(
    response: Mapping[str, object], field_names: tuple[str, ...]
) -> str:
    """Read a non-empty raw or JSON-wrapped secret without logging it."""

    secret_string = response.get("SecretString")
    if isinstance(secret_string, str) and secret_string:
        try:
            raw_parsed: object = json.loads(secret_string)
        except json.JSONDecodeError:
            return secret_string
        if isinstance(raw_parsed, Mapping):
            parsed = cast(Mapping[str, object], raw_parsed)
            for field_name in field_names:
                value = parsed.get(field_name)
                if isinstance(value, str) and value:
                    return value
        raise ValueError("configured secret JSON has no supported field")

    secret_binary = response.get("SecretBinary")
    if isinstance(secret_binary, bytes) and secret_binary:
        return secret_binary.decode("utf-8")
    raise ValueError("configured secret is empty")
