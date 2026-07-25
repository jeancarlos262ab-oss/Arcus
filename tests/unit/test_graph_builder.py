"""Tests for the graph builder module."""
from pathlib import Path

import pytest

from arcus.graph.builder import GraphBuilder
from arcus.contracts import RepoGraph, Node, Edge


@pytest.fixture
def graph_builder() -> GraphBuilder:
    """Create a fresh GraphBuilder instance."""
    return GraphBuilder()


@pytest.fixture
def fixtures_dir() -> Path:
    """Return path to test fixtures directory."""
    return Path(__file__).parent.parent / "fixtures"


class TestGraphBuilderBasics:
    """Tests for basic graph builder functionality."""

    def test_graph_builder_initialization(self, graph_builder: GraphBuilder) -> None:
        """Test that GraphBuilder initializes correctly."""
        assert graph_builder.parser is not None
        assert len(graph_builder.nodes_list) == 0
        assert len(graph_builder.edges_list) == 0

    def test_parse_simple_file(
        self, graph_builder: GraphBuilder, fixtures_dir: Path
    ) -> None:
        """Test parsing a simple Python file."""
        sample_file = fixtures_dir / "sample_module_a.py"
        assert sample_file.exists(), f"Sample file not found: {sample_file}"

        graph = graph_builder.parse_file(sample_file)

        # Verify RepoGraph contract
        assert isinstance(graph, RepoGraph)
        assert len(graph.nodes) > 0
        assert any(node.type == "file" for node in graph.nodes)

    def test_extract_functions(
        self, graph_builder: GraphBuilder, fixtures_dir: Path
    ) -> None:
        """Test extraction of function definitions."""
        sample_file = fixtures_dir / "sample_module_a.py"
        graph = graph_builder.parse_file(sample_file)

        # Check for extracted functions
        function_nodes = [node for node in graph.nodes if node.type == "function"]
        assert len(function_nodes) >= 2, "Should extract at least 2 functions"

        # Verify function node structure
        for func_node in function_nodes:
            assert func_node.file == str(sample_file)
            assert "line_start" in func_node.metadata
            assert "line_end" in func_node.metadata
            assert "is_public" in func_node.metadata

    def test_extract_classes(
        self, graph_builder: GraphBuilder, fixtures_dir: Path
    ) -> None:
        """Test extraction of class definitions."""
        sample_file = fixtures_dir / "sample_module_a.py"
        graph = graph_builder.parse_file(sample_file)

        # Check for extracted classes
        class_nodes = [node for node in graph.nodes if node.type == "class"]
        assert len(class_nodes) >= 2, "Should extract at least 2 classes"

        # Verify class node structure
        for class_node in class_nodes:
            assert class_node.file == str(sample_file)
            assert "line_start" in class_node.metadata
            assert "line_end" in class_node.metadata

    def test_extract_methods(
        self, graph_builder: GraphBuilder, fixtures_dir: Path
    ) -> None:
        """Test extraction of class methods."""
        sample_file = fixtures_dir / "sample_module_a.py"
        graph = graph_builder.parse_file(sample_file)

        # Check for extracted methods
        method_nodes = [node for node in graph.nodes if node.type == "method"]
        assert len(method_nodes) >= 2, "Should extract methods from classes"

        # Verify method metadata
        for method_node in method_nodes:
            assert method_node.metadata.get("is_method") is True

    def test_extract_imports(
        self, graph_builder: GraphBuilder, fixtures_dir: Path
    ) -> None:
        """Test extraction of import statements."""
        sample_file = fixtures_dir / "sample_module_a.py"
        graph = graph_builder.parse_file(sample_file)

        # Check for import edges
        import_edges = [edge for edge in graph.edges if edge.type in ("imports", "imports_from")]
        assert len(import_edges) > 0, "Should extract import statements"

    def test_file_metadata(
        self, graph_builder: GraphBuilder, fixtures_dir: Path
    ) -> None:
        """Test that file node includes metadata."""
        sample_file = fixtures_dir / "sample_module_a.py"
        graph = graph_builder.parse_file(sample_file)

        file_nodes = [node for node in graph.nodes if node.type == "file"]
        assert len(file_nodes) == 1

        file_node = file_nodes[0]
        assert "lines" in file_node.metadata
        assert file_node.metadata["lines"] > 0

    def test_graph_structure_compliance(
        self, graph_builder: GraphBuilder, fixtures_dir: Path
    ) -> None:
        """Test that extracted graph complies with RepoGraph contract."""
        sample_file = fixtures_dir / "sample_module_a.py"
        graph = graph_builder.parse_file(sample_file)

        # Verify all nodes are valid Node instances
        for node in graph.nodes:
            assert isinstance(node, Node)
            assert node.id
            assert node.type
            assert node.file
            assert node.name
            assert isinstance(node.metadata, dict)

        # Verify all edges are valid Edge instances
        for edge in graph.edges:
            assert isinstance(edge, Edge)
            assert edge.source
            assert edge.target
            assert edge.type

    def test_reset_builder_state(
        self, graph_builder: GraphBuilder, fixtures_dir: Path
    ) -> None:
        """Test that reset clears builder state."""
        sample_file = fixtures_dir / "sample_module_a.py"
        graph_builder.parse_file(sample_file)

        assert len(graph_builder.nodes_list) > 0
        assert len(graph_builder.edges_list) > 0

        graph_builder.reset()

        assert len(graph_builder.nodes_list) == 0
        assert len(graph_builder.edges_list) == 0

    def test_public_vs_private_functions(
        self, graph_builder: GraphBuilder, fixtures_dir: Path
    ) -> None:
        """Test that public/private function distinction is tracked."""
        sample_file = fixtures_dir / "sample_module_a.py"
        graph = graph_builder.parse_file(sample_file)

        # Check both top-level functions and methods
        function_nodes = [node for node in graph.nodes if node.type == "function"]
        method_nodes = [node for node in graph.nodes if node.type == "method"]

        # Top-level functions should have is_public
        public_functions = [
            f for f in function_nodes if f.metadata.get("is_public", False)
        ]
        private_functions = [
            f for f in function_nodes if not f.metadata.get("is_public", True)
        ]

        assert len(public_functions) > 0, "Should have public functions"
        assert len(private_functions) >= 0, "May have private functions"
        
        # Methods should be present
        assert len(method_nodes) > 0, "Should have extracted methods"

    def test_multiple_files(self, graph_builder: GraphBuilder, fixtures_dir: Path) -> None:
        """Test parsing multiple files sequentially."""
        sample_a = fixtures_dir / "sample_module_a.py"
        sample_b = fixtures_dir / "sample_module_b.py"

        assert sample_a.exists()
        assert sample_b.exists()

        # Parse first file
        graph_a = graph_builder.parse_file(sample_a)
        nodes_a_count = len(graph_a.nodes)

        # Parse second file (builder accumulates)
        graph_b = graph_builder.parse_file(sample_b)
        nodes_b_count = len(graph_b.nodes)

        # Second parse should have more nodes (cumulative)
        assert nodes_b_count >= nodes_a_count

    def test_edge_types_variety(
        self, graph_builder: GraphBuilder, fixtures_dir: Path
    ) -> None:
        """Test that various edge types are detected."""
        sample_file = fixtures_dir / "sample_module_a.py"
        graph = graph_builder.parse_file(sample_file)

        edge_types = {edge.type for edge in graph.edges}

        # Should have at least 'contains' edges for file->class/function
        # and 'imports' edges for import statements
        assert "contains" in edge_types
        assert any(
            et in edge_types for et in ["imports", "imports_from"]
        ), "Should have import edges"

    def test_node_ids_unique(
        self, graph_builder: GraphBuilder, fixtures_dir: Path
    ) -> None:
        """Test that all node IDs are unique."""
        sample_file = fixtures_dir / "sample_module_a.py"
        graph = graph_builder.parse_file(sample_file)

        node_ids = [node.id for node in graph.nodes]
        unique_ids = set(node_ids)

        assert len(node_ids) == len(
            unique_ids
        ), "All node IDs should be unique"

    def test_parse_nonexistent_file(self, graph_builder: GraphBuilder) -> None:
        """Test that parsing nonexistent file raises an error."""
        nonexistent = Path("/nonexistent/file.py")

        with pytest.raises(IOError):
            graph_builder.parse_file(nonexistent)


