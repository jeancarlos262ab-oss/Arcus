"""Bedrock Converse client with retries and validated model-output parsing."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping
from time import perf_counter
from typing import Any, Protocol, cast

import boto3
from botocore.config import Config
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    HTTPClientError,
    IncompleteReadError,
)
from botocore.exceptions import ConnectionError as BotoConnectionError
from pydantic import TypeAdapter, ValidationError

from arcus.config import Settings, get_settings
from arcus.contracts import Finding, FixBatch
from arcus.errors import BedrockResponseError, PermanentError, TransientError
from arcus.retry import RetryPolicy, call_with_retries

logger = logging.getLogger(__name__)

_TRANSIENT_ERROR_CODES = frozenset(
    {
        "InternalServerException",
        "ModelNotReadyException",
        "ModelTimeoutException",
        "RequestTimeout",
        "ServiceUnavailable",
        "ServiceUnavailableException",
        "ThrottlingException",
        "TooManyRequestsException",
    }
)


class BedrockRuntimeClient(Protocol):
    """Minimal boto3 surface required by the Converse adapter."""

    def converse(
        self,
        *,
        modelId: str,
        messages: list[dict[str, object]],
        inferenceConfig: dict[str, int | float],
    ) -> Mapping[str, object]:
        """Send a user message to a Bedrock model."""
        ...


class BedrockClient:
    """Invoke Converse with one explicit retry owner and hard request limits."""

    def __init__(
        self,
        runtime_client: BedrockRuntimeClient | None = None,
        *,
        settings: Settings | None = None,
        model_id: str | None = None,
        max_attempts: int = 5,
        base_delay: float = 1.0,
        max_delay: float = 8.0,
        sleep: Callable[[float], None] | None = None,
        random_uniform: Callable[[float, float], float] | None = None,
    ) -> None:
        """Create a bounded client whose SDK layer never retries underneath Arcus.

        Args:
            runtime_client: Optional boto3-compatible client, primarily for tests.
            settings: Optional immutable runtime configuration.
            model_id: Optional override for the configured Bedrock model.
            max_attempts: Total Converse attempts owned by Arcus.
            base_delay: Initial retry delay upper bound in seconds.
            max_delay: Maximum retry delay upper bound in seconds.
            sleep: Optional injectable sleeper for deterministic tests.
            random_uniform: Optional injectable full-jitter function.
        """

        resolved_settings = settings or get_settings()
        selected_model_id = model_id or resolved_settings.bedrock_model_id
        if not selected_model_id.strip():
            raise PermanentError(
                "Bedrock model ID cannot be empty",
                code="bedrock_invalid_configuration",
            )

        if runtime_client is None:
            boto3_module = cast(Any, boto3)
            sdk_config = Config(
                connect_timeout=2,
                read_timeout=10,
                retries={"mode": "standard", "total_max_attempts": 1},
            )
            raw_runtime_client = boto3_module.client(
                "bedrock-runtime",
                region_name=resolved_settings.aws_region,
                config=sdk_config,
            )
            self._runtime_client = cast(BedrockRuntimeClient, raw_runtime_client)
        else:
            self._runtime_client = runtime_client

        self._model_id = selected_model_id
        self._max_output_tokens = resolved_settings.max_output_tokens
        self._max_prompt_bytes = resolved_settings.max_prompt_bytes
        self._max_findings_per_stage = resolved_settings.max_findings_per_stage
        self._retry_policy = RetryPolicy(
            max_attempts=max_attempts,
            base_delay=base_delay,
            max_delay=max_delay,
            sleep=sleep,
            random_uniform=random_uniform,
        )

    def invoke_model(
        self,
        prompt: str,
        *,
        model_id: str | None = None,
        max_tokens: int = 1200,
        temperature: float = 0.0,
    ) -> str:
        """Invoke Converse after enforcing prompt and output-token budgets.

        Args:
            prompt: User prompt sent to the model. It is never logged.
            model_id: Optional per-call model override.
            max_tokens: Maximum number of output tokens requested from the model.
            temperature: Sampling temperature sent to Converse.

        Returns:
            Concatenated text blocks from the assistant response.

        Raises:
            PermanentError: For invalid or over-budget arguments, non-retryable SDK
                errors, or an invalid Converse response shape.
            TransientError: If all Arcus-owned retry attempts fail transiently.
        """

        if not prompt.strip():
            raise PermanentError(
                "Bedrock prompt cannot be empty", code="bedrock_invalid_request"
            )
        prompt_bytes = len(prompt.encode("utf-8"))
        if prompt_bytes > self._max_prompt_bytes:
            raise PermanentError(
                f"Bedrock prompt exceeds {self._max_prompt_bytes} bytes",
                code="bedrock_prompt_too_large",
            )
        if max_tokens < 1 or max_tokens > self._max_output_tokens:
            raise PermanentError(
                f"max_tokens must be between 1 and {self._max_output_tokens}",
                code="bedrock_invalid_request",
            )
        if temperature < 0:
            raise PermanentError(
                "temperature cannot be negative",
                code="bedrock_invalid_request",
            )

        selected_model_id = model_id or self._model_id
        if not selected_model_id.strip():
            raise PermanentError(
                "Bedrock model ID cannot be empty",
                code="bedrock_invalid_request",
            )

        started_at = perf_counter()
        response = call_with_retries(
            self._converse_once,
            self._retry_policy,
            prompt,
            model_id=selected_model_id,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        text = extract_text(response)
        usage = _extract_usage(response)
        logger.info(
            "bedrock_converse_completed",
            extra={
                "model_id": selected_model_id,
                "latency_ms": round((perf_counter() - started_at) * 1000, 2),
                "input_tokens": usage[0],
                "output_tokens": usage[1],
            },
        )
        return text

    def parse_findings(self, text: str) -> list[Finding]:
        """Validate findings using the configured per-stage hard limit."""

        return parse_findings(text, max_findings=self._max_findings_per_stage)

    def parse_fix_batch(self, text: str) -> FixBatch:
        """Validate a bounded batch of fixes from one model invocation."""

        return parse_fix_batch(text)

    def _converse_once(
        self,
        prompt: str,
        *,
        model_id: str,
        max_tokens: int,
        temperature: float,
    ) -> Mapping[str, object]:
        """Perform one SDK call and translate provider exceptions."""

        try:
            return self._runtime_client.converse(
                modelId=model_id,
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                inferenceConfig={"maxTokens": max_tokens, "temperature": temperature},
            )
        except ClientError as error:
            error_code = _client_error_code(error)
            if error_code in _TRANSIENT_ERROR_CODES:
                raise TransientError(
                    "Bedrock request failed temporarily",
                    code="bedrock_transient",
                ) from error
            raise PermanentError(
                "Bedrock rejected the request",
                code=f"bedrock_{_normalise_error_code(error_code)}",
            ) from error
        except (BotoConnectionError, HTTPClientError, IncompleteReadError) as error:
            raise TransientError(
                "Bedrock transport failed temporarily",
                code="bedrock_transport_error",
            ) from error
        except BotoCoreError as error:
            raise PermanentError(
                "Bedrock SDK could not execute the request",
                code="bedrock_sdk_error",
            ) from error


def extract_text(response: Mapping[str, object]) -> str:
    """Validate a Converse response and return its non-empty text blocks."""

    output = _require_mapping(response.get("output"), "output")
    message = _require_mapping(output.get("message"), "output.message")
    content = message.get("content")
    if not isinstance(content, list):
        raise BedrockResponseError("Bedrock response content must be a list")

    content_blocks = cast(list[object], content)
    text_blocks: list[str] = []
    for index, block in enumerate(content_blocks):
        block_mapping = _require_mapping(block, f"output.message.content[{index}]")
        text = block_mapping.get("text")
        if text is not None and (not isinstance(text, str) or not text.strip()):
            raise BedrockResponseError(
                f"Bedrock response text block {index} must contain non-empty text"
            )
        if isinstance(text, str):
            text_blocks.append(text)

    if not text_blocks:
        raise BedrockResponseError("Bedrock response did not contain a text block")
    return "\n".join(text_blocks)


def parse_json_response(text: str) -> object:
    """Parse JSON emitted by a model, accepting a conventional Markdown fence."""

    cleaned = _strip_code_fence(text.strip())
    if not cleaned:
        raise BedrockResponseError("Bedrock response text is empty")
    try:
        parsed: object = json.loads(cleaned)
    except json.JSONDecodeError as error:
        raise BedrockResponseError("Bedrock response was not valid JSON") from error
    if isinstance(parsed, dict):
        return cast(dict[str, object], parsed)
    if isinstance(parsed, list):
        return cast(list[object], parsed)
    raise BedrockResponseError("Bedrock response JSON must be an object or array")


def parse_findings(text: str, *, max_findings: int = 10) -> list[Finding]:
    """Parse findings and reject responses above the per-stage cost limit."""

    if max_findings < 1:
        raise ValueError("max_findings must be at least 1")
    parsed = parse_json_response(text)
    findings_payload: object = parsed
    if isinstance(parsed, Mapping):
        parsed_mapping = cast(Mapping[str, object], parsed)
        if "findings" not in parsed_mapping:
            raise BedrockResponseError(
                "Bedrock findings response is missing 'findings'"
            )
        findings_payload = parsed_mapping["findings"]

    try:
        findings = TypeAdapter(list[Finding]).validate_python(findings_payload)
    except ValidationError as error:
        raise BedrockResponseError(
            "Bedrock findings response failed contract validation"
        ) from error
    if len(findings) > max_findings:
        raise BedrockResponseError(
            f"Bedrock findings response exceeds the limit of {max_findings}"
        )
    return findings


def parse_findings_response(
    response: Mapping[str, object], *, max_findings: int = 10
) -> list[Finding]:
    """Extract, parse, and validate findings directly from a Converse response."""

    return parse_findings(extract_text(response), max_findings=max_findings)


def parse_fix_batch(text: str) -> FixBatch:
    """Parse and validate one model-generated batch of fix assignments."""

    parsed = parse_json_response(text)
    try:
        return FixBatch.model_validate(parsed)
    except ValidationError as error:
        raise BedrockResponseError(
            "Bedrock fix response failed contract validation"
        ) from error


def _require_mapping(value: object, path: str) -> Mapping[str, object]:
    """Return a mapping value or raise a path-specific response error."""

    if not isinstance(value, Mapping):
        raise BedrockResponseError(f"Bedrock response field '{path}' must be an object")
    return cast(Mapping[str, object], value)


def _strip_code_fence(text: str) -> str:
    """Remove one complete JSON Markdown fence without altering valid JSON."""

    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if len(lines) < 3 or not lines[-1].strip().startswith("```"):
        return text
    return "\n".join(lines[1:-1]).strip()


def _client_error_code(error: ClientError) -> str:
    """Read a stable provider error code from a botocore ClientError."""

    response = cast(Mapping[str, object], error.response)
    error_data = response.get("Error", {})
    if isinstance(error_data, Mapping):
        error_mapping = cast(Mapping[str, object], error_data)
        code = error_mapping.get("Code")
        if isinstance(code, str) and code:
            return code
    return "unknown"


def _normalise_error_code(error_code: str) -> str:
    """Make a provider code safe and readable as part of an Arcus error code."""

    return (
        "".join(
            character.lower() if character.isalnum() else "_"
            for character in error_code
        ).strip("_")
        or "unknown"
    )


def _extract_usage(response: Mapping[str, object]) -> tuple[int | None, int | None]:
    """Read token counts for metrics while avoiding prompt or response logging."""

    usage = response.get("usage")
    if not isinstance(usage, Mapping):
        return None, None
    usage_mapping = cast(Mapping[str, object], usage)
    input_tokens = usage_mapping.get("inputTokens")
    output_tokens = usage_mapping.get("outputTokens")
    return (
        input_tokens if isinstance(input_tokens, int) else None,
        output_tokens if isinstance(output_tokens, int) else None,
    )
