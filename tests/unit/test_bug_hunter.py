"""Tests for Bug Hunter Agent."""
import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from arcus.agents.bug_hunter import (
    handle_bug_hunter,
    _generate_bug_detection_prompt,
    _parse_claude_findings,
)
from arcus.contracts import PipelineEnvelope


@pytest.fixture
def fixtures_dir() -> Path:
    """Return path to test fixtures directory."""
    return Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def sample_envelope_json(fixtures_dir: Path) -> dict:
    """Load sample envelope from fixtures."""
    with open(fixtures_dir / "envelope_sample.json") as f:
        return json.load(f)


@pytest.fixture
def sample_envelope(sample_envelope_json: dict) -> PipelineEnvelope:
    """Create a sample envelope for testing."""
    return PipelineEnvelope.model_validate(sample_envelope_json)


def process_envelope(envelope: PipelineEnvelope) -> PipelineEnvelope:
    """Helper to call handler and parse dict result back to PipelineEnvelope."""
    result_dict = handle_bug_hunter(envelope)  # type: ignore
    if isinstance(result_dict, dict):
        return PipelineEnvelope.model_validate(result_dict)
    raise TypeError(f"Expected dict, got {type(result_dict)}")


class TestBugHunterPromptGeneration:
    """Tests for prompt generation."""

    def test_prompt_includes_diff(self) -> None:
        """Test that prompt includes the diff content."""
        diff = "--- a/src/main.py\n+++ b/src/main.py\n@@ -1,3 +1,3 @@\n"
        context = {"conventions": {}}

        prompt = _generate_bug_detection_prompt(
            diff_content=diff,
            context_info=context,
            repo_name="test/repo",
            pr_number=1,
        )

        assert diff in prompt
        assert "test/repo" in prompt
        assert "PR #1" in prompt

    def test_prompt_includes_bug_detection_focus(self) -> None:
        """Test that prompt focuses on bug detection."""
        prompt = _generate_bug_detection_prompt(
            diff_content="diff",
            context_info={},
            repo_name="test/repo",
            pr_number=1,
        )

        assert "bug" in prompt.lower()
        assert "logic" in prompt.lower()
        assert "edge case" in prompt.lower() or "edge cases" in prompt.lower()

    def test_prompt_requests_json_response(self) -> None:
        """Test that prompt requests JSON response format."""
        prompt = _generate_bug_detection_prompt(
            diff_content="diff",
            context_info={},
            repo_name="test/repo",
            pr_number=1,
        )

        assert "JSON" in prompt
        assert "line_start" in prompt
        assert "line_end" in prompt

    def test_prompt_includes_context_info(self) -> None:
        """Test that prompt includes context information."""
        context = {
            "conventions": {
                "naming": "snake_case",
                "error_handling": "try-except",
            },
            "changed_files": ["src/main.py", "src/utils.py"],
        }

        prompt = _generate_bug_detection_prompt(
            diff_content="diff",
            context_info=context,
            repo_name="test/repo",
            pr_number=1,
        )

        assert "snake_case" in prompt
        assert "src/main.py" in prompt


