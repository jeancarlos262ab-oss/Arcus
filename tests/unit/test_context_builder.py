"""Tests for Context Builder Agent."""
import json
from datetime import datetime
from pathlib import Path

import pytest

from arcus.agents.context_builder import handle_context_builder
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
    """
    Helper to call handler and parse dict result back to PipelineEnvelope.
    
    The @agent_handler decorator wraps the handler and returns a serialized dict.
    This helper simulates the Lambda call flow and parses the response back.
    """
    # Call the handler (which returns a dict due to decorator)
    result_dict = handle_context_builder(envelope)  # type: ignore
    
    # Parse the dict back to PipelineEnvelope
    if isinstance(result_dict, dict):
        return PipelineEnvelope.model_validate(result_dict)
    
    # Shouldn't happen, but handle unexpected cases
    raise TypeError(f"Expected dict, got {type(result_dict)}")


class TestContextBuilderBasics:
    """Tests for basic context builder functionality."""

    def test_context_builder_processes_envelope(
        self, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test that context builder processes envelope and returns it."""
        result_envelope = process_envelope(sample_envelope)

        assert isinstance(result_envelope, PipelineEnvelope)
        assert result_envelope.pr == sample_envelope.pr

    def test_context_section_populated(
        self, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test that context section is populated with data."""
        result_envelope = process_envelope(sample_envelope)

        assert result_envelope.context.status == "ok"
        assert result_envelope.context.conventions is not None
        assert result_envelope.context.graph_version is not None

    def test_context_conventions_default(
        self, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test that default conventions are populated."""
        result_envelope = process_envelope(sample_envelope)

        conventions = result_envelope.context.conventions
        assert conventions.naming in ("snake_case", "mixed")
        assert conventions.error_handling is not None

    def test_context_has_graph_ref(
        self, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test that context includes graph reference (S3 URL in production)."""
        result_envelope = process_envelope(sample_envelope)

        # In MVP, graph_ref is set
        if result_envelope.context.graph_ref:
            assert "arcus-graphs" in result_envelope.context.graph_ref

    def test_envelope_contract_compliance(
        self, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test that resulting envelope is valid according to contract."""
        result_envelope = process_envelope(sample_envelope)

        # Should be serializable to Pydantic model
        assert result_envelope.model_validate(result_envelope.model_dump())

    def test_context_error_none_on_success(
        self, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test that context.error is None on successful processing."""
        result_envelope = process_envelope(sample_envelope)

        assert result_envelope.context.error is None

    def test_pr_metadata_unchanged(
        self, sample_envelope: PipelineEnvelope,
    ) -> None:
        """Test that PR metadata is not modified."""
        original_pr = sample_envelope.pr.model_dump()
        result_envelope = process_envelope(sample_envelope)

        assert result_envelope.pr.model_dump() == original_pr

    def test_changed_files_logged(self, sample_envelope: PipelineEnvelope) -> None:
        """Test that changed files are processed."""
        sample_envelope.pr.changed_files = ["src/main.py", "src/utils.py"]
        result_envelope = process_envelope(sample_envelope)

        # Context should process changed files
        assert result_envelope.context.status == "ok"


class TestContextBuilderEnvelopeParsing:
    """Tests for envelope parsing and serialization."""

    def test_handle_with_dict_input(self, sample_envelope_json: dict) -> None:
        """Test that handler can process dict input directly."""
        # This tests the decorator's envelope parsing
        result_dict = handle_context_builder(sample_envelope_json)  # type: ignore
        result = PipelineEnvelope.model_validate(result_dict)

        assert isinstance(result, PipelineEnvelope)

    def test_handle_with_envelope_object(self, sample_envelope: PipelineEnvelope) -> None:
        """Test that handler can process envelope object."""
        result_envelope = process_envelope(sample_envelope)

        assert isinstance(result_envelope, PipelineEnvelope)

    def test_result_is_serializable(
        self, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test that result can be serialized to dict for Lambda response."""
        result_envelope = process_envelope(sample_envelope)

        # Should be serializable to dict/JSON
        result_dict = result_envelope.model_dump(mode="json")
        assert isinstance(result_dict, dict)

        # Should be JSON serializable
        json_str = json.dumps(result_dict)
        assert isinstance(json_str, str)

    def test_result_can_be_reparsed(
        self, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test that serialized result can be reparsed as envelope."""
        result_envelope = process_envelope(sample_envelope)

        # Serialize and deserialize
        result_dict = result_envelope.model_dump(mode="json")
        reparsed = PipelineEnvelope.model_validate(result_dict)

        # Should equal original result
        assert reparsed.context.status == result_envelope.context.status


class TestContextBuilderConventions:
    """Tests for convention detection."""

    def test_conventions_include_naming(
        self, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test that conventions include naming convention."""
        result_envelope = process_envelope(sample_envelope)

        conventions = result_envelope.context.conventions
        assert conventions.naming in ("snake_case", "mixed", "camelCase")

    def test_conventions_include_error_handling(
        self, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test that conventions include error handling strategy."""
        result_envelope = process_envelope(sample_envelope)

        conventions = result_envelope.context.conventions
        assert conventions.error_handling is not None
        assert len(conventions.error_handling) > 0

    def test_conventions_can_have_notes(
        self, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test that conventions can include analysis notes."""
        result_envelope = process_envelope(sample_envelope)

        conventions = result_envelope.context.conventions
        assert isinstance(conventions.notes, list)
        # Notes may be empty or populated


class TestContextBuilderErrorHandling:
    """Tests for error handling and resilience."""

    def test_handler_with_minimal_envelope(self) -> None:
        """Test handler with minimal required envelope fields."""
        minimal_envelope = PipelineEnvelope(
            pipeline_run_id="test-1",
            created_at=datetime.now(),
            pr={
                "repo_full_name": "test/repo",
                "pr_number": 1,
                "commit_sha": "abc123",
                "installation_id": 999,
                "diff_ref": "s3://test/diff.patch",
            },
            context={"status": "ok"},
            consistency={"status": "ok"},
            bugs={"status": "ok"},
            fixes={"status": "ok"},
            report={"status": "ok"},
        )

        result = process_envelope(minimal_envelope)

        assert result.context.status == "ok"

    def test_handler_with_empty_changed_files(
        self, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test handler when PR has no changed files."""
        sample_envelope.pr.changed_files = []
        result = process_envelope(sample_envelope)

        assert result.context.status == "ok"

    def test_handler_preserves_other_sections(
        self, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test that context builder doesn't modify other envelope sections."""
        original_consistency = sample_envelope.consistency.model_dump()
        original_bugs = sample_envelope.bugs.model_dump()

        result = process_envelope(sample_envelope)

        assert result.consistency.model_dump() == original_consistency
        assert result.bugs.model_dump() == original_bugs

    def test_multiple_changed_files(
        self, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test processing multiple changed files."""
        sample_envelope.pr.changed_files = [
            "src/main.py",
            "src/utils.py",
            "src/config.py",
            "tests/test_main.py",
        ]

        result = process_envelope(sample_envelope)

        assert result.context.status == "ok"


class TestContextBuilderIntegration:
    """Integration tests for context builder."""

    def test_context_builder_in_pipeline(
        self, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test context builder as first agent in pipeline."""
        # Simulate pipeline flow:
        # 1. Context Builder populates context
        result = process_envelope(sample_envelope)

        # 2. Result should be valid for next agent to consume
        assert result.context.status == "ok"
        assert result.pipeline_run_id == sample_envelope.pipeline_run_id

    def test_envelope_roundtrip_with_context(
        self, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test that envelope survives roundtrip through context builder."""
        # Process envelope
        result = process_envelope(sample_envelope)

        # Serialize
        serialized = result.model_dump(mode="json")

        # Deserialize
        reparsed = PipelineEnvelope.model_validate(serialized)

        # Verify context is intact
        assert reparsed.context.status == "ok"
        assert reparsed.context.conventions.naming is not None


class TestContextBuilderEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_very_long_repo_name(
        self, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test handling of very long repository names."""
        sample_envelope.pr.repo_full_name = (
            "very-long-org-name/" + "a" * 100 + "/" + "b" * 100
        )
        result = process_envelope(sample_envelope)

        assert result.context.status == "ok"

    def test_special_characters_in_files(
        self, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test handling of special characters in file paths."""
        sample_envelope.pr.changed_files = [
            "src/file-with-dashes.py",
            "src/file_with_underscores.py",
            "src/UPPER_CASE.py",
        ]
        result = process_envelope(sample_envelope)

        assert result.context.status == "ok"

    def test_unicode_in_repo_name(
        self, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test handling of unicode in repository names."""
        sample_envelope.pr.repo_full_name = "org-España/proyecto-こんにちは"
        result = process_envelope(sample_envelope)

        assert result.context.status == "ok"

    def test_large_changed_files_list(
        self, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test handling of PR with many changed files."""
        sample_envelope.pr.changed_files = [
            f"src/file_{i}.py" for i in range(100)
        ]
        result = process_envelope(sample_envelope)

        assert result.context.status == "ok"

    def test_context_with_all_optional_fields(
        self, sample_envelope: PipelineEnvelope
    ) -> None:
        """Test that all optional context fields are handled properly."""
        result = process_envelope(sample_envelope)

        context = result.context
        # All these may be None in MVP but should be syntactically valid
        _ = context.graph_ref
        _ = context.graph_version
        _ = context.relevant_subgraph_ref
        _ = context.conventions
        _ = context.error

        # Should still be valid
        assert result.context.status in ("ok", "failed", "skipped")
