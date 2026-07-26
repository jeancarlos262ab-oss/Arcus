"""Queries over the canonical repository node-link graph."""

from __future__ import annotations

from arcus.contracts import GraphLink, GraphNode, RepoGraph


def extract_subgraph(
    graph: RepoGraph,
    changed_files: list[str],
    hops: int = 1,
) -> RepoGraph:
    """Extract changed-file nodes plus dependencies and dependents.

    Args:
        graph: Complete repository graph loaded from S3.
        changed_files: Repository-relative paths changed by the pull request.
        hops: Number of relationship expansions to include.

    Returns:
        A graph preserving source metadata with only relevant nodes and links.
    """

    if hops < 0:
        raise ValueError("hops cannot be negative")
    changed = {path.replace("\\", "/") for path in changed_files}
    relevant = {
        node.id for node in graph.nodes if node.file.replace("\\", "/") in changed
    }

    for _ in range(hops):
        expanded = set(relevant)
        for link in graph.links:
            if link.source in relevant:
                expanded.add(link.target)
            if link.target in relevant:
                expanded.add(link.source)
        relevant = expanded

    nodes = [node for node in graph.nodes if node.id in relevant]
    links = [
        link
        for link in graph.links
        if link.source in relevant and link.target in relevant
    ]
    return graph.model_copy(update={"nodes": nodes, "links": links})


def find_nodes_by_file(graph: RepoGraph, file_path: str) -> list[GraphNode]:
    """Return all graph nodes declared in one repository-relative path."""

    normalized = file_path.replace("\\", "/")
    return [node for node in graph.nodes if node.file.replace("\\", "/") == normalized]


def find_node_by_id(graph: RepoGraph, node_id: str) -> GraphNode | None:
    """Return a graph node by ID, or ``None`` when absent."""

    return next((node for node in graph.nodes if node.id == node_id), None)


def find_links_from_node(graph: RepoGraph, node_id: str) -> list[GraphLink]:
    """Return outgoing links from one node."""

    return [link for link in graph.links if link.source == node_id]


def find_links_to_node(graph: RepoGraph, node_id: str) -> list[GraphLink]:
    """Return incoming links to one node."""

    return [link for link in graph.links if link.target == node_id]


def get_node_dependencies(
    graph: RepoGraph,
    node_id: str,
    hops: int = 1,
) -> list[GraphNode]:
    """Return nodes reachable through outgoing links within ``hops``."""

    return _traverse(graph, node_id, hops=hops, reverse=False)


def get_node_dependents(
    graph: RepoGraph,
    node_id: str,
    hops: int = 1,
) -> list[GraphNode]:
    """Return nodes reaching the target through incoming links."""

    return _traverse(graph, node_id, hops=hops, reverse=True)


def _traverse(
    graph: RepoGraph,
    node_id: str,
    *,
    hops: int,
    reverse: bool,
) -> list[GraphNode]:
    """Traverse links in one direction without returning the origin."""

    if hops < 0:
        raise ValueError("hops cannot be negative")
    visited = {node_id}
    frontier = {node_id}
    found: set[str] = set()
    for _ in range(hops):
        next_frontier: set[str] = set()
        for link in graph.links:
            source = link.target if reverse else link.source
            target = link.source if reverse else link.target
            if source in frontier and target not in visited:
                next_frontier.add(target)
                found.add(target)
        visited.update(next_frontier)
        frontier = next_frontier
    return [node for node in graph.nodes if node.id in found]
