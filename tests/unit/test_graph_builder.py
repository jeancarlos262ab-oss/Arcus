"""Unit tests for canonical tree-sitter graph construction."""

from __future__ import annotations

from pathlib import Path

import pytest

from arcus.contracts import GraphEdgeType, GraphNodeKind, RepoGraph
from arcus.graph import GraphBuilder

FIXTURES = Path(__file__).parents[1] / "fixtures"


@pytest.fixture
def builder() -> GraphBuilder:
    """Create a builder whose paths are relative to shared fixtures."""

    return GraphBuilder(
        "acme/widgets",
        "fixture-commit",
        root_path=FIXTURES,
    )


def test_parse_file_builds_modules_definitions_and_methods(
    builder: GraphBuilder,
) -> None:
    """A Python fixture should produce schema-valid nested definitions."""

    graph = builder.parse_file(FIXTURES / "sample_module_a.py")

    assert isinstance(graph, RepoGraph)
    assert graph.repo == "acme/widgets"
    assert graph.graph_version == "fixture-commit"
    assert {node.kind for node in graph.nodes} >= {
        GraphNodeKind.MODULE,
        GraphNodeKind.CLASS,
        GraphNodeKind.FUNCTION,
        GraphNodeKind.METHOD,
    }
    assert any(node.name == "process_data" for node in graph.nodes)
    assert any(node.name == "AdvancedProcessor" for node in graph.nodes)
    assert any(link.type is GraphEdgeType.DEFINES for link in graph.links)
    assert any(link.type is GraphEdgeType.CALLS for link in graph.links)
    assert any(link.type is GraphEdgeType.INHERITS for link in graph.links)
    assert len({node.id for node in graph.nodes}) == len(graph.nodes)


def test_parse_directory_accumulates_files_in_stable_relative_paths(
    builder: GraphBuilder,
) -> None:
    """Directory builds should include both shared modules without absolute paths."""

    graph = builder.parse_directory(FIXTURES)

    files = {node.file for node in graph.nodes}
    assert "sample_module_a.py" in files
    assert "sample_module_b.py" in files
    assert all(not Path(file_name).is_absolute() for file_name in files)


def test_parse_directory_connects_imports_calls_and_inheritance(
    builder: GraphBuilder,
) -> None:
    """One-hop context must cross real repository dependency relationships."""

    graph = builder.parse_directory(FIXTURES)
    links = {(link.source, link.target, link.type) for link in graph.links}

    assert (
        "sample_module_b.py",
        "sample_module_a.py",
        GraphEdgeType.IMPORTS,
    ) in links
    assert (
        "sample_module_b.py::transform_record",
        "sample_module_a.py::process_data",
        GraphEdgeType.CALLS,
    ) in links
    assert (
        "sample_module_a.py::AdvancedProcessor",
        "sample_module_a.py::DataProcessor",
        GraphEdgeType.INHERITS,
    ) in links


def test_builder_records_source_ranges_signatures_and_docstrings(
    builder: GraphBuilder,
) -> None:
    """LLM context metadata should identify real source spans."""

    graph = builder.parse_file(FIXTURES / "sample_module_a.py")
    process = next(node for node in graph.nodes if node.name == "process_data")

    assert process.line_start < process.line_end
    assert process.signature is not None
    assert process.signature.startswith("def process_data")
    assert process.docstring_present is True


def test_parse_missing_file_fails_with_context(builder: GraphBuilder) -> None:
    """A missing graph source should fail rather than emit an empty graph."""

    with pytest.raises(FileNotFoundError):
        builder.parse_file(FIXTURES / "missing.py")
