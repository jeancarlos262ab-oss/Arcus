"""Unit tests for canonical repository graph queries."""

from __future__ import annotations

from pathlib import Path

import pytest

from arcus.contracts import RepoGraph
from arcus.graph import (
    extract_subgraph,
    find_links_from_node,
    find_links_to_node,
    find_node_by_id,
    find_nodes_by_file,
    get_node_dependencies,
    get_node_dependents,
)

GRAPH_FIXTURE = (
    Path(__file__).parents[1] / "fixtures" / "graphs" / "example_repo_graph.json"
)


@pytest.fixture
def graph() -> RepoGraph:
    """Load the shared graph used by all workstreams."""

    return RepoGraph.model_validate_json(GRAPH_FIXTURE.read_text(encoding="utf-8"))


def test_changed_file_subgraph_includes_definitions_and_dependents(
    graph: RepoGraph,
) -> None:
    """One-hop context should include the changed module and its caller."""

    subgraph = extract_subgraph(graph, ["src/config.py"], hops=1)

    identifiers = {node.id for node in subgraph.nodes}
    assert "src/config.py" in identifiers
    assert "src/config.py::load_config" in identifiers
    assert "src/review.py::run_review" in identifiers
    assert all(
        link.source in identifiers and link.target in identifiers
        for link in subgraph.links
    )


def test_zero_hops_and_missing_paths_are_bounded(graph: RepoGraph) -> None:
    """Zero hops should not expand, while unknown paths should return empty context."""

    direct = extract_subgraph(graph, ["src/config.py"], hops=0)
    missing = extract_subgraph(graph, ["src/missing.py"])

    assert {node.file for node in direct.nodes} == {"src/config.py"}
    assert missing.nodes == []
    assert missing.links == []
    with pytest.raises(ValueError, match="hops"):
        extract_subgraph(graph, ["src/config.py"], hops=-1)


def test_lookup_and_traversal_helpers_use_links(graph: RepoGraph) -> None:
    """ID, file, dependency, and dependent helpers should agree on direction."""

    config_nodes = find_nodes_by_file(graph, "src/config.py")
    load_config = find_node_by_id(graph, "src/config.py::load_config")
    outgoing = find_links_from_node(graph, "src/review.py::run_review")
    incoming = find_links_to_node(graph, "src/config.py::load_config")
    dependencies = get_node_dependencies(graph, "src/review.py::run_review")
    dependents = get_node_dependents(graph, "src/config.py::load_config")

    assert len(config_nodes) == 2
    assert load_config is not None
    assert {(link.source, link.target, link.type) for link in outgoing} == {
        (
            "src/review.py::run_review",
            "src/config.py::load_config",
            "calls",
        )
    }
    assert {link.source for link in incoming} == {
        "src/config.py",
        "src/review.py::run_review",
    }
    assert all(link.target == "src/config.py::load_config" for link in incoming)
    assert {node.id for node in dependencies} == {"src/config.py::load_config"}
    assert {node.id for node in dependents} == {
        "src/config.py",
        "src/review.py::run_review",
    }
