"""Unit tests for canonical graph serialization."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from arcus.contracts import RepoGraph
from arcus.graph import GraphStore

GRAPH_FIXTURE = (
    Path(__file__).parents[1] / "fixtures" / "graphs" / "example_repo_graph.json"
)


def _graph() -> RepoGraph:
    return RepoGraph.model_validate_json(GRAPH_FIXTURE.read_text(encoding="utf-8"))


def test_json_and_mapping_round_trips_preserve_contract() -> None:
    """S3 text and SDK mappings should preserve the exact node-link schema."""

    graph = _graph()
    from_json = GraphStore.from_json(GraphStore.to_json(graph))
    payload = GraphStore.to_dict(graph)
    from_mapping = GraphStore.from_dict(payload)

    assert from_json == graph
    assert from_mapping == graph
    assert "links" in payload
    assert "edges" not in payload


def test_file_round_trip_uses_utf8(tmp_path: Path) -> None:
    """Local graph seeding should produce a reloadable UTF-8 artifact."""

    path = tmp_path / "graph.json"
    GraphStore.to_file(_graph(), path)

    assert GraphStore.from_file(path) == _graph()


def test_invalid_or_legacy_graph_shapes_are_rejected() -> None:
    """Storage must not silently accept the removed nodes/edges schema."""

    with pytest.raises(ValidationError):
        GraphStore.from_json('{"nodes": [], "edges": []}')
    with pytest.raises(ValidationError):
        GraphStore.from_json("not json")
