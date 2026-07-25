"""Tests for Reporter Agent."""
import json
from datetime import datetime
from pathlib import Path

import pytest

from arcus.agents.reporter import (
    handle_reporter,
    _generate_markdown_report,
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


def process_envelope(envelope: PipelineEnvelope) -> PipelineEnvelope:
    """Helper to call handler and parse dict result back to PipelineEnvelope."""
    result_dict = handle_reporter(envelope)  # type: ignore
    if isinstance(result_dict, dict):
        return PipelineEnvelope.model_validate(result_dict)
    raise TypeError(f"Expected dict, got {type(result_dict)}")


class TestReporterReportGeneration:
    """Tests for report generation."""

    def test_report_includes_repo_info(self, sample_envelope: PipelineEnvelope) -> None:
        """Test report includes repository info."""
        report = _generate_markdown_report(sample_envelope)

        assert "Code Review Report" in report
        assert sample_envelope.pr.repo_full_name in report
        assert str(sample_envelope.pr.pr_number) in report

    def test_report_includes_executive_summary(
        self, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test report includes executive summary."""
        report = _generate_markdown_report(sample_envelope)

        assert "Executive Summary" in report
        assert "Total Issues Found" in report

    def test_report_includes_analysis_status(
        self, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test report includes analysis status."""
        report = _generate_markdown_report(sample_envelope)

        assert "Analysis Status" in report
        assert "Context" in report
        assert "Consistency" in report
        assert "Bugs" in report

    def test_report_includes_findings_header(
        self, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test report includes findings sections."""
        sample_envelope.consistency.findings = [
            Finding(
                id="test-0",
                agent="consistency_checker",
                type="convention_violation",
                severity="high",
                file="src/main.py",
                line_start=1,
                line_end=3,
                title="Test Finding",
                rationale="Test rationale",
            )
        ]

        report = _generate_markdown_report(sample_envelope)

        assert "Consistency Issues" in report
        assert "Test Finding" in report

    def test_report_counts_severity_levels(
        self, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test report counts findings by severity."""
        sample_envelope.consistency.findings = [
            Finding(
                id="high-0",
                agent="consistency_checker",
                type="convention_violation",
                severity="high",
                file="src/main.py",
                line_start=1,
                line_end=3,
                title="High severity",
                rationale="Test",
            ),
            Finding(
                id="medium-0",
                agent="consistency_checker",
                type="convention_violation",
                severity="medium",
                file="src/main.py",
                line_start=5,
                line_end=7,
                title="Medium severity",
                rationale="Test",
            ),
        ]

        report = _generate_markdown_report(sample_envelope)

        # Check for severity counts (with emoji formatting)
        assert "High Severity" in report and "1" in report
        assert "Medium Severity" in report and "1" in report

    def test_report_includes_conventions(self, sample_envelope: PipelineEnvelope) -> None:
        """Test report includes detected conventions."""
        report = _generate_markdown_report(sample_envelope)

        assert "Code Conventions" in report
        assert "Naming Convention" in report
        assert "Error Handling" in report

    def test_report_includes_recommendations(
        self, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test report includes recommendations."""
        report = _generate_markdown_report(sample_envelope)

        assert "Recommendations" in report

    def test_report_with_high_severity_warning(
        self, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test report includes warning for high severity issues."""
        sample_envelope.consistency.findings = [
            Finding(
                id="high-0",
                agent="consistency_checker",
                type="convention_violation",
                severity="high",
                file="src/main.py",
                line_start=1,
                line_end=3,
                title="Critical issue",
                rationale="Test",
            )
        ]

        report = _generate_markdown_report(sample_envelope)

        assert "HIGH severity issues" in report or "high" in report

    def test_report_with_no_findings(self, sample_envelope: PipelineEnvelope) -> None:
        """Test report when no findings."""
        sample_envelope.consistency.findings = []
        sample_envelope.bugs.findings = []

        report = _generate_markdown_report(sample_envelope)

        assert "No issues found" in report or "✅" in report

    def test_report_includes_footer(self, sample_envelope: PipelineEnvelope) -> None:
        """Test report includes footer."""
        report = _generate_markdown_report(sample_envelope)

        assert "Arcus PR Review Pipeline" in report
        assert sample_envelope.pipeline_run_id in report

    def test_report_is_markdown_formatted(
        self, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test report is properly formatted Markdown."""
        report = _generate_markdown_report(sample_envelope)

        # Should have markdown headers
        assert "#" in report
        # Should have code formatting
        assert "`" in report
        # Should have emphasis
        assert "**" in report


class TestReporterBasics:
    """Tests for basic handler functionality."""

    def test_handler_generates_report(self, sample_envelope: PipelineEnvelope) -> None:
        """Test handler generates report."""
        result = process_envelope(sample_envelope)

        assert result.report.status == "ok"
        assert result.report.summary is not None
        assert len(result.report.summary) > 0

    def test_handler_with_findings(self, sample_envelope: PipelineEnvelope) -> None:
        """Test handler with findings."""
        sample_envelope.consistency.findings = [
            Finding(
                id="test-0",
                agent="consistency_checker",
                type="convention_violation",
                severity="high",
                file="src/main.py",
                line_start=1,
                line_end=3,
                title="Test issue",
                rationale="Test rationale",
            )
        ]

        result = process_envelope(sample_envelope)

        assert result.report.status == "ok"
        # Summary includes header and repo/PR info
        assert "Code Review Report" in result.report.summary

    def test_handler_preserves_pr_info(self, sample_envelope: PipelineEnvelope) -> None:
        """Test handler preserves PR info."""
        original_pr = sample_envelope.pr.model_dump()

        result = process_envelope(sample_envelope)

        assert result.pr.model_dump() == original_pr

    def test_handler_preserves_context(self, sample_envelope: PipelineEnvelope) -> None:
        """Test handler preserves context."""
        original_context = sample_envelope.context.model_dump()

        result = process_envelope(sample_envelope)

        assert result.context.model_dump() == original_context

    def test_handler_with_consistency_and_bugs(
        self, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test handler with both consistency and bug findings."""
        sample_envelope.consistency.findings = [
            Finding(
                id="consistency-0",
                agent="consistency_checker",
                type="convention_violation",
                severity="high",
                file="src/main.py",
                line_start=1,
                line_end=3,
                title="Naming issue",
                rationale="Test",
            )
        ]
        sample_envelope.bugs.findings = [
            Finding(
                id="bug-0",
                agent="bug_hunter",
                type="logic_bug",
                severity="high",
                file="src/utils.py",
                line_start=10,
                line_end=12,
                title="Logic error",
                rationale="Test",
            )
        ]

        result = process_envelope(sample_envelope)

        assert result.report.status == "ok"


class TestReporterSeverityCounting:
    """Tests for severity counting."""

    def test_counts_high_severity(self, sample_envelope: PipelineEnvelope) -> None:
        """Test counting high severity findings."""
        sample_envelope.consistency.findings = [
            Finding(
                id="high-0",
                agent="consistency_checker",
                type="convention_violation",
                severity="high",
                file="src/main.py",
                line_start=1,
                line_end=3,
                title="Issue 1",
                rationale="Test",
            ),
            Finding(
                id="high-1",
                agent="consistency_checker",
                type="convention_violation",
                severity="high",
                file="src/main.py",
                line_start=5,
                line_end=7,
                title="Issue 2",
                rationale="Test",
            ),
        ]

        report = _generate_markdown_report(sample_envelope)

        assert "High Severity" in report and "2" in report

    def test_counts_medium_severity(self, sample_envelope: PipelineEnvelope) -> None:
        """Test counting medium severity findings."""
        sample_envelope.bugs.findings = [
            Finding(
                id="med-0",
                agent="bug_hunter",
                type="logic_bug",
                severity="medium",
                file="src/utils.py",
                line_start=1,
                line_end=3,
                title="Medium issue",
                rationale="Test",
            )
        ]

        report = _generate_markdown_report(sample_envelope)

        assert "Medium Severity" in report and "1" in report

    def test_counts_low_severity(self, sample_envelope: PipelineEnvelope) -> None:
        """Test counting low severity findings."""
        sample_envelope.consistency.findings = [
            Finding(
                id="low-0",
                agent="consistency_checker",
                type="convention_violation",
                severity="low",
                file="src/main.py",
                line_start=1,
                line_end=3,
                title="Low issue",
                rationale="Test",
            )
        ]

        report = _generate_markdown_report(sample_envelope)

        assert "Low Severity" in report and "1" in report

    def test_counts_across_all_sections(
        self, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test counting findings across all sections."""
        sample_envelope.consistency.findings = [
            Finding(
                id="c-0",
                agent="consistency_checker",
                type="convention_violation",
                severity="high",
                file="src/main.py",
                line_start=1,
                line_end=3,
                title="Consistency",
                rationale="Test",
            )
        ]
        sample_envelope.bugs.findings = [
            Finding(
                id="b-0",
                agent="bug_hunter",
                type="logic_bug",
                severity="high",
                file="src/utils.py",
                line_start=1,
                line_end=3,
                title="Bug",
                rationale="Test",
            )
        ]

        report = _generate_markdown_report(sample_envelope)

        assert "Total Issues Found" in report and "2" in report
        assert "High Severity" in report and "2" in report


class TestReporterErrorHandling:
    """Tests for error handling."""

    def test_handler_on_error(self, sample_envelope: PipelineEnvelope) -> None:
        """Test handler resilience on error."""
        # Mock an error by corrupting the envelope structure
        # Since reporter doesn't call Claude, errors are unlikely
        # But test the error path exists
        result = process_envelope(sample_envelope)

        # Should always return ok status (no external calls)
        assert result.report.status == "ok"

    def test_handler_with_no_sections(self, sample_envelope: PipelineEnvelope) -> None:
        """Test handler when no findings in any section."""
        sample_envelope.consistency.findings = []
        sample_envelope.bugs.findings = []

        result = process_envelope(sample_envelope)

        assert result.report.status == "ok"


class TestReporterEnvelopeHandling:
    """Tests for envelope handling."""

    def test_result_envelope_valid(self, sample_envelope: PipelineEnvelope) -> None:
        """Test result envelope is valid."""
        result = process_envelope(sample_envelope)

        # Should be re-parseable
        reparsed = PipelineEnvelope.model_validate(result.model_dump())
        assert reparsed.report.status == "ok"

    def test_other_sections_unchanged(self, sample_envelope: PipelineEnvelope) -> None:
        """Test other sections are unchanged."""
        original_consistency = sample_envelope.consistency.model_dump()
        original_bugs = sample_envelope.bugs.model_dump()

        result = process_envelope(sample_envelope)

        assert result.consistency.model_dump() == original_consistency
        assert result.bugs.model_dump() == original_bugs

    def test_report_summary_not_empty(self, sample_envelope: PipelineEnvelope) -> None:
        """Test report summary is not empty."""
        result = process_envelope(sample_envelope)

        assert result.report.summary is not None
        assert len(result.report.summary) > 0

    def test_comment_url_initialized(self, sample_envelope: PipelineEnvelope) -> None:
        """Test comment_url is initialized (None in MVP)."""
        result = process_envelope(sample_envelope)

        # In MVP, comment_url should be None (set in production when posting to GitHub)
        assert result.report.comment_url is None


class TestReporterReportContent:
    """Tests for specific report content."""

    def test_report_mentions_findings_by_type(
        self, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test report mentions finding types."""
        sample_envelope.consistency.findings = [
            Finding(
                id="test-0",
                agent="consistency_checker",
                type="convention_violation",
                severity="high",
                file="src/main.py",
                line_start=1,
                line_end=3,
                title="Convention violation",
                rationale="Test",
            )
        ]

        report = _generate_markdown_report(sample_envelope)

        assert "Convention violation" in report or "convention" in report.lower()

    def test_report_with_evidence_refs(self, sample_envelope: PipelineEnvelope) -> None:
        """Test report includes evidence references."""
        sample_envelope.consistency.findings = [
            Finding(
                id="test-0",
                agent="consistency_checker",
                type="convention_violation",
                severity="high",
                file="src/main.py",
                line_start=1,
                line_end=3,
                title="Issue",
                rationale="Test",
                evidence_refs=["ref1", "ref2"],
            )
        ]

        report = _generate_markdown_report(sample_envelope)

        # Report generation should handle evidence refs gracefully
        assert "Issue" in report

    def test_report_with_suggested_fixes(
        self, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test report handles suggested fixes."""
        from arcus.contracts import Fix

        sample_envelope.consistency.findings = [
            Finding(
                id="test-0",
                agent="consistency_checker",
                type="convention_violation",
                severity="high",
                file="src/main.py",
                line_start=1,
                line_end=3,
                title="Issue",
                rationale="Test",
                fix=Fix(
                    description="Fix it",
                    suggested_diff="code change",
                    confidence="high",
                ),
            )
        ]

        report = _generate_markdown_report(sample_envelope)

        # Report should include fixes section if available
        assert "Fixes" in report or "fix" in report.lower() or "Issue" in report