class TestBugHunterParsing:
    """Tests for Claude response parsing."""

    def test_parse_empty_response(self) -> None:
        """Test parsing empty findings list."""
        response = "[]"
        findings = _parse_claude_findings(response)

        assert findings == []

    def test_parse_single_bug(self) -> None:
        """Test parsing single bug finding."""
        response = json.dumps(
            [
                {
                    "file": "src/main.py",
                    "line_start": 15,
                    "line_end": 18,
                    "title": "Null pointer dereference",
                    "rationale": "Variable may be None",
                    "severity": "high",
                    "type": "logic_bug",
                    "suggested_fix": "Add None check",
                }
            ]
        )

        findings = _parse_claude_findings(response)

        assert len(findings) == 1
        assert findings[0].file == "src/main.py"
        assert findings[0].type == "logic_bug"
        assert findings[0].severity == "high"

    def test_parse_security_bug(self) -> None:
        """Test parsing security bug finding."""
        response = json.dumps(
            [
                {
                    "file": "src/api.py",
                    "line_start": 50,
                    "line_end": 55,
                    "title": "SQL injection vulnerability",
                    "rationale": "User input not sanitized",
                    "severity": "high",
                    "type": "security",
                    "suggested_fix": "Use parameterized query",
                }
            ]
        )

        findings = _parse_claude_findings(response)

        assert len(findings) == 1
        assert findings[0].type == "security"
        assert "SQL" in findings[0].title

    def test_parse_multiple_bugs(self) -> None:
        """Test parsing multiple bug findings."""
        response = json.dumps(
            [
                {
                    "file": "src/main.py",
                    "line_start": 10,
                    "line_end": 12,
                    "title": "Infinite loop",
                    "rationale": "Condition always true",
                    "severity": "high",
                    "type": "logic_bug",
                },
                {
                    "file": "src/utils.py",
                    "line_start": 20,
                    "line_end": 22,
                    "title": "Off-by-one error",
                    "rationale": "Loop condition incorrect",
                    "severity": "medium",
                    "type": "logic_bug",
                },
            ]
        )

        findings = _parse_claude_findings(response)

        assert len(findings) == 2
        assert findings[0].severity == "high"
        assert findings[1].severity == "medium"

    def test_parse_with_suggested_fix(self) -> None:
        """Test parsing bug with suggested fix."""
        response = json.dumps(
            [
                {
                    "file": "src/main.py",
                    "line_start": 10,
                    "line_end": 12,
                    "title": "Bug",
                    "rationale": "Reason",
                    "severity": "medium",
                    "type": "logic_bug",
                    "suggested_fix": "Use correct operator",
                }
            ]
        )

        findings = _parse_claude_findings(response)

        assert len(findings) == 1
        assert findings[0].fix is not None
        assert findings[0].fix.description == "Use correct operator"

    def test_parse_with_extra_text(self) -> None:
        """Test parsing response with explanatory text."""
        response = """I found the following bugs:

[
  {
    "file": "src/main.py",
    "line_start": 10,
    "line_end": 12,
    "title": "Bug",
    "rationale": "Reason",
    "severity": "high",
    "type": "logic_bug"
  }
]

Let me know if you need more details."""

        findings = _parse_claude_findings(response)

        assert len(findings) == 1
        assert findings[0].severity == "high"

    def test_parse_invalid_json(self) -> None:
        """Test parsing invalid JSON gracefully."""
        response = "This is not valid JSON"
        findings = _parse_claude_findings(response)

        assert findings == []

    def test_parse_agent_name_is_bug_hunter(self) -> None:
        """Test that findings are attributed to bug_hunter agent."""
        response = json.dumps(
            [
                {
                    "file": "src/main.py",
                    "line_start": 10,
                    "line_end": 12,
                    "title": "Bug",
                    "rationale": "Reason",
                    "severity": "medium",
                    "type": "logic_bug",
                }
            ]
        )

        findings = _parse_claude_findings(response)

        assert len(findings) == 1
        assert findings[0].agent == "bug_hunter"


