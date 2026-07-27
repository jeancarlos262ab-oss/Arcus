"""Reporter stage posting one idempotent GitHub comment and history row."""

from __future__ import annotations

from functools import lru_cache

from arcus.agents.base import BaseAgent
from arcus.agents.runtime import history, settings
from arcus.config import Settings
from arcus.contracts import (
    AgentStatus,
    Finding,
    FixSuggestion,
    PipelineEnvelope,
    ReportSection,
    Severity,
)
from arcus.github.api import GitHubClient
from arcus.github.runtime import github_client
from arcus.storage.history import ReviewHistoryStore


class ReporterAgent(BaseAgent):
    """Render all surviving stage results and persist the final review."""

    section_name = "report"
    failure_code = "report_generation_failed"
    continue_on_error = False

    def __init__(
        self,
        github: GitHubClient,
        history_store: ReviewHistoryStore,
        runtime_settings: Settings,
    ) -> None:
        """Create Reporter with idempotent GitHub and DynamoDB boundaries."""

        super().__init__(runtime_settings)
        self._github = github
        self._history = history_store

    def process(self, envelope: PipelineEnvelope) -> PipelineEnvelope:
        """Upsert the review comment and deterministic history record."""

        markdown = generate_markdown_report(envelope)
        comment_url = self._github.upsert_review_comment(
            envelope.pr.repo_full_name,
            envelope.pr.pr_number,
            envelope.pr.installation_id,
            markdown,
        )
        envelope.report = ReportSection(
            status=AgentStatus.OK,
            comment_url=comment_url,
            summary=_summary(envelope),
        )
        self._history.put(envelope)
        return envelope


def generate_markdown_report(envelope: PipelineEnvelope) -> str:
    """Render deterministic Markdown for one GitHub review comment."""

    findings = [*envelope.consistency.findings, *envelope.bugs.findings]
    context_mode = (
        "unavailable"
        if envelope.context.status is AgentStatus.FAILED
        else "diff-only"
        if envelope.context.ran_diff_only
        else "graph + diff"
    )
    counts = {
        severity: sum(finding.severity is severity for finding in findings)
        for severity in Severity
    }
    lines = [
        "# Arcus review",
        "",
        f"Repository: `{envelope.pr.repo_full_name}`",
        f"PR: **#{envelope.pr.pr_number}**",
        f"Commit: `{envelope.pr.commit_sha}`",
        "",
        "## Summary",
        "",
        f"- High: **{counts[Severity.HIGH]}**",
        f"- Medium: **{counts[Severity.MEDIUM]}**",
        f"- Low: **{counts[Severity.LOW]}**",
        f"- Context mode: **{context_mode}**",
        "",
        "## Pipeline status",
        "",
        f"- Context: `{envelope.context.status.value}`",
        f"- Consistency: `{envelope.consistency.status.value}`",
        f"- Bugs: `{envelope.bugs.status.value}`",
        f"- Fixes: `{envelope.fixes.status.value}`",
    ]
    failed_sections = [
        (name, section.error)
        for name, section in (
            ("context", envelope.context),
            ("consistency", envelope.consistency),
            ("bugs", envelope.bugs),
            ("fixes", envelope.fixes),
        )
        if section.status is AgentStatus.FAILED
    ]
    if failed_sections:
        lines.extend(["", "## Degraded stages", ""])
        for name, error in failed_sections:
            if error is not None:
                lines.append(f"- **{name}**: `{error.code}` — {error.message}")

    if findings:
        lines.extend(["", "## Findings", ""])
        fixes = {finding.id: finding.fix for finding in envelope.fixes.findings}
        for finding in findings:
            _append_finding(lines, finding, fixes.get(finding.id))
    else:
        lines.extend(["", "No actionable findings were detected."])

    lines.extend(
        [
            "",
            "---",
            f"Pipeline run: `{envelope.pipeline_run_id}`",
        ]
    )
    return "\n".join(lines)


def _append_finding(
    lines: list[str],
    finding: Finding,
    fix: FixSuggestion | None,
) -> None:
    """Append one finding and its optional enriched fix."""

    lines.extend(
        [
            f"### [{finding.severity.value.upper()}] {finding.title}",
            "",
            f"`{finding.file}:{finding.line_start}-{finding.line_end}` · `{finding.type.value}`",
            "",
            finding.rationale,
        ]
    )
    if fix is not None:
        lines.extend(
            [
                "",
                f"**Suggested fix ({fix.confidence.value})**: {fix.description}",
                "",
                "```diff",
                fix.suggested_diff,
                "```",
            ]
        )
    lines.append("")


def _summary(envelope: PipelineEnvelope) -> str:
    """Return a compact deterministic summary for DynamoDB/dashboard reads."""

    findings = [*envelope.consistency.findings, *envelope.bugs.findings]
    high = sum(finding.severity is Severity.HIGH for finding in findings)
    medium = sum(finding.severity is Severity.MEDIUM for finding in findings)
    low = sum(finding.severity is Severity.LOW for finding in findings)
    return f"{len(findings)} findings: {high} high, {medium} medium, {low} low"


@lru_cache(maxsize=1)
def _agent() -> ReporterAgent:
    """Reuse GitHub and DynamoDB clients across warm invocations."""

    return ReporterAgent(github_client(), history(), settings())


def lambda_handler(event: dict[str, object], _context: object) -> dict[str, object]:
    """Run Reporter for one validated pipeline envelope."""

    return _agent().run(event)
