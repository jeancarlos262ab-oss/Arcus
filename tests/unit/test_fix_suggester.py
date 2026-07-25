"""Tests for Fix Suggester Agent."""
import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from arcus.agents.fix_suggester import (
    handle_fix_suggester,
    _generate_fix_prompt,
    _parse_claude_fixes,
)
from arcus.contracts import Finding, PipelineEnvelope


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


@pytest.fixture
def sample_findings() -> list[Finding]:
    """Create sample findings for testing."""
    return [
        Finding(
            id="consistency-0",
            agent="consistency_checker",
            type="convention_violation",
            severity="high",
            file="src/main.py",
            line_start=10,
            line_end=12,
            title="Naming convention violation",
            rationale="Uses camelCase instead of snake_case",
            evidence_refs=[],
        ),
        Finding(
            id="bug-0",
            agent="bug_hunter",
            type="logic_bug",
            severity="medium",
            file="src/utils.py",
            line_start=20,
            line_end=22,
            title="Potential null pointer",
            rationale="Variable not checked for None",
            evidence_refs=[],
        ),
    ]


def process_envelope(envelope: PipelineEnvelope) -> PipelineEnvelope:
    """Helper to call handler and parse dict result back to PipelineEnvelope."""
    result_dict = handle_fix_suggester(envelope)  # type: ignore
    if isinstance(result_dict, dict):
        return PipelineEnvelope.model_validate(result_dict)
    raise TypeError(f"Expected dict, got {type(result_dict)}")


class TestFixSuggesterPromptGeneration:
    """Tests for prompt generation."""

    def test_prompt_includes_findings(self, sample_findings: list[Finding]) -> None:
        """Test that prompt includes findings."""
        prompt = _generate_fix_prompt(
            findings=sample_findings,
            repo_name="test/repo",
            pr_number=1,
        )

        assert "Naming convention violation" in prompt
        assert "Potential null pointer" in prompt

    def test_prompt_includes_repo_context(self, sample_findings: list[Finding]) -> None:
        """Test that prompt includes repo and PR context."""
        prompt = _generate_fix_prompt(
            findings=sample_findings,
            repo_name="test/repo",
            pr_number=1,
        )

        assert "test/repo" in prompt
        assert "PR #1" in prompt

    def test_prompt_requests_json_response(
        self, sample_findings: list[Finding]
    ) -> None:
        """Test that prompt requests JSON response format."""
        prompt = _generate_fix_prompt(
            findings=sample_findings,
            repo_name="test/repo",
            pr_number=1,
        )

        assert "JSON" in prompt
        assert "finding_id" in prompt
        assert "suggested_diff" in prompt

    def test_prompt_focuses_on_high_medium(
        self, sample_findings: list[Finding]
    ) -> None:
        """Test that prompt mentions high/medium severity."""
        prompt = _generate_fix_prompt(
            findings=sample_findings,
            repo_name="test/repo",
            pr_number=1,
        )

        assert "HIGH" in prompt or "high" in prompt
        assert "MEDIUM" in prompt or "medium" in prompt