class TestBugHunterBasics:
    """Tests for basic handler functionality."""

    @patch("arcus.agents.bug_hunter.invoke_claude")
    def test_handler_invokes_claude(
        self, mock_invoke: MagicMock, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test that handler invokes Claude."""
        mock_invoke.return_value = "[]"

        result = process_envelope(sample_envelope)

        assert mock_invoke.called
        assert result.bugs.status == "ok"

    @patch("arcus.agents.bug_hunter.invoke_claude")
    def test_handler_with_no_bugs(
        self, mock_invoke: MagicMock, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test handler when Claude finds no bugs."""
        mock_invoke.return_value = "[]"

        result = process_envelope(sample_envelope)

        assert result.bugs.status == "ok"
        assert result.bugs.findings == []
        assert result.bugs.error is None

    @patch("arcus.agents.bug_hunter.invoke_claude")
    def test_handler_with_bugs(
        self, mock_invoke: MagicMock, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test handler when Claude finds bugs."""
        claude_response = json.dumps(
            [
                {
                    "file": "src/main.py",
                    "line_start": 15,
                    "line_end": 18,
                    "title": "Null pointer",
                    "rationale": "May be None",
                    "severity": "high",
                    "type": "logic_bug",
                }
            ]
        )
        mock_invoke.return_value = claude_response

        result = process_envelope(sample_envelope)

        assert result.bugs.status == "ok"
        assert len(result.bugs.findings) == 1
        assert result.bugs.findings[0].title == "Null pointer"

    @patch("arcus.agents.bug_hunter.invoke_claude")
    def test_handler_preserves_pr_info(
        self, mock_invoke: MagicMock, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test that handler preserves PR information."""
        mock_invoke.return_value = "[]"
        original_pr = sample_envelope.pr.model_dump()

        result = process_envelope(sample_envelope)

        assert result.pr.model_dump() == original_pr

    @patch("arcus.agents.bug_hunter.invoke_claude")
    def test_handler_preserves_context(
        self, mock_invoke: MagicMock, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test that handler preserves context section."""
        mock_invoke.return_value = "[]"
        original_context = sample_envelope.context.model_dump()

        result = process_envelope(sample_envelope)

        assert result.context.model_dump() == original_context


class TestBugHunterClaudeIntegration:
    """Tests for Claude prompt and response handling."""

    @patch("arcus.agents.bug_hunter.invoke_claude")
    def test_claude_called_with_correct_system_prompt(
        self, mock_invoke: MagicMock, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test that Claude is called with correct system prompt."""
        mock_invoke.return_value = "[]"

        process_envelope(sample_envelope)

        call_kwargs = mock_invoke.call_args.kwargs
        assert "bug" in call_kwargs["system_prompt"].lower()

    @patch("arcus.agents.bug_hunter.invoke_claude")
    def test_claude_called_with_repo_context(
        self, mock_invoke: MagicMock, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test that Claude receives repo and PR context."""
        mock_invoke.return_value = "[]"

        process_envelope(sample_envelope)

        call_kwargs = mock_invoke.call_args.kwargs
        prompt = call_kwargs["prompt"]
        assert sample_envelope.pr.repo_full_name in prompt
        assert str(sample_envelope.pr.pr_number) in prompt

    @patch("arcus.agents.bug_hunter.invoke_claude")
    def test_claude_called_with_changed_files(
        self, mock_invoke: MagicMock, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test that Claude receives changed files in context."""
        mock_invoke.return_value = "[]"

        process_envelope(sample_envelope)

        call_kwargs = mock_invoke.call_args.kwargs
        prompt = call_kwargs["prompt"]
        assert "src/main.py" in prompt

    @patch("arcus.agents.bug_hunter.invoke_claude")
    def test_max_tokens_configured(
        self, mock_invoke: MagicMock, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test that max_tokens is configured for response."""
        mock_invoke.return_value = "[]"

        process_envelope(sample_envelope)

        call_kwargs = mock_invoke.call_args.kwargs
        assert call_kwargs["max_tokens"] == 2048


class TestBugHunterBugDetection:
    """Tests for different types of bug detection."""

    @patch("arcus.agents.bug_hunter.invoke_claude")
    def test_detects_logic_bugs(
        self, mock_invoke: MagicMock, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test detection of logic bugs."""
        mock_invoke.return_value = json.dumps(
            [
                {
                    "file": "src/main.py",
                    "line_start": 10,
                    "line_end": 12,
                    "title": "Infinite loop",
                    "rationale": "i is never incremented",
                    "severity": "high",
                    "type": "logic_bug",
                }
            ]
        )

        result = process_envelope(sample_envelope)

        assert result.bugs.findings[0].type == "logic_bug"

    @patch("arcus.agents.bug_hunter.invoke_claude")
    def test_detects_security_issues(
        self, mock_invoke: MagicMock, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test detection of security issues."""
        mock_invoke.return_value = json.dumps(
            [
                {
                    "file": "src/api.py",
                    "line_start": 50,
                    "line_end": 55,
                    "title": "SQL injection",
                    "rationale": "No sanitization",
                    "severity": "high",
                    "type": "security",
                }
            ]
        )

        result = process_envelope(sample_envelope)

        assert result.bugs.findings[0].type == "security"

    @patch("arcus.agents.bug_hunter.invoke_claude")
    def test_severity_levels(
        self, mock_invoke: MagicMock, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test handling of different severity levels."""
        mock_invoke.return_value = json.dumps(
            [
                {
                    "file": "src/main.py",
                    "line_start": 10,
                    "line_end": 12,
                    "title": "High severity",
                    "rationale": "Critical",
                    "severity": "high",
                    "type": "logic_bug",
                },
                {
                    "file": "src/main.py",
                    "line_start": 20,
                    "line_end": 22,
                    "title": "Low severity",
                    "rationale": "Minor",
                    "severity": "low",
                    "type": "logic_bug",
                },
            ]
        )

        result = process_envelope(sample_envelope)

        severities = {f.severity for f in result.bugs.findings}
        assert "high" in severities
        assert "low" in severities


class TestBugHunterErrorHandling:
    """Tests for error handling and resilience."""

    @patch("arcus.agents.bug_hunter.invoke_claude")
    def test_handler_on_claude_error(
        self, mock_invoke: MagicMock, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test handler resilience when Claude fails."""
        mock_invoke.side_effect = Exception("Claude API error")

        result = process_envelope(sample_envelope)

        assert result.bugs.status == "failed"
        assert result.bugs.error is not None
        assert "Claude API error" in result.bugs.error.message

    @patch("arcus.agents.bug_hunter.invoke_claude")
    def test_handler_on_invalid_response(
        self, mock_invoke: MagicMock, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test handler when Claude returns invalid JSON."""
        mock_invoke.return_value = "This is not JSON"

        result = process_envelope(sample_envelope)

        # Should still mark as ok but with no findings
        assert result.bugs.status == "ok"
        assert result.bugs.findings == []

    @patch("arcus.agents.bug_hunter.invoke_claude")
    def test_handler_with_minimal_conventions(
        self, mock_invoke: MagicMock, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test handler when context has minimal conventions info."""
        mock_invoke.return_value = "[]"
        # Don't set to None, just keep what's there
        result = process_envelope(sample_envelope)

        # Should still work
        assert result.bugs.status == "ok"
        assert mock_invoke.called

    @patch("arcus.agents.bug_hunter.invoke_claude")
    def test_handler_with_many_bugs(
        self, mock_invoke: MagicMock, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test handler with large number of bug findings."""
        bugs_list = [
            {
                "file": "src/main.py",
                "line_start": 10 + i,
                "line_end": 12 + i,
                "title": f"Bug {i}",
                "rationale": f"Reason {i}",
                "severity": "medium",
                "type": "logic_bug",
            }
            for i in range(30)
        ]
        mock_invoke.return_value = json.dumps(bugs_list)

        result = process_envelope(sample_envelope)

        assert result.bugs.status == "ok"
        assert len(result.bugs.findings) == 30


class TestBugHunterEnvelopeHandling:
    """Tests for envelope validation and integrity."""

    @patch("arcus.agents.bug_hunter.invoke_claude")
    def test_result_envelope_is_valid(
        self, mock_invoke: MagicMock, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test that result envelope is valid according to Pydantic schema."""
        mock_invoke.return_value = "[]"

        result = process_envelope(sample_envelope)

        # Should be re-parseable
        reparsed = PipelineEnvelope.model_validate(result.model_dump())
        assert reparsed.bugs.status == "ok"

    @patch("arcus.agents.bug_hunter.invoke_claude")
    def test_other_sections_unchanged(
        self, mock_invoke: MagicMock, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test that handler doesn't modify other envelope sections."""
        mock_invoke.return_value = "[]"
        original_consistency = sample_envelope.consistency.model_dump()
        original_fixes = sample_envelope.fixes.model_dump()

        result = process_envelope(sample_envelope)

        assert result.consistency.model_dump() == original_consistency
        assert result.fixes.model_dump() == original_fixes

    @patch("arcus.agents.bug_hunter.invoke_claude")
    def test_finding_ids_are_unique(
        self, mock_invoke: MagicMock, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test that finding IDs are unique."""
        bugs_list = [
            {
                "file": "src/main.py",
                "line_start": 10,
                "line_end": 12,
                "title": "Bug",
                "rationale": "Reason",
                "severity": "medium",
                "type": "logic_bug",
            }
            for _ in range(3)
        ]
        mock_invoke.return_value = json.dumps(bugs_list)

        result = process_envelope(sample_envelope)

        ids = [f.id for f in result.bugs.findings]
        assert len(ids) == len(set(ids))  # All unique

    @patch("arcus.agents.bug_hunter.invoke_claude")
    def test_all_findings_have_agent_name(
        self, mock_invoke: MagicMock, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test that all findings are attributed to bug_hunter."""
        bugs_list = [
            {
                "file": "src/main.py",
                "line_start": 10,
                "line_end": 12,
                "title": "Bug",
                "rationale": "Reason",
                "severity": "medium",
                "type": "logic_bug",
            }
        ]
        mock_invoke.return_value = json.dumps(bugs_list)

        result = process_envelope(sample_envelope)

        for finding in result.bugs.findings:
            assert finding.agent == "bug_hunter"
