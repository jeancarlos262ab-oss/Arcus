"""Bug Hunter stage using Bedrock Converse and persisted PR artifacts."""

from __future__ import annotations

import json
from functools import lru_cache

from arcus.agents.base import BaseAgent, build_analysis_prompt, load_relevant_graph
from arcus.agents.runtime import artifacts, model, settings
from arcus.bedrock.client import BedrockClient
from arcus.config import Settings
from arcus.contracts import (
    AgentFindingsSection,
    AgentStatus,
    FindingAgent,
    FindingType,
    PipelineEnvelope,
)
from arcus.errors import AgentError, BedrockResponseError
from arcus.storage.artifacts import S3ArtifactStore


class BugHunterAgent(BaseAgent):
    """Find logic and security defects using bounded diff and graph context."""

    section_name = "bugs"
    failure_code = "bug_analysis_failed"

    def __init__(
        self,
        *,
        model: BedrockClient,
        artifact_store: S3ArtifactStore,
        runtime_settings: Settings,
    ) -> None:
        """Create the stage with deterministic model and artifact boundaries."""

        super().__init__(runtime_settings)
        self._model = model
        self._artifacts = artifact_store

    def process(self, envelope: PipelineEnvelope) -> PipelineEnvelope:
        """Read bounded artifacts, invoke Converse once, and validate findings."""

        if envelope.pr.diff_ref is None:
            raise AgentError("pull request diff is unavailable", code="missing_diff")
        diff = self._artifacts.get_text(envelope.pr.diff_ref)
        graph = load_relevant_graph(envelope, self._artifacts.get_text)
        context = {
            "changed_files": envelope.pr.changed_files,
            "ran_diff_only": envelope.context.ran_diff_only,
            "conventions": (
                envelope.context.conventions.model_dump(mode="json")
                if envelope.context.conventions is not None
                else None
            ),
        }
        prompt = build_analysis_prompt(
            _build_instructions(envelope, context),
            diff,
            graph,
            max_bytes=self._settings.max_prompt_bytes,
        )
        findings = self._model.parse_findings(
            self._model.invoke_model(
                prompt,
                max_tokens=self._settings.max_output_tokens,
            )
        )
        for finding in findings:
            if finding.agent is not FindingAgent.BUG_HUNTER:
                raise BedrockResponseError("Bug response used the wrong agent")
            if finding.type not in {FindingType.LOGIC_BUG, FindingType.SECURITY}:
                raise BedrockResponseError("Bug response used an invalid finding type")
        envelope.bugs = AgentFindingsSection(
            status=AgentStatus.OK,
            findings=findings,
        )
        return envelope


def _build_instructions(
    envelope: PipelineEnvelope,
    context: dict[str, object],
) -> str:
    """Build deterministic instructions requesting the exact Finding contract."""

    return (
        "You are Arcus Bug Hunter. Review the supplied unified diff for logic "
        "bugs, unsafe edge cases, and security defects. Use repository graph "
        "relationships to inspect dependencies and dependents represented in the "
        "provided context. Return JSON as "
        '{"findings": [...]} where every item has id (UUID), '
        'agent="bug_hunter", type (logic_bug or security), severity, file, '
        "line_start, line_end, title, rationale, evidence_refs, and fix=null. "
        "Return an empty findings array when there are no actionable defects.\n\n"
        f"Repository: {envelope.pr.repo_full_name}\n"
        f"PR: {envelope.pr.pr_number}\n"
        f"Context: {json.dumps(context, separators=(',', ':'))}"
    )


@lru_cache(maxsize=1)
def _agent() -> BugHunterAgent:
    """Reuse the stage and clients across warm invocations."""

    return BugHunterAgent(
        model=model(),
        artifact_store=artifacts(),
        runtime_settings=settings(),
    )


def lambda_handler(event: dict[str, object], _context: object) -> dict[str, object]:
    """Run Bug Hunter for one validated pipeline envelope."""

    return _agent().run(event)
