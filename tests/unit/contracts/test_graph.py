"""Unit tests for repository graph contracts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from arcus.contracts import GraphEdgeType, RepoGraph

FIXTURE_PATH = (
    Path(__file__).parents[2] / "fixtures" / "graphs" / "example_repo_graph.json"
)


@pytest.mark.contract
def test_graph_fixture_validates_as_repo_graph() -> None:
    """The shared node-link graph fixture must be consumable by graph agents."""

    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    graph = RepoGraph.model_validate(payload)

    assert graph.repo == "acme/widgets"
    assert len(graph.nodes) == 3
    assert len(graph.links) == 2
    assert graph.links[0].type is GraphEdgeType.DEFINES
    assert graph.built_at.tzinfo is not None


@pytest.mark.contract
def test_graph_serialization_preserves_json_schema() -> None:
    """Graph serialization should use the node-link key expected by S3 consumers."""

    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    graph = RepoGraph.model_validate(payload)
    serialized = graph.model_dump(mode="json")

    assert "links" in serialized
    assert "edges" not in serialized
    assert serialized["built_at"] == "2026-07-21T10:00:00Z"


@pytest.mark.contract
def test_graph_rejects_inverted_node_ranges() -> None:
    """A graph node cannot describe an inverted source span."""

    payload = {
        "id": "src/example.py::run",
        "kind": "function",
        "file": "src/example.py",
        "name": "run",
        "line_start": 12,
        "line_end": 8,
    }

    from arcus.contracts.graph import GraphNode

    with pytest.raises(ValidationError, match="line_end"):
        GraphNode.model_validate(payload)
