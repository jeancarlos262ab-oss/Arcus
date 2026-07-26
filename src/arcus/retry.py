"""Retry helpers for transient service failures."""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from functools import wraps

from arcus.errors import TransientError

Sleep = Callable[[float], None]
Uniform = Callable[[float, float], float]


def _validate_policy(max_attempts: int, base_delay: float, max_delay: float) -> None:
    """Reject retry settings that would make the retry loop ambiguous."""

    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")
    if base_delay < 0:
        raise ValueError("base_delay cannot be negative")
    if max_delay < 0:
        raise ValueError("max_delay cannot be negative")


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Exponential-backoff policy shared by synchronous service adapters."""

    max_attempts: int = 5
    base_delay: float = 2.0
    max_delay: float = 30.0
    retry_exceptions: tuple[type[Exception], ...] = (TransientError,)
    sleep: Sleep | None = None
    random_uniform: Uniform | None = None

    def __post_init__(self) -> None:
        """Validate the policy when it is created rather than during an I/O call."""

        _validate_policy(self.max_attempts, self.base_delay, self.max_delay)


def call_with_retries[**P, R](
    function: Callable[P, R],
    policy: RetryPolicy,
    /,
    *args: P.args,
    **kwargs: P.kwargs,
) -> R:
    """Call a function again when it raises a configured transient exception.

    The delay uses exponential growth capped at ``max_delay`` and full jitter. The
    number of attempts includes the first call, which keeps the behavior predictable
    for service adapters and unit tests.

    Args:
        function: Callable that may raise one of the policy's retry exceptions.
        policy: Validated retry settings.
        *args: Positional arguments passed to ``function``.
        **kwargs: Keyword arguments passed to ``function``.

    Returns:
        The result returned by ``function``.

    Raises:
        Exception: The last exception from ``function``, or any non-retryable
            exception, is propagated unchanged.
    """

    sleeper = policy.sleep or time.sleep
    jitter = policy.random_uniform or random.uniform

    for attempt in range(1, policy.max_attempts + 1):
        try:
            return function(*args, **kwargs)
        except policy.retry_exceptions:
            if attempt == policy.max_attempts:
                raise
            delay_ceiling = min(
                policy.max_delay, policy.base_delay * (2 ** (attempt - 1))
            )
            if delay_ceiling > 0:
                sleeper(jitter(0.0, delay_ceiling))

    raise RuntimeError("retry loop exited without returning or raising")


def with_retries[**P, R](
    *,
    max_attempts: int = 5,
    base_delay: float = 2.0,
    max_delay: float = 30.0,
    retry_exceptions: tuple[type[Exception], ...] = (TransientError,),
    sleep: Sleep | None = None,
    random_uniform: Uniform | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorate a synchronous I/O function with transient retries.

    The decorator is intentionally narrow: callers must translate SDK-specific
    exceptions into ``TransientError`` or another explicitly configured type first.
    """

    policy = RetryPolicy(
        max_attempts=max_attempts,
        base_delay=base_delay,
        max_delay=max_delay,
        retry_exceptions=retry_exceptions,
        sleep=sleep,
        random_uniform=random_uniform,
    )

    def decorator(function: Callable[P, R]) -> Callable[P, R]:
        @wraps(function)
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
            return call_with_retries(function, policy, *args, **kwargs)

        return wrapped

    return decorator
