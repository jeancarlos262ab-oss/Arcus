"""Runtime configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

DEFAULT_AWS_REGION = "us-east-1"
DEFAULT_BEDROCK_MODEL_ID = "us.amazon.nova-2-lite-v1:0"
DEFAULT_MAX_OUTPUT_TOKENS = 1200
DEFAULT_MAX_PROMPT_BYTES = 60_000
DEFAULT_MAX_FINDINGS_PER_STAGE = 10
DEFAULT_MAX_FINDINGS_TOTAL = 10
DEFAULT_MAX_CHANGED_FILES = 50
DEFAULT_MAX_DIFF_BYTES = 524_288
DEFAULT_MAX_ENVELOPE_BYTES = 240_000
DEFAULT_MAX_AI_OPERATIONS_PER_RUN = 3


@dataclass(frozen=True, slots=True)
class Settings:
    """Immutable cost and payload limits shared by runtime adapters."""

    aws_region: str
    bedrock_model_id: str
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS
    max_prompt_bytes: int = DEFAULT_MAX_PROMPT_BYTES
    max_findings_per_stage: int = DEFAULT_MAX_FINDINGS_PER_STAGE
    max_findings_total: int = DEFAULT_MAX_FINDINGS_TOTAL
    max_changed_files: int = DEFAULT_MAX_CHANGED_FILES
    max_diff_bytes: int = DEFAULT_MAX_DIFF_BYTES
    max_envelope_bytes: int = DEFAULT_MAX_ENVELOPE_BYTES
    max_ai_operations_per_run: int = DEFAULT_MAX_AI_OPERATIONS_PER_RUN

    def __post_init__(self) -> None:
        """Reject settings that exceed shared contract or operation boundaries."""

        numeric_limits = {
            "max_output_tokens": self.max_output_tokens,
            "max_prompt_bytes": self.max_prompt_bytes,
            "max_findings_per_stage": self.max_findings_per_stage,
            "max_findings_total": self.max_findings_total,
            "max_changed_files": self.max_changed_files,
            "max_diff_bytes": self.max_diff_bytes,
            "max_envelope_bytes": self.max_envelope_bytes,
            "max_ai_operations_per_run": self.max_ai_operations_per_run,
        }
        if any(value < 1 for value in numeric_limits.values()):
            raise ValueError("all runtime limits must be at least 1")
        if self.max_findings_per_stage > 10 or self.max_findings_total > 10:
            raise ValueError(
                "finding limits cannot exceed the 10-item envelope contract"
            )
        if self.max_changed_files > 50:
            raise ValueError(
                "max_changed_files cannot exceed the 50-item envelope contract"
            )
        if self.max_envelope_bytes > 250_000:
            raise ValueError(
                "max_envelope_bytes cannot exceed the Step Functions safety limit"
            )
        if self.max_ai_operations_per_run > 3:
            raise ValueError(
                "max_ai_operations_per_run cannot exceed the three AI stages"
            )


def _read_setting(name: str, default: str) -> str:
    """Read one non-empty environment setting without exposing secrets."""

    value = os.getenv(name, default).strip()
    if not value:
        raise ValueError(f"{name} cannot be empty")
    return value


def _read_positive_int(name: str, default: int) -> int:
    """Read one strictly positive integer cost limit from the environment."""

    raw_value = os.getenv(name, str(default)).strip()
    try:
        value = int(raw_value)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error
    if value < 1:
        raise ValueError(f"{name} must be at least 1")
    return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load runtime settings once so every Lambda uses one validated snapshot."""

    return Settings(
        aws_region=_read_setting("AWS_REGION", DEFAULT_AWS_REGION),
        bedrock_model_id=_read_setting("BEDROCK_MODEL_ID", DEFAULT_BEDROCK_MODEL_ID),
        max_output_tokens=_read_positive_int(
            "MAX_OUTPUT_TOKENS", DEFAULT_MAX_OUTPUT_TOKENS
        ),
        max_prompt_bytes=_read_positive_int(
            "MAX_PROMPT_BYTES", DEFAULT_MAX_PROMPT_BYTES
        ),
        max_findings_per_stage=_read_positive_int(
            "MAX_FINDINGS_PER_STAGE", DEFAULT_MAX_FINDINGS_PER_STAGE
        ),
        max_findings_total=_read_positive_int(
            "MAX_FINDINGS_TOTAL", DEFAULT_MAX_FINDINGS_TOTAL
        ),
        max_changed_files=_read_positive_int(
            "MAX_CHANGED_FILES", DEFAULT_MAX_CHANGED_FILES
        ),
        max_diff_bytes=_read_positive_int("MAX_DIFF_BYTES", DEFAULT_MAX_DIFF_BYTES),
        max_envelope_bytes=_read_positive_int(
            "MAX_ENVELOPE_BYTES", DEFAULT_MAX_ENVELOPE_BYTES
        ),
        max_ai_operations_per_run=_read_positive_int(
            "MAX_AI_OPERATIONS_PER_RUN", DEFAULT_MAX_AI_OPERATIONS_PER_RUN
        ),
    )