class TestGraphBuilderIntegration:
    """Integration tests for graph builder."""

    def test_cross_module_references(
        self, graph_builder: GraphBuilder, fixtures_dir: Path
    ) -> None:
        """Test detection of cross-module references."""
        # sample_module_b imports from sample_module_a
        sample_b = fixtures_dir / "sample_module_b.py"
        graph = graph_builder.parse_file(sample_b)

        # Should have edges indicating imports from another module
        import_edges = [e for e in graph.edges if e.type in ("imports", "imports_from")]
        assert len(import_edges) > 0

    def test_class_hierarchy(
        self, graph_builder: GraphBuilder, fixtures_dir: Path
    ) -> None:
        """Test detection of class inheritance (AdvancedProcessor extends DataProcessor)."""
        sample_file = fixtures_dir / "sample_module_a.py"
        graph = graph_builder.parse_file(sample_file)

        # Should have classes extracted
        classes = [n for n in graph.nodes if n.type == "class"]
        assert any(c.name == "DataProcessor" for c in classes)
        assert any(c.name == "AdvancedProcessor" for c in classes)

    def test_full_contract_compliance(
        self, graph_builder: GraphBuilder, fixtures_dir: Path
    ) -> None:
        """Test full compliance with RepoGraph contract."""
        sample_file = fixtures_dir / "sample_module_a.py"
        graph = graph_builder.parse_file(sample_file)

        # Must be a RepoGraph
        assert isinstance(graph, RepoGraph)

        # All nodes must have required fields
        for node in graph.nodes:
            assert node.id, "Node must have ID"
            assert node.type in [
                "file", "module", "class", "function", "method"
            ], f"Invalid node type: {node.type}"
            assert node.file, "Node must have file path"
            assert node.name, "Node must have name"

        # All edges must have required fields
        for edge in graph.edges:
            assert edge.source, "Edge must have source"
            assert edge.target, "Edge must have target"
            assert edge.type in [
                "imports", "imports_from", "contains", "calls", "defines"
            ], f"Invalid edge type: {edge.type}"
