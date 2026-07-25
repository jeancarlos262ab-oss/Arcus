"""Bug Hunter Agent - Detects logical bugs, edge cases, and potential runtime errors."""
import json
import logging
from typing import Any

from arcus.agents.base import agent_handler, mark_section_failed, mark_section_ok
from arcus.bedrock.client import invoke_claude
from arcus.contracts import Finding, Fix, PipelineEnvelope

logger = logging.getLogger(__name__)


def _generate_bug_detection_prompt(
    diff_content: str,
    context_info: dict[str, Any],
    repo_name: str,
    pr_number: int,
) -> str:
    """
    Generate a prompt for Claude to detect bugs in code changes.

    Args:
        diff_content: Unified diff from the PR.
        context_info: Code context (conventions, subgraph info).
        repo_name: Repository name for context.
        pr_number: PR number for context.

    Returns:
        Formatted prompt for Claude.
    """
    context_text = json.dumps(context_info, indent=2)

    return f"""Analyze the following code diff for potential bugs, logical errors, and edge cases.

**Project**: {repo_name} (PR #{pr_number})

**Code Context**:
{context_text}

**Code Diff**:
```patch
{diff_content}
```

**Analysis Task**:
1. Detect logical bugs (e.g., infinite loops, incorrect conditions)
2. Identify potential runtime errors (e.g., null pointer dereferences, missing error handling)
3. Find edge cases not handled (e.g., boundary conditions, empty inputs)
4. Look for security issues (e.g., input validation, SQL injection, XSS)
5. Spot performance problems (e.g., inefficient algorithms, N+1 queries)

**Response Format**:
Respond with a JSON array of findings. Each finding must have:
- "file": file path
- "line_start": starting line number
- "line_end": ending line number
- "title": short bug description
- "rationale": explanation of the bug
- "severity": "high", "medium", or "low"
- "type": "logic_bug" or "security"
- "suggested_fix": optional fix suggestion

Example:
[
  {{
    "file": "src/utils.py",
    "line_start": 15,
    "line_end": 18,
    "title": "Potential null pointer dereference",
    "rationale": "Variable 'user' may be None but is accessed without check",
    "severity": "high",
    "type": "logic_bug",
    "suggested_fix": "Add None check before accessing user.name"
  }}
]

If no bugs found, return empty array [].
"""


def _parse_claude_findings(
    claude_response: str,
    agent_name: str = "bug_hunter",
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
        # Extract JSON from response
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
                    id=f"{agent_name}-bug-{idx}",
                    agent=agent_name,
                    type=item.get("type", "logic_bug"),
                    severity=item.get("severity", "medium"),
                    file=item.get("file", "unknown"),
                    line_start=int(item.get("line_start", 0)),
                    line_end=int(item.get("line_end", 0)),
                    title=item.get("title", "Potential bug"),
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
def handle_bug_hunter(envelope: PipelineEnvelope) -> PipelineEnvelope:
    """
    Detect logical bugs and potential runtime errors in code changes.

    Handler for Bug Hunter Agent (B6).
    - Reads diff and code context
    - Invokes Claude for bug detection
    - Populates envelope.bugs with findings

    Args:
        envelope: PipelineEnvelope with PR context.

    Returns:
        Updated envelope with bug findings.
    """
    try:
        logger.info(
            f"Bug Hunter analyzing {envelope.pr.repo_full_name}#{envelope.pr.pr_number}"
        )

        # Step 1: Extract context information
        context_dict = {
            "conventions": {
                "naming": envelope.context.conventions.naming if envelope.context.conventions else None,
                "error_handling": envelope.context.conventions.error_handling if envelope.context.conventions else None,
            },
            "graph_info": {
                "version": envelope.context.graph_version,
                "subgraph_ref": envelope.context.relevant_subgraph_ref,
            },
            "changed_files": envelope.pr.changed_files,
        }

        # Step 2: Read diff content
        # In MVP, we'll use a simple placeholder or mock diff
        # In production, fetch from envelope.pr.diff_ref (S3)
        diff_content = f"# Diff for {envelope.pr.repo_full_name} PR #{envelope.pr.pr_number}"

        # Step 3: Generate prompt for Claude
        prompt = _generate_bug_detection_prompt(
            diff_content=diff_content,
            context_info=context_dict,
            repo_name=envelope.pr.repo_full_name,
            pr_number=envelope.pr.pr_number,
        )

        # Step 4: Invoke Claude
        logger.debug(
            f"Invoking Claude for bug detection (repo={envelope.pr.repo_full_name})"
        )
        claude_response = invoke_claude(
            prompt=prompt,
            system_prompt="You are an expert bug hunter. Analyze code for logical errors, edge cases, and security issues. Respond only with valid JSON.",
            max_tokens=2048,
        )

        # Step 5: Parse findings
        findings = _parse_claude_findings(claude_response)
        logger.info(f"Found {len(findings)} potential bugs")

        # Step 6: Update envelope
        envelope.bugs.status = "ok"
        envelope.bugs.findings = findings
        envelope.bugs.error = None

        mark_section_ok(envelope, "bugs")

        return envelope

    except Exception as e:
        logger.error(f"Bug Hunter failed: {type(e).__name__}: {e}", exc_info=True)
        mark_section_failed(
            envelope,
            "bugs",
            error_code="bug_detection_failed",
            error_message=f"Failed to detect bugs: {str(e)}",
        )
        return envelope
