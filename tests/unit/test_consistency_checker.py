"""Tests for Consistency Checker Agent."""
import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from arcus.agents.consistency_checker import (
    handle_consistency_checker,
    _generate_consistency_prompt,
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
    result_dict = handle_consistency_checker(envelope)  # type: ignore
    if isinstance(result_dict, dict):
        return PipelineEnvelope.model_validate(result_dict)
    raise TypeError(f"Expected dict, got {type(result_dict)}")


class TestConsistencyCheckerPromptGeneration:
    """Tests for prompt generation."""

    def test_prompt_includes_diff(self) -> None:
        """Test that prompt includes the diff content."""
        diff = "--- a/src/main.py\n+++ b/src/main.py\n@@ -1,3 +1,3 @@\n"
        conventions = {"naming": "snake_case"}

        prompt = _generate_consistency_prompt(
            diff_content=diff,
            conventions=conventions,
            repo_name="test/repo",
            pr_number=1,
        )

        assert diff in prompt
        assert "test/repo" in prompt
        assert "PR #1" in prompt

    def test_prompt_includes_conventions(self) -> None:
        """Test that prompt includes detected conventions."""
        conventions = {
            "naming": "snake_case",
            "error_handling": "custom exceptions",
        }

        prompt = _generate_consistency_prompt(
            diff_content="diff",
            conventions=conventions,
            repo_name="test/repo",
            pr_number=1,
        )

        assert "snake_case" in prompt
        assert "custom exceptions" in prompt

    def test_prompt_requests_json_response(self) -> None:
        """Test that prompt requests JSON response format."""
        prompt = _generate_consistency_prompt(
            diff_content="diff",
            conventions={},
            repo_name="test/repo",
            pr_number=1,
        )

        assert "JSON" in prompt
        assert "line_start" in prompt
        assert "line_end" in prompt


class TestConsistencyCheckerParsing:
    """Tests for Claude response parsing."""

    def test_parse_empty_response(self) -> None:
        """Test parsing empty findings list."""
        response = "[]"
        findings = _parse_claude_findings(response)

        assert findings == []

    def test_parse_single_finding(self) -> None:
        """Test parsing single finding."""
        response = json.dumps(
            [
                {
                    "file": "src/main.py",
                    "line_start": 10,
                    "line_end": 12,
                    "title": "Naming violation",
                    "rationale": "Uses camelCase instead of snake_case",
                    "severity": "medium",
                    "type": "convention_violation",
                    "suggested_fix": "Rename to snake_case",
                }
            ]
        )

        findings = _parse_claude_findings(response)

        assert len(findings) == 1
        assert findings[0].file == "src/main.py"
        assert findings[0].line_start == 10
        assert findings[0].line_end == 12
        assert findings[0].title == "Naming violation"
        assert findings[0].severity == "medium"

    def test_parse_multiple_findings(self) -> None:
        """Test parsing multiple findings."""
        response = json.dumps(
            [
                {
                    "file": "src/main.py",
                    "line_start": 10,
                    "line_end": 12,
                    "title": "First violation",
                    "rationale": "Reason 1",
                    "severity": "high",
                    "type": "convention_violation",
                },
                {
                    "file": "src/utils.py",
                    "line_start": 20,
                    "line_end": 22,
                    "title": "Second violation",
                    "rationale": "Reason 2",
                    "severity": "low",
                    "type": "inconsistency",
                },
            ]
        )

        findings = _parse_claude_findings(response)

        assert len(findings) == 2
        assert findings[0].file == "src/main.py"
        assert findings[1].file == "src/utils.py"

    def test_parse_with_suggested_fix(self) -> None:
        """Test parsing finding with suggested fix."""
        response = json.dumps(
            [
                {
                    "file": "src/main.py",
                    "line_start": 10,
                    "line_end": 12,
                    "title": "Violation",
                    "rationale": "Reason",
                    "severity": "medium",
                    "type": "convention_violation",
                    "suggested_fix": "Use snake_case naming",
                }
            ]
        )

        findings = _parse_claude_findings(response)

        assert len(findings) == 1
        assert findings[0].fix is not None
        assert findings[0].fix.description == "Use snake_case naming"

    def test_parse_with_extra_text(self) -> None:
        """Test parsing response with explanatory text before/after JSON."""
        response = """Here are the findings:

[
  {
    "file": "src/main.py",
    "line_start": 10,
    "line_end": 12,
    "title": "Violation",
    "rationale": "Reason",
    "severity": "medium",
    "type": "convention_violation"
  }
]

Analysis complete."""

        findings = _parse_claude_findings(response)

        assert len(findings) == 1
        assert findings[0].file == "src/main.py"

    def test_parse_invalid_json(self) -> None:
        """Test parsing invalid JSON gracefully returns empty list."""
        response = "This is not valid JSON"
        findings = _parse_claude_findings(response)

        assert findings == []

    def test_parse_malformed_finding(self) -> None:
        """Test that malformed findings are still parsed with defaults."""
        response = json.dumps(
            [
                {
                    "file": "src/main.py",
                    "line_start": 10,
                    "line_end": 12,
                    "title": "Valid",
                    "rationale": "Reason",
                    "severity": "medium",
                    "type": "convention_violation",
                },
                {
                    # Missing required fields - will use defaults
                    "file": "src/bad.py",
                    # Missing title, rationale, etc - will use defaults
                },
            ]
        )

        findings = _parse_claude_findings(response)

        # Should get both findings (malformed gets defaults)
        assert len(findings) == 2
        assert findings[0].file == "src/main.py"
        assert findings[1].file == "src/bad.py"


class TestConsistencyCheckerBasics:
    """Tests for basic handler functionality."""

    @patch("arcus.agents.consistency_checker.invoke_claude")
    def test_handler_invokes_claude(
        self, mock_invoke: MagicMock, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test that handler invokes Claude."""
        mock_invoke.return_value = "[]"

        result = process_envelope(sample_envelope)

        assert mock_invoke.called
        assert result.consistency.status == "ok"

    @patch("arcus.agents.consistency_checker.invoke_claude")
    def test_handler_with_no_findings(
        self, mock_invoke: MagicMock, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test handler when Claude finds no violations."""
        mock_invoke.return_value = "[]"

        result = process_envelope(sample_envelope)

        assert result.consistency.status == "ok"
        assert result.consistency.findings == []
        assert result.consistency.error is None

    @patch("arcus.agents.consistency_checker.invoke_claude")
    def test_handler_with_findings(
        self, mock_invoke: MagicMock, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test handler when Claude finds violations."""
        claude_response = json.dumps(
            [
                {
                    "file": "src/main.py",
                    "line_start": 10,
                    "line_end": 12,
                    "title": "Naming violation",
                    "rationale": "Uses camelCase",
                    "severity": "medium",
                    "type": "convention_violation",
                }
            ]
        )
        mock_invoke.return_value = claude_response

        result = process_envelope(sample_envelope)

        assert result.consistency.status == "ok"
        assert len(result.consistency.findings) == 1
        assert result.consistency.findings[0].title == "Naming violation"

    @patch("arcus.agents.consistency_checker.invoke_claude")
    def test_handler_preserves_pr_info(
        self, mock_invoke: MagicMock, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test that handler preserves PR information."""
        mock_invoke.return_value = "[]"
        original_pr = sample_envelope.pr.model_dump()

        result = process_envelope(sample_envelope)

        assert result.pr.model_dump() == original_pr

    @patch("arcus.agents.consistency_checker.invoke_claude")
    def test_handler_preserves_context(
        self, mock_invoke: MagicMock, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test that handler preserves context section."""
        mock_invoke.return_value = "[]"
        original_context = sample_envelope.context.model_dump()

        result = process_envelope(sample_envelope)

        assert result.context.model_dump() == original_context


class TestConsistencyCheckerClaudeIntegration:
    """Tests for Claude prompt and response handling."""

    @patch("arcus.agents.consistency_checker.invoke_claude")
    def test_claude_called_with_correct_system_prompt(
        self, mock_invoke: MagicMock, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test that Claude is called with correct system prompt."""
        mock_invoke.return_value = "[]"

        process_envelope(sample_envelope)

        # Verify system prompt mentions consistency
        call_kwargs = mock_invoke.call_args.kwargs
        assert "consistency" in call_kwargs["system_prompt"].lower()

    @patch("arcus.agents.consistency_checker.invoke_claude")
    def test_claude_called_with_repo_context(
        self, mock_invoke: MagicMock, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test that Claude receives repo and PR context."""
        mock_invoke.return_value = "[]"

        process_envelope(sample_envelope)

        # Verify prompt includes repo name and PR number
        call_kwargs = mock_invoke.call_args.kwargs
        prompt = call_kwargs["prompt"]
        assert sample_envelope.pr.repo_full_name in prompt
        assert str(sample_envelope.pr.pr_number) in prompt

    @patch("arcus.agents.consistency_checker.invoke_claude")
    def test_claude_called_with_conventions(
        self, mock_invoke: MagicMock, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test that Claude receives conventions in prompt."""
        mock_invoke.return_value = "[]"

        process_envelope(sample_envelope)

        call_kwargs = mock_invoke.call_args.kwargs
        prompt = call_kwargs["prompt"]
        assert "snake_case" in prompt
        assert "custom exceptions" in prompt


class TestConsistencyCheckerErrorHandling:
    """Tests for error handling and resilience."""

    @patch("arcus.agents.consistency_checker.invoke_claude")
    def test_handler_on_claude_error(
        self, mock_invoke: MagicMock, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test handler resilience when Claude fails."""
        mock_invoke.side_effect = Exception("Claude API error")

        result = process_envelope(sample_envelope)

        assert result.consistency.status == "failed"
        assert result.consistency.error is not None
        assert "Claude API error" in result.consistency.error.message

    @patch("arcus.agents.consistency_checker.invoke_claude")
    def test_handler_on_invalid_response(
        self, mock_invoke: MagicMock, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test handler when Claude returns invalid JSON."""
        mock_invoke.return_value = "This is not JSON"

        result = process_envelope(sample_envelope)

        # Should still mark as ok but with no findings
        assert result.consistency.status == "ok"
        assert result.consistency.findings == []

    @patch("arcus.agents.consistency_checker.invoke_claude")
    def test_handler_with_minimal_conventions(
        self, mock_invoke: MagicMock, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test handler when context has minimal conventions info."""
        mock_invoke.return_value = "[]"
        # Don't set to None, just keep what's there
        result = process_envelope(sample_envelope)

        # Should still work
        assert result.consistency.status == "ok"
        assert mock_invoke.called

    @patch("arcus.agents.consistency_checker.invoke_claude")
    def test_handler_with_many_findings(
        self, mock_invoke: MagicMock, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test handler with large number of findings."""
        findings_list = [
            {
                "file": "src/main.py",
                "line_start": 10 + i,
                "line_end": 12 + i,
                "title": f"Violation {i}",
                "rationale": f"Reason {i}",
                "severity": "medium",
                "type": "convention_violation",
            }
            for i in range(50)
        ]
        mock_invoke.return_value = json.dumps(findings_list)

        result = process_envelope(sample_envelope)

        assert result.consistency.status == "ok"
        assert len(result.consistency.findings) == 50


class TestConsistencyCheckerEnvelopeHandling:
    """Tests for envelope validation and integrity."""

    @patch("arcus.agents.consistency_checker.invoke_claude")
    def test_result_envelope_is_valid(
        self, mock_invoke: MagicMock, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test that result envelope is valid according to Pydantic schema."""
        mock_invoke.return_value = "[]"

        result = process_envelope(sample_envelope)

        # Should be re-parseable
        reparsed = PipelineEnvelope.model_validate(result.model_dump())
        assert reparsed.consistency.status == "ok"

    @patch("arcus.agents.consistency_checker.invoke_claude")
    def test_other_sections_unchanged(
        self, mock_invoke: MagicMock, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test that handler doesn't modify other envelope sections."""
        mock_invoke.return_value = "[]"
        original_bugs = sample_envelope.bugs.model_dump()
        original_fixes = sample_envelope.fixes.model_dump()

        result = process_envelope(sample_envelope)

        assert result.bugs.model_dump() == original_bugs
        assert result.fixes.model_dump() == original_fixes

    @patch("arcus.agents.consistency_checker.invoke_claude")
    def test_finding_ids_are_unique(
        self, mock_invoke: MagicMock, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test that finding IDs are unique."""
        findings_list = [
            {
                "file": "src/main.py",
                "line_start": 10,
                "line_end": 12,
                "title": "Violation",
                "rationale": "Reason",
                "severity": "medium",
                "type": "convention_violation",
            }
            for _ in range(3)
        ]
        mock_invoke.return_value = json.dumps(findings_list)

        result = process_envelope(sample_envelope)

        ids = [f.id for f in result.consistency.findings]
        assert len(ids) == len(set(ids))  # All unique

    @patch("arcus.agents.consistency_checker.invoke_claude")
    def test_all_findings_have_agent_name(
        self, mock_invoke: MagicMock, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test that all findings are attributed to consistency_checker."""
        findings_list = [
            {
                "file": "src/main.py",
                "line_start": 10,
                "line_end": 12,
                "title": "Violation",
                "rationale": "Reason",
                "severity": "medium",
                "type": "convention_violation",
            }
        ]
        mock_invoke.return_value = json.dumps(findings_list)

        result = process_envelope(sample_envelope)

        for finding in result.consistency.findings:
            assert finding.agent == "consistency_checker"
