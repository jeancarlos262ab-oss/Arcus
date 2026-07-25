"""Fix Suggester Agent - Generates code fixes for detected issues."""
import json
import logging

from arcus.agents.base import agent_handler, mark_section_failed, mark_section_ok
from arcus.bedrock.client import invoke_claude
from arcus.contracts import Finding, Fix, PipelineEnvelope

logger = logging.getLogger(__name__)


def _generate_fix_prompt(
    findings: list[Finding],
    repo_name: str,
    pr_number: int,
) -> str:
    """
    Generate a prompt for Claude to suggest fixes for findings.

    Args:
        findings: List of findings to suggest fixes for.
        repo_name: Repository name for context.
        pr_number: PR number for context.

    Returns:
        Formatted prompt for Claude.
    """
    findings_text = json.dumps(
        [
            {
                "file": f.file,
                "line_start": f.line_start,
                "line_end": f.line_end,
                "title": f.title,
                "rationale": f.rationale,
                "severity": f.severity,
                "type": f.type,
            }
            for f in findings
        ],
        indent=2,
    )

    return f"""Generate code fixes for the following findings in {repo_name} PR #{pr_number}.

**Findings to Fix**:
{findings_text}

**Task**:
For each HIGH or MEDIUM severity finding, suggest a code fix.

**Response Format**:
Respond with a JSON array of fixes. Each fix must have:
- "finding_id": identifier matching the finding
- "description": brief description of the fix
- "suggested_diff": the suggested code change (diff format or code snippet)
- "confidence": "high", "medium", or "low"

Example:
[
  {{
    "finding_id": "bug-0",
    "description": "Add None check before accessing variable",
    "suggested_diff": "if user is not None: user.name",
    "confidence": "high"
  }}
]

If no fixes are needed, return empty array [].
"""


def _parse_claude_fixes(
    claude_response: str,
    findings: list[Finding],
) -> list[Finding]:
    """
    Parse Claude's fix suggestions and update findings.

    Args:
        claude_response: Claude's JSON response with fixes.
        findings: Original findings list to update with fixes.

    Returns:
        Updated findings list with Fix objects populated.
    """
    updated_findings = [f.model_copy() for f in findings]

    try:
        # Extract JSON from response
        response_text = claude_response.strip()

        # Try to find JSON array in response
        json_start = response_text.find("[")
        json_end = response_text.rfind("]") + 1

        if json_start == -1 or json_end == 0:
            logger.warning("No JSON array found in Claude response")
            return updated_findings

        json_str = response_text[json_start:json_end]
        fixes_data = json.loads(json_str)

        if not isinstance(fixes_data, list):
            logger.warning("Claude response is not a JSON array")
            return updated_findings

        # Create a map of finding IDs for quick lookup
        finding_map = {f.id: i for i, f in enumerate(updated_findings)}

        # Apply fixes to findings
        for fix_item in fixes_data:
            try:
                finding_id = fix_item.get("finding_id", "")
                if finding_id not in finding_map:
                    logger.debug(f"Fix for unknown finding: {finding_id}")
                    continue

                idx = finding_map[finding_id]
                fix_obj = Fix(
                    description=fix_item.get("description", ""),
                    suggested_diff=fix_item.get("suggested_diff", ""),
                    confidence=fix_item.get("confidence", "medium"),
                )
                updated_findings[idx].fix = fix_obj

            except (ValueError, TypeError, KeyError) as e:
                logger.warning(f"Failed to parse fix item: {e}")
                continue

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Claude JSON response: {e}")
        return updated_findings

    return updated_findings


@agent_handler
def handle_fix_suggester(envelope: PipelineEnvelope) -> PipelineEnvelope:
    """
    Suggest code fixes for detected consistency and bug findings.

    Handler for Fix Suggester Agent (B7).
    - Reads findings from consistency and bugs sections
    - Invokes Claude to suggest fixes for high/medium severity issues
    - Populates envelope.fixes with suggested solutions

    Args:
        envelope: PipelineEnvelope with findings from analysis agents.

    Returns:
        Updated envelope with fix suggestions.
    """
    try:
        logger.info(
            f"Fix Suggester processing {envelope.pr.repo_full_name}#{envelope.pr.pr_number}"
        )

        # Step 1: Collect all high/medium severity findings
        all_findings: list[Finding] = []

        # Add consistency findings
        if envelope.consistency.findings:
            for finding in envelope.consistency.findings:
                if finding.severity in ("high", "medium"):
                    all_findings.append(finding)

        # Add bug findings
        if envelope.bugs.findings:
            for finding in envelope.bugs.findings:
                if finding.severity in ("high", "medium"):
                    all_findings.append(finding)

        logger.info(f"Found {len(all_findings)} findings to fix")

        # Step 2: Skip if no significant findings
        if not all_findings:
            logger.info("No high/medium severity findings to fix")
            envelope.fixes.status = "ok"
            envelope.fixes.findings = []
            envelope.fixes.error = None
            mark_section_ok(envelope, "fixes")
            return envelope

        # Step 3: Generate prompt for Claude
        prompt = _generate_fix_prompt(
            findings=all_findings,
            repo_name=envelope.pr.repo_full_name,
            pr_number=envelope.pr.pr_number,
        )

        # Step 4: Invoke Claude
        logger.debug(
            f"Invoking Claude for fix generation (repo={envelope.pr.repo_full_name})"
        )
        claude_response = invoke_claude(
            prompt=prompt,
            system_prompt="You are an expert code fixer. Generate practical, well-tested code fixes. Respond only with valid JSON.",
            max_tokens=3072,
        )

        # Step 5: Parse fixes and update findings
        updated_findings = _parse_claude_fixes(claude_response, all_findings)
        logger.info(f"Generated fixes for {sum(1 for f in updated_findings if f.fix)} findings")

        # Step 6: Update envelope
        envelope.fixes.status = "ok"
        envelope.fixes.findings = updated_findings
        envelope.fixes.error = None

        mark_section_ok(envelope, "fixes")

        return envelope

    except Exception as e:
        logger.error(f"Fix Suggester failed: {type(e).__name__}: {e}", exc_info=True)
        mark_section_failed(
            envelope,
            "fixes",
            error_code="fix_generation_failed",
            error_message=f"Failed to generate fixes: {str(e)}",
        )
        return envelope
