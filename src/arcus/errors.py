"""Typed exceptions used at Arcus service boundaries."""

from __future__ import annotations


class ArcusError(Exception):
    """Base exception carrying a stable error code for logs and orchestration."""

    def __init__(self, message: str, *, code: str = "arcus_error") -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class TransientError(ArcusError):
    """An operation failed temporarily and may succeed when retried."""


class PermanentError(ArcusError):
    """An operation cannot succeed by retrying the same request."""


class AgentError(ArcusError):
    """An agent could not complete its work but the pipeline may continue."""


class BedrockResponseError(PermanentError):
    """Bedrock returned a response that does not satisfy the expected shape."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="bedrock_invalid_response")
