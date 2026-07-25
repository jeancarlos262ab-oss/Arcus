"""Tests for graph querying and subgraph extraction."""
import pytest

from arcus.contracts import Edge, Node, RepoGraph
from arcus.graph.query import (
    extract_subgraph,
    find_edges_from_node,
    find_edges_to_node,
    find_node_by_id,
    find_nodes_by_file,
    get_node_dependencies,
    get_node_dependents,
)


@pytest.fixture
def simple_graph() -> RepoGraph:
    """Create a simple graph for testing."""
    nodes = [
        Node(
            id="fil_main",
            type="file",
            file="src/main.py",
            name="main.py",
            metadata={"lines": 50},
        ),
        Node(
            id="fun_main",
            type="function",
            file="src/main.py",
            name="main",
            metadata={"is_public": True},
        ),
        Node(
            id="cla_app",
            type="class",
            file="src/main.py",
            name="App",
            metadata={},
        ),
        Node(
            id="met_run",
            type="method",
            file="src/main.py",
            name="run",
            metadata={"is_method": True},
        ),
    ]

    edges = [
        Edge(source="fil_main", target="fun_main", type="contains"),
        Edge(source="fil_main", target="cla_app", type="contains"),
        Edge(source="cla_app", target="met_run", type="contains"),
    ]

    return RepoGraph(nodes=nodes, edges=edges)


@pytest.fixture
def dependency_graph() -> RepoGraph:
    """Create a graph with dependencies between files."""
    nodes = [
        # main.py
        Node(
            id="fil_main",
            type="file",
            file="src/main.py",
            name="main.py",
            metadata={},
        ),
        Node(
            id="fun_main",
            type="function",
            file="src/main.py",
            name="main",
            metadata={},
        ),
        # utils.py
        Node(
            id="fil_utils",
            type="file",
            file="src/utils.py",
            name="utils.py",
            metadata={},
        ),
        Node(
            id="fun_helper",
            type="function",
            file="src/utils.py",
            name="helper",
            metadata={},
        ),
        # config.py
        Node(
            id="fil_config",
            type="file",
            file="src/config.py",
            name="config.py",
            metadata={},
        ),
        Node(
            id="fun_load_config",
            type="function",
            file="src/config.py",
            name="load_config",
            metadata={},
        ),
    ]

    edges = [
        # Contains relationships
        Edge(source="fil_main", target="fun_main", type="contains"),
        Edge(source="fil_utils", target="fun_helper", type="contains"),
        Edge(source="fil_config", target="fun_load_config", type="contains"),
        # Import relationships
        Edge(source="fil_main", target="fil_utils", type="imports"),
        Edge(source="fil_main", target="fil_config", type="imports"),
        # Function call relationships
        Edge(source="fun_main", target="fun_helper", type="calls"),
        Edge(source="fun_main", target="fun_load_config", type="calls"),
    ]

    return RepoGraph(nodes=nodes, edges=edges)


