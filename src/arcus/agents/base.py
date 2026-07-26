"""Shared execution boundary for every agent Lambda."""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from typing import Literal, cast

from arcus.config import Settings
from arcus.contracts import (
    AgentError,
    AgentStatus,
    PipelineEnvelope,
    RepoGraph,
    StageSection,
)
from arcus.errors import AgentError as AgentExecutionError
from arcus.errors import ArcusError

logger = logging.getLogger(__name__)

SectionName = Literal["context", "consistency", "bugs", "fixes", "report"]


class BaseAgent(ABC):
    """Validate, execute, degrade, and serialize one pipeline stage."""

    section_name: SectionName
    failure_code: str
    continue_on_error = True

    def __init__(self, runtime_settings: Settings) -> None:
        """Store the limits applied to every stage output."""

        self._settings = runtime_settings

    def run(self, event: Mapping[str, object] | PipelineEnvelope) -> dict[str, object]:
        """Run one stage and return a complete valid envelope.

        Invalid input raises so Step Functions can classify a contract failure.
        Intermediate stages degrade after validated-input failures, while terminal
        side-effect stages can disable degradation and fail the Lambda task.
        """

        envelope = parse_envelope(event)
        try:
            result = self.process(envelope)
        except Exception as error:
            error_code = (
                error.code if isinstance(error, ArcusError) else self.failure_code
            )
            logger.exception(
                "agent_stage_failed",
                extra={
                    "correlation_id": str(envelope.pipeline_run_id),
                    "agent": self.section_name,
                    "pr_id": f"{envelope.pr.repo_full_name}#{envelope.pr.pr_number}",
                    "error_code": error_code,
                    "error_type": type(error).__name__,
                },
            )
            if not self.continue_on_error:
                raise
            mark_section_failed(envelope, self.section_name, error_code, str(error))
            result = envelope
        return serialize_envelope(result, max_bytes=self._settings.max_envelope_bytes)

    @abstractmethod
    def process(self, envelope: PipelineEnvelope) -> PipelineEnvelope:
        """Append this stage's result without modifying prior sections."""


def parse_envelope(
    event: Mapping[str, object] | PipelineEnvelope,
) -> PipelineEnvelope:
    """Validate untrusted Lambda input against the shared contract."""

    if isinstance(event, PipelineEnvelope):
        return event.model_copy(deep=True)
    return PipelineEnvelope.model_validate(event)


