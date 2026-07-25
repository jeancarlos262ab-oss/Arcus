"""Tests for graph storage and serialization."""
import json
import tempfile
from pathlib import Path

import pytest

from arcus.contracts import Edge, Node, RepoGraph
from arcus.graph.store import GraphStore


@pytest.fixture
def sample_graph() -> RepoGraph:
    """Create a sample graph for testing."""
    nodes = [
        Node(
            id="fil_001",
            type="file",
            file="src/main.py",
            name="main.py",
            metadata={"lines": 100},
        ),
        Node(
            id="fun_001",
            type="function",
            file="src/main.py",
            name="process",
            metadata={"line_start": 10, "line_end": 20, "is_public": True},
        ),
        Node(
            id="cla_001",
            type="class",
            file="src/main.py",
            name="Processor",
            metadata={"line_start": 30, "line_end": 80},
        ),
        Node(
            id="met_001",
            type="method",
            file="src/main.py",
            name="run",
            metadata={"line_start": 35, "line_end": 50, "is_method": True},
        ),
    ]

    edges = [
        Edge(source="fil_001", target="fun_001", type="contains"),
        Edge(source="fil_001", target="cla_001", type="contains"),
        Edge(source="cla_001", target="met_001", type="contains"),
    ]

    return RepoGraph(nodes=nodes, edges=edges)


@pytest.fixture
def multi_file_graph() -> RepoGraph:
    """Create a multi-file graph with imports."""
    nodes = [
        Node(
            id="fil_001",
            type="file",
            file="src/main.py",
            name="main.py",
            metadata={"lines": 50},
        ),
        Node(
            id="fun_001",
            type="function",
            file="src/main.py",
            name="main",
            metadata={"line_start": 1, "line_end": 10, "is_public": True},
        ),
        Node(
            id="fil_002",
            type="file",
            file="src/utils.py",
            name="utils.py",
            metadata={"lines": 30},
        ),
        Node(
            id="fun_002",
            type="function",
            file="src/utils.py",
            name="helper",
            metadata={"line_start": 5, "line_end": 15, "is_public": True},
        ),
    ]

    edges = [
        Edge(source="fil_001", target="fun_001", type="contains"),
        Edge(source="fil_002", target="fun_002", type="contains"),
        Edge(source="fun_001", target="fun_002", type="calls"),
        Edge(source="fil_001", target="fil_002", type="imports"),
    ]

    return RepoGraph(nodes=nodes, edges=edges)


class TestGraphStoreJSON:
    """Tests for JSON serialization."""

    def test_to_json_basic(self, sample_graph: RepoGraph) -> None:
        """Test serializing a graph to JSON."""
        json_str = GraphStore.to_json(sample_graph)

        assert isinstance(json_str, str)
        assert "nodes" in json_str
        assert "edges" in json_str

        # Verify it's valid JSON
        data = json.loads(json_str)
        assert len(data["nodes"]) == 4
        assert len(data["edges"]) == 3

    def test_from_json_basic(self, sample_graph: RepoGraph) -> None:
        """Test deserializing a graph from JSON."""
        json_str = GraphStore.to_json(sample_graph)
        recovered_graph = GraphStore.from_json(json_str)

        assert len(recovered_graph.nodes) == len(sample_graph.nodes)
        assert len(recovered_graph.edges) == len(sample_graph.edges)

    def test_json_roundtrip(self, sample_graph: RepoGraph) -> None:
        """Test that serialization and deserialization preserve data."""
        json_str = GraphStore.to_json(sample_graph)
        recovered = GraphStore.from_json(json_str)

        # Check nodes
        for orig_node, rec_node in zip(sample_graph.nodes, recovered.nodes):
            assert orig_node.id == rec_node.id
            assert orig_node.type == rec_node.type
            assert orig_node.file == rec_node.file
            assert orig_node.name == rec_node.name
            assert orig_node.metadata == rec_node.metadata

        # Check edges
        for orig_edge, rec_edge in zip(sample_graph.edges, recovered.edges):
            assert orig_edge.source == rec_edge.source
            assert orig_edge.target == rec_edge.target
            assert orig_edge.type == rec_edge.type

    def test_from_json_invalid_format(self) -> None:
        """Test error handling for invalid JSON."""
        with pytest.raises(json.JSONDecodeError):
            GraphStore.from_json("not valid json")

    def test_from_json_missing_keys(self) -> None:
        """Test error handling for missing keys."""
        with pytest.raises(ValueError):
            GraphStore.from_json('{"nodes": []}')  # Missing "edges"

        with pytest.raises(ValueError):
            GraphStore.from_json('{"edges": []}')  # Missing "nodes"

    def test_from_json_not_dict(self) -> None:
        """Test error handling for non-dict JSON."""
        with pytest.raises(ValueError):
            GraphStore.from_json("[]")  # Array instead of object

    def test_json_preserves_metadata(self, sample_graph: RepoGraph) -> None:
        """Test that metadata is preserved through serialization."""
        json_str = GraphStore.to_json(sample_graph)
        recovered = GraphStore.from_json(json_str)

        # Find file node
        orig_file = next(n for n in sample_graph.nodes if n.type == "file")
        rec_file = next(n for n in recovered.nodes if n.type == "file")

        assert orig_file.metadata == rec_file.metadata
        assert rec_file.metadata["lines"] == 100

    def test_json_empty_graph(self) -> None:
        """Test serializing an empty graph."""
        empty_graph = RepoGraph(nodes=[], edges=[])
        json_str = GraphStore.to_json(empty_graph)

        recovered = GraphStore.from_json(json_str)
        assert len(recovered.nodes) == 0
        assert len(recovered.edges) == 0