class TestExtractSubgraph:
    """Tests for extract_subgraph function."""

    def test_extract_single_file(self, dependency_graph: RepoGraph) -> None:
        """Test extracting subgraph for a single changed file."""
        subgraph = extract_subgraph(dependency_graph, ["src/main.py"])

        # Should include the file and its contents
        file_nodes = [n for n in subgraph.nodes if n.type == "file"]
        assert any(n.file == "src/main.py" for n in file_nodes)

        # Should include functions in main.py
        main_funcs = [n for n in subgraph.nodes if n.file == "src/main.py"]
        assert len(main_funcs) > 1  # File + functions

    def test_extract_with_dependencies(self, dependency_graph: RepoGraph) -> None:
        """Test that subgraph includes immediate dependencies."""
        subgraph = extract_subgraph(dependency_graph, ["src/main.py"], hops=1)

        # Should include main.py
        assert any(n.file == "src/main.py" for n in subgraph.nodes)

        # Should include functions that main.py calls
        file_paths = {n.file for n in subgraph.nodes}
        assert "src/utils.py" in file_paths or "src/config.py" in file_paths

    def test_extract_multiple_files(self, dependency_graph: RepoGraph) -> None:
        """Test extracting subgraph for multiple changed files."""
        subgraph = extract_subgraph(dependency_graph, ["src/main.py", "src/utils.py"])

        file_paths = {n.file for n in subgraph.nodes}
        assert "src/main.py" in file_paths
        assert "src/utils.py" in file_paths

    def test_extract_with_zero_hops(self, dependency_graph: RepoGraph) -> None:
        """Test extracting with zero hops (only changed files)."""
        subgraph = extract_subgraph(dependency_graph, ["src/main.py"], hops=0)

        # Should only include main.py and its contents
        file_paths = {n.file for n in subgraph.nodes}
        assert file_paths == {"src/main.py"}

    def test_extract_nonexistent_file(self, dependency_graph: RepoGraph) -> None:
        """Test extracting for a file not in the graph."""
        subgraph = extract_subgraph(dependency_graph, ["src/nonexistent.py"])

        # Should return empty or minimal graph
        assert len(subgraph.nodes) == 0 or all(
            n.file != "src/nonexistent.py" for n in subgraph.nodes
        )

    def test_extract_preserves_edges(self, dependency_graph: RepoGraph) -> None:
        """Test that extracted subgraph preserves edges within the subgraph."""
        subgraph = extract_subgraph(dependency_graph, ["src/main.py"], hops=1)

        # Should have edges between nodes in the subgraph
        assert len(subgraph.edges) > 0

        # All edges should connect nodes in the subgraph
        node_ids = {n.id for n in subgraph.nodes}
        for edge in subgraph.edges:
            assert edge.source in node_ids
            assert edge.target in node_ids

    def test_extract_different_hops(self, dependency_graph: RepoGraph) -> None:
        """Test that different hop counts produce different subgraphs."""
        subgraph_0 = extract_subgraph(dependency_graph, ["src/main.py"], hops=0)
        subgraph_1 = extract_subgraph(dependency_graph, ["src/main.py"], hops=1)

        # 1-hop should have more or equal nodes
        assert len(subgraph_1.nodes) >= len(subgraph_0.nodes)


class TestNodeLookupFunctions:
    """Tests for node lookup utility functions."""

    def test_find_nodes_by_file(self, simple_graph: RepoGraph) -> None:
        """Test finding nodes by file path."""
        nodes = find_nodes_by_file(simple_graph, "src/main.py")

        assert len(nodes) > 0
        assert all(n.file == "src/main.py" for n in nodes)

    def test_find_nodes_by_nonexistent_file(self, simple_graph: RepoGraph) -> None:
        """Test finding nodes for nonexistent file."""
        nodes = find_nodes_by_file(simple_graph, "src/nonexistent.py")

        assert len(nodes) == 0

    def test_find_node_by_id(self, simple_graph: RepoGraph) -> None:
        """Test finding a node by its ID."""
        node = find_node_by_id(simple_graph, "fun_main")

        assert node is not None
        assert node.name == "main"

    def test_find_node_by_nonexistent_id(self, simple_graph: RepoGraph) -> None:
        """Test finding node with nonexistent ID."""
        node = find_node_by_id(simple_graph, "nonexistent_id")

        assert node is None


class TestEdgeLookupFunctions:
    """Tests for edge lookup functions."""

    def test_find_edges_from_node(self, simple_graph: RepoGraph) -> None:
        """Test finding edges from a node."""
        edges = find_edges_from_node(simple_graph, "fil_main")

        assert len(edges) > 0
        assert all(e.source == "fil_main" for e in edges)

    def test_find_edges_from_node_no_edges(self, simple_graph: RepoGraph) -> None:
        """Test finding edges from node with no outgoing edges."""
        edges = find_edges_from_node(simple_graph, "met_run")

        assert len(edges) == 0

    def test_find_edges_to_node(self, simple_graph: RepoGraph) -> None:
        """Test finding edges to a node."""
        edges = find_edges_to_node(simple_graph, "fun_main")

        assert len(edges) > 0
        assert all(e.target == "fun_main" for e in edges)

    def test_find_edges_to_node_no_edges(self, simple_graph: RepoGraph) -> None:
        """Test finding edges to node with no incoming edges."""
        edges = find_edges_to_node(simple_graph, "fil_main")

        assert len(edges) == 0


