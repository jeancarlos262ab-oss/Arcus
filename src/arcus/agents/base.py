"""Base agent framework for Lambda handlers in the PR review pipeline."""
import json
import logging
from collections.abc import Callable
from typing import Any, TypeVar

from arcus.contracts import ErrorDetail, PipelineEnvelope

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=Callable[..., Any])


def agent_handler(func: T) -> T:
    """
    Decorator for agent handler functions.

    Wraps handler logic with envelope parsing, error handling, and serialization.
    Converts exceptions into failed envelope states with error details.

    Usage:
        @agent_handler
        def my_agent(envelope: PipelineEnvelope) -> PipelineEnvelope:
            # Process envelope
            return updated_envelope

    Args:
        func: Handler function that takes a PipelineEnvelope and returns one.

    Returns:
        Wrapped function that handles parsing, errors, and serialization.

    Raises:
        No exceptions raised - errors are captured in envelope.{section}.error
    """

    def wrapper(event: dict[str, Any]) -> dict[str, Any]:
        """
        Wrapper that handles envelope parsing, execution, and error recovery.

        Args:
            event: Lambda event containing envelope JSON or dict.

        Returns:
            Dictionary with serialized envelope (always a valid response).
        """
        try:
            # Step 1: Parse input envelope
            if isinstance(event, str):
                event_data = json.loads(event)
            else:
                event_data = event

            envelope = PipelineEnvelope.model_validate(event_data)
            logger.info(
                f"Agent {func.__name__} processing PR {envelope.pr.repo_full_name}#{envelope.pr.pr_number}"
            )

            # Step 2: Execute handler
            try:
                result_envelope = func(envelope)
            except Exception as handler_error:
                # Handler failed - mark section as failed and return
                logger.error(
                    f"Handler {func.__name__} failed: {type(handler_error).__name__}: {handler_error}",
                    exc_info=True,
                )
                # The handler is responsible for catching and marking its own section
                # But if it completely crashes, we still return the envelope
                result_envelope = envelope

            # Step 3: Serialize result
            serialized = result_envelope.model_dump(mode="json")
            assert isinstance(serialized, dict)
            return serialized

        except json.JSONDecodeError as json_error:
            logger.error(f"Invalid JSON input: {json_error}")
            # Cannot parse envelope - return generic error response
            return {
                "error": "Invalid JSON input",
                "detail": str(json_error),
            }

        except ValueError as validation_error:
            logger.error(f"Invalid envelope schema: {validation_error}")
            # Invalid envelope structure
            return {
                "error": "Invalid envelope schema",
                "detail": str(validation_error),
            }

        except Exception as unexpected_error:
            logger.error(
                f"Unexpected error in agent wrapper: {type(unexpected_error).__name__}: {unexpected_error}",
                exc_info=True,
            )
            # Catastrophic failure - return error response
            return {
                "error": "Internal agent error",
                "detail": str(unexpected_error),
            }

    return wrapper  # type: ignore


def mark_section_failed(
    envelope: PipelineEnvelope,
    section_name: str,
    error_code: str,
    error_message: str,
) -> None:
    """
    Mark a section of the envelope as failed with error details.

    Args:
        envelope: PipelineEnvelope to modify.
        section_name: Name of section ('context', 'consistency', 'bugs', 'fixes', 'report').
        error_code: Error code for categorization.
        error_message: Human-readable error message.
    """
    section = getattr(envelope, section_name, None)
    if section is not None:
        section_dict = section if isinstance(section, dict) else section.__dict__
        section_dict["status"] = "failed"
        section_dict["error"] = ErrorDetail(code=error_code, message=error_message)


def mark_section_ok(envelope: PipelineEnvelope, section_name: str) -> None:
    """
    Mark a section of the envelope as successfully processed.

    Args:
        envelope: PipelineEnvelope to modify.
        section_name: Name of section.
    """
    section = getattr(envelope, section_name, None)
    if section is not None:
        section_dict = section if isinstance(section, dict) else section.__dict__
        section_dict["status"] = "ok"
        section_dict["error"] = None


def mark_section_skipped(
    envelope: PipelineEnvelope,
    section_name: str,
    reason: str = "Not applicable",
) -> None:
    """
    Mark a section as skipped (not executed).

    Args:
        envelope: PipelineEnvelope to modify.
        section_name: Name of section.
        reason: Optional reason for skipping.
    """
    section = getattr(envelope, section_name, None)
    if section is not None:
        section_dict = section if isinstance(section, dict) else section.__dict__
        section_dict["status"] = "skipped"