class TestGraphStoreFile:
    """Tests for file-based storage."""

    def test_to_file_and_from_file(self, sample_graph: RepoGraph) -> None:
        """Test writing and reading from file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "graph.json"

            GraphStore.to_file(sample_graph, file_path)
            assert file_path.exists()

            recovered = GraphStore.from_file(file_path)
            assert len(recovered.nodes) == len(sample_graph.nodes)
            assert len(recovered.edges) == len(sample_graph.edges)

    def test_from_file_nonexistent(self) -> None:
        """Test error handling for nonexistent file."""
        nonexistent = Path("/nonexistent/file.json")
        with pytest.raises(IOError):
            GraphStore.from_file(nonexistent)

    def test_file_roundtrip_multifile(self, multi_file_graph: RepoGraph) -> None:
        """Test file storage with multi-file graph."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "complex_graph.json"

            GraphStore.to_file(multi_file_graph, file_path)
            recovered = GraphStore.from_file(file_path)

            assert len(recovered.nodes) == 4
            assert len(recovered.edges) == 4

            # Verify nodes are preserved
            recovered_ids = {n.id for n in recovered.nodes}
            orig_ids = {n.id for n in multi_file_graph.nodes}
            assert recovered_ids == orig_ids


class TestGraphStoreDict:
    """Tests for dictionary conversion."""

    def test_to_dict(self, sample_graph: RepoGraph) -> None:
        """Test converting graph to dict."""
        data = GraphStore.to_dict(sample_graph)

        assert isinstance(data, dict)
        assert "nodes" in data
        assert "edges" in data
        assert len(data["nodes"]) == 4
        assert len(data["edges"]) == 3

    def test_from_dict(self, sample_graph: RepoGraph) -> None:
        """Test converting dict to graph."""
        data = GraphStore.to_dict(sample_graph)
        recovered = GraphStore.from_dict(data)

        assert len(recovered.nodes) == len(sample_graph.nodes)
        assert len(recovered.edges) == len(sample_graph.edges)

    def test_dict_roundtrip(self, sample_graph: RepoGraph) -> None:
        """Test dict roundtrip preservation."""
        data = GraphStore.to_dict(sample_graph)
        recovered = GraphStore.from_dict(data)

        # Check all nodes are present
        orig_ids = {n.id for n in sample_graph.nodes}
        rec_ids = {n.id for n in recovered.nodes}
        assert orig_ids == rec_ids

        # Check all edges are present
        orig_edges = {(e.source, e.target, e.type) for e in sample_graph.edges}
        rec_edges = {(e.source, e.target, e.type) for e in recovered.edges}
        assert orig_edges == rec_edges

    def test_from_dict_invalid_format(self) -> None:
        """Test error handling for invalid dict."""
        with pytest.raises(ValueError):
            GraphStore.from_dict({"nodes": []})  # Missing edges

        with pytest.raises(ValueError):
            GraphStore.from_dict("not a dict")  # Not a dict

    def test_dict_s3_compatibility(self, sample_graph: RepoGraph) -> None:
        """Test that dict format is JSON-serializable (S3 compatible)."""
        data = GraphStore.to_dict(sample_graph)

        # Should be JSON-serializable
        json_str = json.dumps(data)
        recovered_data = json.loads(json_str)

        # Should be convertible back
        recovered_graph = GraphStore.from_dict(recovered_data)
        assert len(recovered_graph.nodes) > 0


class TestGraphStoreEdgeCases:
    """Tests for edge cases and robustness."""

    def test_large_graph_serialization(self) -> None:
        """Test serialization of a large graph."""
        # Create a large graph
        nodes = [
            Node(
                id=f"node_{i}",
                type="function",
                file=f"file_{i % 10}.py",
                name=f"func_{i}",
                metadata={"index": i},
            )
            for i in range(100)
        ]

        edges = [
            Edge(source=f"node_{i}", target=f"node_{(i+1) % 100}", type="calls")
            for i in range(100)
        ]

        large_graph = RepoGraph(nodes=nodes, edges=edges)

        # Test serialization
        json_str = GraphStore.to_json(large_graph)
        recovered = GraphStore.from_json(json_str)

        assert len(recovered.nodes) == 100
        assert len(recovered.edges) == 100

    def test_special_characters_in_metadata(self) -> None:
        """Test handling of special characters in node metadata."""
        nodes = [
            Node(
                id="node_1",
                type="function",
                file="test.py",
                name="func",
                metadata={"note": "Has \"quotes\" and 'apostrophes'"},
            )
        ]

        graph = RepoGraph(nodes=nodes, edges=[])
        json_str = GraphStore.to_json(graph)
        recovered = GraphStore.from_json(json_str)

        assert recovered.nodes[0].metadata["note"] == "Has \"quotes\" and 'apostrophes'"

    def test_unicode_in_names(self) -> None:
        """Test handling of unicode characters."""
        nodes = [
            Node(
                id="node_1",
                type="function",
                file="test.py",
                name="función_españa",
                metadata={"description": "Función en español"},
            )
        ]

        graph = RepoGraph(nodes=nodes, edges=[])
        json_str = GraphStore.to_json(graph)
        recovered = GraphStore.from_json(json_str)

        assert recovered.nodes[0].name == "función_españa"
        assert "español" in recovered.nodes[0].metadata["description"]

    def test_empty_metadata(self) -> None:
        """Test handling of nodes with empty metadata."""
        nodes = [
            Node(id="n1", type="file", file="f.py", name="f", metadata={})
        ]

        graph = RepoGraph(nodes=nodes, edges=[])
        json_str = GraphStore.to_json(graph)
        recovered = GraphStore.from_json(json_str)

        assert recovered.nodes[0].metadata == {}