def serialize_envelope(
    envelope: PipelineEnvelope,
    *,
    max_bytes: int,
) -> dict[str, object]:
    """Serialize an envelope and enforce the Step Functions payload budget."""

    payload = cast(dict[str, object], envelope.model_dump(mode="json"))
    size = len(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    if size > max_bytes:
        raise ValueError(f"pipeline envelope exceeds the {max_bytes}-byte limit")
    return payload


def load_relevant_graph(
    envelope: PipelineEnvelope,
    artifact_reader: Callable[[str], str],
) -> RepoGraph | None:
    """Load and validate the PR subgraph or confirm explicit diff-only mode.

    Args:
        envelope: Validated pipeline state produced by Context Builder.
        artifact_reader: Bounded text loader for the referenced S3 artifact.

    Returns:
        The repository-matching subgraph, or ``None`` for declared diff-only mode.

    Raises:
        AgentExecutionError: If graph mode is declared without usable context.
    """

    if envelope.context.ran_diff_only:
        return None
    reference = envelope.context.relevant_subgraph_ref
    if reference is None:
        raise AgentExecutionError(
            "graph context reference is unavailable",
            code="missing_graph_context",
        )
    try:
        graph = RepoGraph.model_validate_json(artifact_reader(reference))
    except (ValueError, UnicodeError) as error:
        raise AgentExecutionError(
            "graph context artifact is invalid",
            code="invalid_graph_context",
        ) from error
    if graph.repo != envelope.pr.repo_full_name:
        raise AgentExecutionError(
            "graph context does not match the pull request repository",
            code="graph_repository_mismatch",
        )
    return graph


def build_analysis_prompt(
    instructions: str,
    diff: str,
    graph: RepoGraph | None,
    *,
    max_bytes: int,
) -> str:
    """Fit deterministic graph context and diff text within the model byte budget.

    The complete prompt—not only the fetched diff—is bounded. Graph context remains
    valid JSON after reduction, and oversized diffs are UTF-8-safe truncated rather
    than causing an otherwise valid pipeline run to skip analysis.

    Args:
        instructions: Agent-specific contract and repository metadata.
        diff: Persisted unified diff text.
        graph: Validated PR-relevant graph, or ``None`` in diff-only mode.
        max_bytes: Maximum UTF-8 prompt size accepted by the Bedrock adapter.

    Returns:
        A complete prompt whose encoded size does not exceed ``max_bytes``.
    """

    prefix = instructions.rstrip()
    graph_label = "\n\nRepository graph context:\n"
    diff_label = "\n\nUnified diff:\n"
    fixed_size = len(f"{prefix}{graph_label}{diff_label}".encode())
    available = max_bytes - fixed_size
    if available < 2:
        raise ValueError("max_prompt_bytes is too small for agent instructions")

    if graph is None:
        graph_text = '{"mode":"diff-only"}'
    else:
        graph_budget = max(2, available // 3)
        graph_text = _bounded_graph_json(graph, graph_budget)
    diff_budget = max(0, available - len(graph_text.encode("utf-8")))
    diff_text = _truncate_utf8(diff, diff_budget)
    prompt = f"{prefix}{graph_label}{graph_text}{diff_label}{diff_text}"
    if len(prompt.encode("utf-8")) > max_bytes:
        raise ValueError("analysis prompt budget calculation failed")
    return prompt


def mark_section_failed(
    envelope: PipelineEnvelope,
    section_name: SectionName,
    error_code: str,
    error_message: str,
) -> None:
    """Replace one stage section with a contract-valid failed copy."""

    section = cast(StageSection, getattr(envelope, section_name))
    data = section.model_dump(mode="python")
    data.update(
        {
            "status": AgentStatus.FAILED,
            "error": AgentError(code=error_code, message=error_message),
        }
    )
    if section_name == "context":
        data["ran_diff_only"] = True
    failed = type(section).model_validate(data)
    setattr(envelope, section_name, failed)


def _bounded_graph_json(graph: RepoGraph, max_bytes: int) -> str:
    """Reduce graph entities in stable order while keeping valid compact JSON."""

    payload: dict[str, object] = {
        "repo": graph.repo,
        "graph_version": graph.graph_version,
        "nodes": [],
        "links": [],
    }
    if _json_size(payload) > max_bytes:
        return "{}"

    selected_nodes: list[dict[str, object]] = []
    selected_ids: set[str] = set()
    for node in graph.nodes:
        candidate_node = cast(dict[str, object], node.model_dump(mode="json"))
        candidate_payload = {**payload, "nodes": [*selected_nodes, candidate_node]}
        if _json_size(candidate_payload) > max_bytes:
            break
        selected_nodes.append(candidate_node)
        selected_ids.add(node.id)
        payload = candidate_payload

    selected_links: list[dict[str, object]] = []
    for link in graph.links:
        if link.source not in selected_ids or link.target not in selected_ids:
            continue
        candidate_link = cast(dict[str, object], link.model_dump(mode="json"))
        candidate_payload = {**payload, "links": [*selected_links, candidate_link]}
        if _json_size(candidate_payload) > max_bytes:
            break
        selected_links.append(candidate_link)
        payload = candidate_payload
    return json.dumps(payload, separators=(",", ":"))


def _json_size(payload: Mapping[str, object]) -> int:
    """Return compact JSON size for prompt-budget calculations."""

    return len(json.dumps(payload, separators=(",", ":")).encode("utf-8"))


def _truncate_utf8(text: str, max_bytes: int) -> str:
    """Truncate text at a UTF-8 boundary and mark bounded loss when possible."""

    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    marker = b"\n...[truncated]"
    if max_bytes <= len(marker):
        return encoded[:max_bytes].decode("utf-8", errors="ignore")
    prefix = encoded[: max_bytes - len(marker)].decode("utf-8", errors="ignore")
    return f"{prefix}{marker.decode()}"
