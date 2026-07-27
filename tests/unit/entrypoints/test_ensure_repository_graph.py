"""Unit coverage for the graph-bootstrap Lambda degradation boundary."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock

from arcus.config import Settings
from arcus.contracts import AgentStatus, PipelineEnvelope
from arcus.entrypoints.ensure_repository_graph import EnsureRepositoryGraphHandler
from arcus.errors import PermanentError
from arcus.graph.bootstrap import RepositoryGraphBootstrapper

FIXTURE = Path(__file__).parents[2] / "fixtures" / "envelopes" / "initial.json"


def test_bootstrap_failure_returns_explicit_diff_only_envelope() -> None:
    bootstrapper = Mock(spec=RepositoryGraphBootstrapper)
    bootstrapper.ensure.side_effect = PermanentError(
        "archive exceeded limit",
        code="repository_archive_too_large",
    )
    settings = Settings(
        aws_region="us-east-1",
        bedrock_model_id="fixture-model",
    )
    handler = EnsureRepositoryGraphHandler(bootstrapper, settings)
    event = json.loads(FIXTURE.read_text(encoding="utf-8"))

    output = handler.run(event)
    envelope = PipelineEnvelope.model_validate(output)

    assert envelope.context.status is AgentStatus.FAILED
    assert envelope.context.ran_diff_only is True
    assert envelope.context.error is not None
    assert envelope.context.error.code == "repository_archive_too_large"
    assert "diff-only" in envelope.context.error.message
