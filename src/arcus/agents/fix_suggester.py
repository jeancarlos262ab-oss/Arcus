"""Fix Suggester stage enriching existing findings in one model call."""

from __future__ import annotations

import json
from functools import lru_cache

from arcus.agents.base import BaseAgent
from arcus.agents.runtime import model, settings
from arcus.bedrock.client import BedrockClient
from arcus.config import Settings
from arcus.contracts import (
    AgentFindingsSection,
    AgentStatus,
    Finding,
    PipelineEnvelope,
    Severity,
)
from arcus.errors import BedrockResponseError


class FixSuggesterAgent(BaseAgent):
    """Attach validated fixes to existing high/medium findings only."""

    section_name = "fixes"
    failure_code = "fix_generation_failed"

    def __init__(self, model: BedrockClient, runtime_settings: Settings) -> None:
        """Create the stage with one bounded Converse client."""

        super().__init__(runtime_settings)
        self._model = model

    def process(self, envelope: PipelineEnvelope) -> PipelineEnvelope:
        """Generate one fix batch and preserve all original finding identities."""

        candidates = [
            finding
            for finding in [*envelope.consistency.findings, *envelope.bugs.findings]
            if finding.severity in {Severity.HIGH, Severity.MEDIUM}
        ][: self._settings.max_findings_total]
        if not candidates:
            envelope.fixes = AgentFindingsSection(status=AgentStatus.SKIPPED)
            return envelope

        response = self._model.invoke_model(
            _build_prompt(envelope, candidates),
            max_tokens=self._settings.max_output_tokens,
        )
        batch = self._model.parse_fix_batch(response)
        candidate_ids = {finding.id for finding in candidates}
        assignments = {
            assignment.finding_id: assignment.fix for assignment in batch.fixes
        }
        unknown_ids = set(assignments) - candidate_ids
        if unknown_ids:
            raise BedrockResponseError("Fix response referenced unknown finding IDs")

        enriched = [
            finding.model_copy(update={"fix": assignments.get(finding.id)})
            for finding in candidates
        ]
        envelope.fixes = AgentFindingsSection(
            status=AgentStatus.OK,
            findings=enriched,
        )
        return envelope


def _build_prompt(envelope: PipelineEnvelope, findings: list[Finding]) -> str:
    """Build one bounded prompt for all eligible findings."""

    payload = [finding.model_dump(mode="json", exclude={"fix"}) for finding in findings]
    return (
        "You are Arcus Fix Suggester. Propose a focused fix for each supplied "
        'finding. Do not create findings. Return JSON as {"fixes": [{"finding_id": '
        'UUID, "fix": {"description": string, "suggested_diff": unified diff, '
        '"confidence": high|medium|low}}]}.\n\n'
        f"Repository: {envelope.pr.repo_full_name}\n"
        f"PR: {envelope.pr.pr_number}\n"
        f"Findings: {json.dumps(payload, separators=(',', ':'))}"
    )


@lru_cache(maxsize=1)
def _agent() -> FixSuggesterAgent:
    """Reuse the stage and Converse client across warm invocations."""

    return FixSuggesterAgent(model(), settings())


def lambda_handler(event: dict[str, object], _context: object) -> dict[str, object]:
    """Run Fix Suggester for one validated pipeline envelope."""

    return _agent().run(event)