class TestFixSuggesterParsing:
    """Tests for Claude response parsing."""

    def test_parse_empty_response(self, sample_findings: list[Finding]) -> None:
        """Test parsing empty fixes."""
        response = "[]"
        updated = _parse_claude_fixes(response, sample_findings)

        assert len(updated) == len(sample_findings)
        assert all(f.fix is None for f in updated)

    def test_parse_single_fix(self, sample_findings: list[Finding]) -> None:
        """Test parsing single fix."""
        response = json.dumps(
            [
                {
                    "finding_id": "consistency-0",
                    "description": "Rename to snake_case",
                    "suggested_diff": "def renamed_function():",
                    "confidence": "high",
                }
            ]
        )

        updated = _parse_claude_fixes(response, sample_findings)

        assert updated[0].fix is not None
        assert updated[0].fix.description == "Rename to snake_case"
        assert updated[0].fix.confidence == "high"

    def test_parse_multiple_fixes(self, sample_findings: list[Finding]) -> None:
        """Test parsing multiple fixes."""
        response = json.dumps(
            [
                {
                    "finding_id": "consistency-0",
                    "description": "Fix 1",
                    "suggested_diff": "code1",
                    "confidence": "high",
                },
                {
                    "finding_id": "bug-0",
                    "description": "Fix 2",
                    "suggested_diff": "code2",
                    "confidence": "medium",
                },
            ]
        )

        updated = _parse_claude_fixes(response, sample_findings)

        assert updated[0].fix is not None
        assert updated[1].fix is not None
        assert updated[0].fix.description == "Fix 1"
        assert updated[1].fix.description == "Fix 2"

    def test_parse_partial_fixes(self, sample_findings: list[Finding]) -> None:
        """Test parsing when only some findings get fixes."""
        response = json.dumps(
            [
                {
                    "finding_id": "consistency-0",
                    "description": "Fix 1",
                    "suggested_diff": "code1",
                    "confidence": "high",
                }
            ]
        )

        updated = _parse_claude_fixes(response, sample_findings)

        assert updated[0].fix is not None
        assert updated[1].fix is None

    def test_parse_with_extra_text(self, sample_findings: list[Finding]) -> None:
        """Test parsing with extra text around JSON."""
        response = """Here are the fixes:

[
  {
    "finding_id": "consistency-0",
    "description": "Fix it",
    "suggested_diff": "code",
    "confidence": "high"
  }
]

Done!"""

        updated = _parse_claude_fixes(response, sample_findings)

        assert updated[0].fix is not None

    def test_parse_invalid_json(self, sample_findings: list[Finding]) -> None:
        """Test parsing invalid JSON."""
        response = "This is not JSON"
        updated = _parse_claude_fixes(response, sample_findings)

        # Should return unchanged findings
        assert len(updated) == len(sample_findings)

    def test_parse_unknown_finding_id(
        self, sample_findings: list[Finding]
    ) -> None:
        """Test parsing fix for unknown finding ID."""
        response = json.dumps(
            [
                {
                    "finding_id": "unknown-999",
                    "description": "Fix",
                    "suggested_diff": "code",
                    "confidence": "high",
                }
            ]
        )

        updated = _parse_claude_fixes(response, sample_findings)

        # Should not crash, just ignore unknown IDs
        assert len(updated) == len(sample_findings)


