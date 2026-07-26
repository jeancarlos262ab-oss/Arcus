"""Dependency-free Lambda stub used to exercise the Arcus state machine."""

from __future__ import annotations

import json
import logging
import os

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


def _pr_id(event: dict[str, object]) -> str:
    """Build a non-sensitive PR identifier for the temporary structured log."""

    pr = event.get("pr")
    if not isinstance(pr, dict):
        return "unknown"

    repo = pr.get("repo_full_name", "unknown")
    number = pr.get("pr_number", "unknown")
    return f"{repo}#{number}"


def lambda_handler(event: dict[str, object], _context: object) -> dict[str, object]:
    """Return the complete input envelope unchanged while real stages are developed.

    The shared no-op handler keeps every stage independently deployable without adding
    runtime dependencies or mutating another agent's section of the envelope.

    Args:
        event: Complete PipelineEnvelope serialized as JSON by Step Functions.
        _context: AWS Lambda invocation context, unused by this temporary handler.

    Returns:
        The exact envelope received from the previous pipeline state.
    """

    stage = os.getenv("ARCUS_PIPELINE_STAGE", "unknown")
    log_record = {
        "message": "pipeline_stub_invoked",
        "pipeline_run_id": event.get("pipeline_run_id", "unknown"),
        "agent": stage,
        "pr_id": _pr_id(event),
    }
    _LOGGER.info(json.dumps(log_record, separators=(",", ":"), default=str))
    return event
