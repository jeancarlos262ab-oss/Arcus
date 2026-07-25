"""Graph querying: Subgraph extraction for PR context analysis."""

from arcus.contracts import Edge, Node, RepoGraph


def extract_subgraph(
    graph: RepoGraph, changed_files: list[str], hops: int = 1
) -> RepoGraph:
    """
    Extract a subgraph containing changed files and their dependencies.

    This function filters the global repo graph to include only:
    - Nodes corresponding to changed files
    - Nodes that are `hops` edges away (default 1 hop for immediate dependencies)

    Used by Context Builder to create a focused context for PR analysis.

    Args:
        graph: The full RepoGraph to query.
        changed_files: List of file paths that changed in the PR.
        hops: Number of edges to traverse from changed files (default 1).

    Returns:
        A new RepoGraph containing relevant nodes and edges.

    Example:
        >>> full_graph = RepoGraph(...)
        >>> subgraph = extract_subgraph(full_graph, ["src/main.py", "src/utils.py"])
        >>> # Returns graph with main.py, utils.py, and all functions/classes they contain
    """
    # Normalize file paths for comparison
    changed_files_set = {str(f) for f in changed_files}

    # Step 1: Find all nodes related to changed files
    relevant_node_ids: set[str] = set()

    # Add nodes from changed files (file nodes and their children)
    for node in graph.nodes:
        if node.type == "file" and node.file in changed_files_set:
            # Add the file node itself
            relevant_node_ids.add(node.id)

    # Add all nodes contained within changed files
    for edge in graph.edges:
        if edge.type == "contains" and edge.source in relevant_node_ids:
            # File contains function/class
            relevant_node_ids.add(edge.target)

    # Step 2: Expand to dependencies (hops away)
    for hop in range(hops):
        new_nodes: set[str] = set()

        # Find all nodes that current relevant nodes depend on
        for edge in graph.edges:
            if edge.source in relevant_node_ids and edge.type != "contains":
                # This is a dependency edge (imports, calls, etc.)
                new_nodes.add(edge.target)

            # Also include reverse: nodes that depend on our changed files
            if edge.target in relevant_node_ids and edge.type != "contains":
                new_nodes.add(edge.source)

        relevant_node_ids.update(new_nodes)

    # Step 3: Build the subgraph with filtered nodes and edges
    subgraph_nodes = [node for node in graph.nodes if node.id in relevant_node_ids]

    subgraph_edges = [
        edge
        for edge in graph.edges
        if edge.source in relevant_node_ids and edge.target in relevant_node_ids
    ]

    return RepoGraph(nodes=subgraph_nodes, edges=subgraph_edges)


def find_nodes_by_file(graph: RepoGraph, file_path: str) -> list[Node]:
    """
    Find all nodes associated with a specific file.

    Args:
        graph: RepoGraph to search.
        file_path: File path to find nodes for.

    Returns:
        List of nodes in the file (functions, classes, methods, etc.)
    """
    return [node for node in graph.nodes if node.file == file_path]


def find_node_by_id(graph: RepoGraph, node_id: str) -> Node | None:
    """
    Find a node by its ID.

    Args:
        graph: RepoGraph to search.
        node_id: ID of the node to find.

    Returns:
        The node if found, None otherwise.
    """
    for node in graph.nodes:
        if node.id == node_id:
            return node
    return None


def find_edges_from_node(graph: RepoGraph, node_id: str) -> list[Edge]:
    """
    Find all edges originating from a specific node.

    Args:
        graph: RepoGraph to search.
        node_id: Source node ID.

    Returns:
        List of edges where this node is the source.
    """
    return [edge for edge in graph.edges if edge.source == node_id]


def find_edges_to_node(graph: RepoGraph, node_id: str) -> list[Edge]:
    """
    Find all edges pointing to a specific node.

    Args:
        graph: RepoGraph to search.
        node_id: Target node ID.

    Returns:
        List of edges where this node is the target.
    """
    return [edge for edge in graph.edges if edge.target == node_id]


def get_node_dependencies(
    graph: RepoGraph, node_id: str, hops: int = 1
) -> list[Node]:
    """
    Get all nodes that a given node depends on (transitively).

    Args:
        graph: RepoGraph to search.
        node_id: Source node to find dependencies for.
        hops: Number of hops to traverse (default 1).

    Returns:
        List of dependency nodes.
    """
    visited: set[str] = set()
    to_visit = [node_id]
    dependencies: set[str] = set()

    for _ in range(hops):
        next_visit = []
        for current_id in to_visit:
            if current_id in visited:
                continue
            visited.add(current_id)

            # Find edges from this node (excluding "contains" edges)
            for edge in graph.edges:
                if (
                    edge.source == current_id
                    and edge.type != "contains"
                    and edge.target not in visited
                ):
                    dependencies.add(edge.target)
                    next_visit.append(edge.target)

        to_visit = next_visit

    return [
        node for node in graph.nodes if node.id in dependencies
    ]


def get_node_dependents(
    graph: RepoGraph, node_id: str, hops: int = 1
) -> list[Node]:
    """
    Get all nodes that depend on a given node (reverse dependencies).

    Args:
        graph: RepoGraph to search.
        node_id: Target node to find dependents for.
        hops: Number of hops to traverse (default 1).

    Returns:
        List of dependent nodes.
    """
    visited: set[str] = set()
    to_visit = [node_id]
    dependents: set[str] = set()

    for _ in range(hops):
        next_visit = []
        for current_id in to_visit:
            if current_id in visited:
                continue
            visited.add(current_id)

            # Find edges to this node (excluding "contains" edges)
            for edge in graph.edges:
                if (
                    edge.target == current_id
                    and edge.type != "contains"
                    and edge.source not in visited
                ):
                    dependents.add(edge.source)
                    next_visit.append(edge.source)

        to_visit = next_visit

    return [
        node for node in graph.nodes if node.id in dependents
    ]