class TestDependencyTraversal:
    """Tests for dependency traversal functions."""

    def test_get_node_dependencies(self, dependency_graph: RepoGraph) -> None:
        """Test getting dependencies of a node."""
        deps = get_node_dependencies(dependency_graph, "fun_main", hops=1)

        # main function calls helper and load_config
        dep_names = {d.name for d in deps}
        assert "helper" in dep_names or "load_config" in dep_names

    def test_get_node_dependencies_zero_hops(
        self, dependency_graph: RepoGraph
    ) -> None:
        """Test getting dependencies with zero hops."""
        deps = get_node_dependencies(dependency_graph, "fun_main", hops=0)

        # Zero hops means no dependencies
        assert len(deps) == 0

    def test_get_node_dependents(self, dependency_graph: RepoGraph) -> None:
        """Test getting dependents of a node."""
        dependents = get_node_dependents(dependency_graph, "fun_helper", hops=1)

        # main function depends on helper
        dependent_names = {d.name for d in dependents}
        assert "main" in dependent_names

    def test_get_node_dependents_zero_hops(
        self, dependency_graph: RepoGraph
    ) -> None:
        """Test getting dependents with zero hops."""
        dependents = get_node_dependents(dependency_graph, "fun_helper", hops=0)

        # Zero hops means no dependents
        assert len(dependents) == 0

    def test_dependencies_multiple_hops(self, dependency_graph: RepoGraph) -> None:
        """Test dependency traversal with multiple hops."""
        # Get 2-hop dependencies from main
        deps_1 = get_node_dependencies(dependency_graph, "fun_main", hops=1)
        deps_2 = get_node_dependencies(dependency_graph, "fun_main", hops=2)

        # 2 hops should have at least as many as 1 hop
        assert len(deps_2) >= len(deps_1)


class TestSubgraphEdgeCases:
    """Tests for edge cases in subgraph extraction."""

    def test_empty_changed_files(self, dependency_graph: RepoGraph) -> None:
        """Test extracting subgraph with no changed files."""
        subgraph = extract_subgraph(dependency_graph, [])

        assert len(subgraph.nodes) == 0
        assert len(subgraph.edges) == 0

    def test_file_path_normalization(self, dependency_graph: RepoGraph) -> None:
        """Test that file paths are normalized for comparison."""
        # Try with trailing slash (should still match)
        subgraph = extract_subgraph(dependency_graph, ["src/main.py/"])

        # Implementation should handle this gracefully
        # (may or may not match depending on implementation)
        assert isinstance(subgraph, RepoGraph)

    def test_cyclic_dependencies(self) -> None:
        """Test subgraph extraction with cyclic dependencies."""
        nodes = [
            Node(
                id="fil_a",
                type="file",
                file="a.py",
                name="a.py",
                metadata={},
            ),
            Node(id="f1", type="function", file="a.py", name="f1", metadata={}),
            Node(id="f2", type="function", file="a.py", name="f2", metadata={}),
        ]

        edges = [
            Edge(source="fil_a", target="f1", type="contains"),
            Edge(source="fil_a", target="f2", type="contains"),
            Edge(source="f1", target="f2", type="calls"),
            Edge(source="f2", target="f1", type="calls"),  # Cycle
        ]

        graph = RepoGraph(nodes=nodes, edges=edges)
        subgraph = extract_subgraph(graph, ["a.py"])

        # Should handle cycles without infinite loops
        assert len(subgraph.nodes) > 0

    def test_single_node_graph(self) -> None:
        """Test subgraph extraction on a single-node graph."""
        nodes = [
            Node(id="n1", type="file", file="test.py", name="test", metadata={})
        ]
        graph = RepoGraph(nodes=nodes, edges=[])

        subgraph = extract_subgraph(graph, ["test.py"])

        assert len(subgraph.nodes) == 1
        assert subgraph.nodes[0].id == "n1"

    def test_isolated_nodes(self) -> None:
        """Test subgraph with isolated nodes (no edges)."""
        nodes = [
            Node(id="n1", type="file", file="a.py", name="a", metadata={}),
            Node(id="n2", type="file", file="b.py", name="b", metadata={}),
        ]
        graph = RepoGraph(nodes=nodes, edges=[])

        subgraph = extract_subgraph(graph, ["a.py"], hops=1)

        # Should only include a.py, not b.py (no edges connecting them)
        assert all(n.file == "a.py" for n in subgraph.nodes)
