"""Consistency Checker Agent - Analyzes code for consistency with project conventions."""
import json
import logging
from typing import Any

from arcus.agents.base import agent_handler, mark_section_failed, mark_section_ok
from arcus.bedrock.client import invoke_claude
from arcus.contracts import Finding, Fix, PipelineEnvelope

logger = logging.getLogger(__name__)


def _generate_consistency_prompt(
    diff_content: str,
    conventions: dict[str, Any],
    repo_name: str,
    pr_number: int,
) -> str:
    """
    Generate a prompt for Claude to analyze code consistency.

    Args:
        diff_content: Unified diff from the PR.
        conventions: Detected conventions (naming, error handling, etc.).
        repo_name: Repository name for context.
        pr_number: PR number for context.

    Returns:
        Formatted prompt for Claude.
    """
    conventions_text = json.dumps(conventions, indent=2)

    return f"""Analyze the following code diff for consistency with project conventions.

**Project**: {repo_name} (PR #{pr_number})

**Detected Conventions**:
{conventions_text}

**Code Diff**:
```patch
{diff_content}
```

**Analysis Task**:
1. Check if added/modified code follows naming conventions
2. Verify error handling consistency
3. Look for code style violations
4. Identify inconsistencies with documented patterns

**Response Format**:
Respond with a JSON array of findings. Each finding must have:
- "file": file path
- "line_start": starting line number
- "line_end": ending line number
- "title": short description
- "rationale": explanation of the violation
- "severity": "high", "medium", or "low"
- "type": "consistency" or "convention_violation"
- "suggested_fix": optional suggestion

Example:
[
  {{
    "file": "src/main.py",
    "line_start": 42,
    "line_end": 44,
    "title": "Inconsistent naming pattern",
    "rationale": "Function uses camelCase but convention is snake_case",
    "severity": "medium",
    "type": "convention_violation",
    "suggested_fix": "rename_function() instead of renameFunction()"
  }}
]

If no violations found, return empty array [].
"""


def _parse_claude_findings(
    claude_response: str,
    agent_name: str = "consistency_checker",
) -> list[Finding]:
    """
    Parse Claude's JSON response into Finding objects.

    Args:
        claude_response: Claude's response text.
        agent_name: Name of the agent for finding attribution.

    Returns:
        List of Finding objects.
    """
    findings: list[Finding] = []

    try:
        # Extract JSON from response (Claude may add explanatory text)
        response_text = claude_response.strip()

        # Try to find JSON array in response
        json_start = response_text.find("[")
        json_end = response_text.rfind("]") + 1

        if json_start == -1 or json_end == 0:
            logger.warning("No JSON array found in Claude response")
            return findings

        json_str = response_text[json_start:json_end]
        items = json.loads(json_str)

        if not isinstance(items, list):
            logger.warning("Claude response is not a JSON array")
            return findings

        for idx, item in enumerate(items):
            try:
                # Map Claude response to Finding model
                fix_data = None
                if item.get("suggested_fix"):
                    fix_data = Fix(
                        description=item.get("suggested_fix", ""),
                        suggested_diff="",
                        confidence="medium",
                    )

                finding = Finding(
                    id=f"{agent_name}-consistency-{idx}",
                    agent=agent_name,
                    type=item.get("type", "convention_violation"),
                    severity=item.get("severity", "medium"),
                    file=item.get("file", "unknown"),
                    line_start=int(item.get("line_start", 0)),
                    line_end=int(item.get("line_end", 0)),
                    title=item.get("title", "Consistency violation"),
                    rationale=item.get("rationale", ""),
                    evidence_refs=[],
                    fix=fix_data,
                )
                findings.append(finding)

            except (ValueError, TypeError, KeyError) as e:
                logger.warning(f"Failed to parse finding item {idx}: {e}")
                continue

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Claude JSON response: {e}")
        return findings

    return findings


@agent_handler
def handle_consistency_checker(envelope: PipelineEnvelope) -> PipelineEnvelope:
    """
    Check code consistency with project conventions.

    Handler for Consistency Checker Agent (B5).
    - Reads diff and context conventions
    - Invokes Claude for consistency analysis
    - Populates envelope.consistency with findings

    Args:
        envelope: PipelineEnvelope with PR context.

    Returns:
        Updated envelope with consistency findings.
    """
    try:
        logger.info(
            f"Consistency Checker analyzing {envelope.pr.repo_full_name}#{envelope.pr.pr_number}"
        )

        # Step 1: Extract context information
        conventions = envelope.context.conventions
        if not conventions:
            logger.warning("No conventions found in context")
            conventions_dict = {}
        else:
            conventions_dict = {
                "naming": conventions.naming,
                "error_handling": conventions.error_handling,
                "notes": conventions.notes,
            }

        # Step 2: Read diff content
        # In MVP, we'll use a simple placeholder or mock diff
        # In production, fetch from envelope.pr.diff_ref (S3)
        diff_content = f"# Diff for {envelope.pr.repo_full_name} PR #{envelope.pr.pr_number}"

        # Step 3: Generate prompt for Claude
        prompt = _generate_consistency_prompt(
            diff_content=diff_content,
            conventions=conventions_dict,
            repo_name=envelope.pr.repo_full_name,
            pr_number=envelope.pr.pr_number,
        )

        # Step 4: Invoke Claude
        logger.debug(
            f"Invoking Claude for consistency analysis (repo={envelope.pr.repo_full_name})"
        )
        claude_response = invoke_claude(
            prompt=prompt,
            system_prompt="You are a strict code consistency analyzer. Analyze code for violations of project conventions. Respond only with valid JSON.",
            max_tokens=2048,
        )

        # Step 5: Parse findings
        findings = _parse_claude_findings(claude_response)
        logger.info(f"Found {len(findings)} consistency violations")

        # Step 6: Update envelope
        envelope.consistency.status = "ok"
        envelope.consistency.findings = findings
        envelope.consistency.error = None

        mark_section_ok(envelope, "consistency")

        return envelope

    except Exception as e:
        logger.error(f"Consistency Checker failed: {type(e).__name__}: {e}", exc_info=True)
        mark_section_failed(
            envelope,
            "consistency",
            error_code="consistency_analysis_failed",
            error_message=f"Failed to analyze consistency: {str(e)}",
        )
        return envelope