class TestFixSuggesterBasics:
    """Tests for basic handler functionality."""

    @patch("arcus.agents.fix_suggester.invoke_claude")
    def test_handler_invokes_claude(
        self, mock_invoke: MagicMock, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test that handler invokes Claude when findings exist."""
        sample_envelope.consistency.findings = [
            Finding(
                id="test-0",
                agent="consistency_checker",
                type="convention_violation",
                severity="high",
                file="src/main.py",
                line_start=1,
                line_end=3,
                title="Test",
                rationale="Test",
            )
        ]
        mock_invoke.return_value = "[]"

        result = process_envelope(sample_envelope)

        assert mock_invoke.called

    @patch("arcus.agents.fix_suggester.invoke_claude")
    def test_handler_with_no_findings(
        self, mock_invoke: MagicMock, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test handler when there are no findings."""
        sample_envelope.consistency.findings = []
        sample_envelope.bugs.findings = []

        result = process_envelope(sample_envelope)

        assert result.fixes.status == "ok"
        assert result.fixes.findings == []
        assert not mock_invoke.called

    @patch("arcus.agents.fix_suggester.invoke_claude")
    def test_handler_skips_low_severity(
        self, mock_invoke: MagicMock, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test handler skips low severity findings."""
        sample_envelope.consistency.findings = [
            Finding(
                id="test-0",
                agent="consistency_checker",
                type="convention_violation",
                severity="low",
                file="src/main.py",
                line_start=1,
                line_end=3,
                title="Test",
                rationale="Test",
            )
        ]

        result = process_envelope(sample_envelope)

        assert result.fixes.status == "ok"
        assert not mock_invoke.called

    @patch("arcus.agents.fix_suggester.invoke_claude")
    def test_handler_includes_high_severity(
        self, mock_invoke: MagicMock, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test handler includes high severity findings."""
        sample_envelope.consistency.findings = [
            Finding(
                id="test-0",
                agent="consistency_checker",
                type="convention_violation",
                severity="high",
                file="src/main.py",
                line_start=1,
                line_end=3,
                title="Test",
                rationale="Test",
            )
        ]
        mock_invoke.return_value = "[]"

        result = process_envelope(sample_envelope)

        assert mock_invoke.called

    @patch("arcus.agents.fix_suggester.invoke_claude")
    def test_handler_includes_medium_severity(
        self, mock_invoke: MagicMock, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test handler includes medium severity findings."""
        sample_envelope.bugs.findings = [
            Finding(
                id="test-0",
                agent="bug_hunter",
                type="logic_bug",
                severity="medium",
                file="src/main.py",
                line_start=1,
                line_end=3,
                title="Test",
                rationale="Test",
            )
        ]
        mock_invoke.return_value = "[]"

        result = process_envelope(sample_envelope)

        assert mock_invoke.called


class TestFixSuggesterClaudeIntegration:
    """Tests for Claude integration."""

    @patch("arcus.agents.fix_suggester.invoke_claude")
    def test_claude_called_with_correct_system_prompt(
        self, mock_invoke: MagicMock, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test Claude is called with correct system prompt."""
        sample_envelope.consistency.findings = [
            Finding(
                id="test-0",
                agent="consistency_checker",
                type="convention_violation",
                severity="high",
                file="src/main.py",
                line_start=1,
                line_end=3,
                title="Test",
                rationale="Test",
            )
        ]
        mock_invoke.return_value = "[]"

        process_envelope(sample_envelope)

        call_kwargs = mock_invoke.call_args.kwargs
        assert "fix" in call_kwargs["system_prompt"].lower()

    @patch("arcus.agents.fix_suggester.invoke_claude")
    def test_max_tokens_configured(
        self, mock_invoke: MagicMock, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test max_tokens is configured."""
        sample_envelope.consistency.findings = [
            Finding(
                id="test-0",
                agent="consistency_checker",
                type="convention_violation",
                severity="high",
                file="src/main.py",
                line_start=1,
                line_end=3,
                title="Test",
                rationale="Test",
            )
        ]
        mock_invoke.return_value = "[]"

        process_envelope(sample_envelope)

        call_kwargs = mock_invoke.call_args.kwargs
        assert call_kwargs["max_tokens"] == 3072


class TestFixSuggesterErrorHandling:
    """Tests for error handling."""

    @patch("arcus.agents.fix_suggester.invoke_claude")
    def test_handler_on_claude_error(
        self, mock_invoke: MagicMock, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test handler resilience on Claude error."""
        sample_envelope.consistency.findings = [
            Finding(
                id="test-0",
                agent="consistency_checker",
                type="convention_violation",
                severity="high",
                file="src/main.py",
                line_start=1,
                line_end=3,
                title="Test",
                rationale="Test",
            )
        ]
        mock_invoke.side_effect = Exception("Claude error")

        result = process_envelope(sample_envelope)

        assert result.fixes.status == "failed"
        assert result.fixes.error is not None

    @patch("arcus.agents.fix_suggester.invoke_claude")
    def test_handler_on_invalid_response(
        self, mock_invoke: MagicMock, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test handler on invalid Claude response."""
        sample_envelope.consistency.findings = [
            Finding(
                id="test-0",
                agent="consistency_checker",
                type="convention_violation",
                severity="high",
                file="src/main.py",
                line_start=1,
                line_end=3,
                title="Test",
                rationale="Test",
            )
        ]
        mock_invoke.return_value = "Not JSON"

        result = process_envelope(sample_envelope)

        assert result.fixes.status == "ok"


class TestFixSuggesterEnvelopeHandling:
    """Tests for envelope handling."""

    @patch("arcus.agents.fix_suggester.invoke_claude")
    def test_result_envelope_valid(
        self, mock_invoke: MagicMock, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test result envelope is valid."""
        mock_invoke.return_value = "[]"

        result = process_envelope(sample_envelope)

        # Should be re-parseable
        reparsed = PipelineEnvelope.model_validate(result.model_dump())
        assert reparsed.fixes.status == "ok"

    @patch("arcus.agents.fix_suggester.invoke_claude")
    def test_other_sections_unchanged(
        self, mock_invoke: MagicMock, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test other sections are not modified."""
        mock_invoke.return_value = "[]"
        original_bugs = sample_envelope.bugs.model_dump()

        result = process_envelope(sample_envelope)

        assert result.bugs.model_dump() == original_bugs

    @patch("arcus.agents.fix_suggester.invoke_claude")
    def test_with_many_findings(
        self, mock_invoke: MagicMock, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test handler with many findings."""
        findings = [
            Finding(
                id=f"test-{i}",
                agent="consistency_checker",
                type="convention_violation",
                severity="high",
                file="src/main.py",
                line_start=i * 10,
                line_end=i * 10 + 2,
                title=f"Test {i}",
                rationale="Test",
            )
            for i in range(20)
        ]
        sample_envelope.consistency.findings = findings
        mock_invoke.return_value = "[]"

        result = process_envelope(sample_envelope)

        assert result.fixes.status == "ok"
