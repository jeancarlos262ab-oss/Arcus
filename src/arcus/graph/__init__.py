"""Lazy public API for graph construction, queries, and serialization."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from arcus.graph.builder import GraphBuilder, update_graph_incremental
    from arcus.graph.query import (
        extract_subgraph,
        find_links_from_node,
        find_links_to_node,
        find_node_by_id,
        find_nodes_by_file,
        get_node_dependencies,
        get_node_dependents,
    )
    from arcus.graph.store import GraphStore

__all__ = [
    "GraphBuilder",
    "GraphStore",
    "extract_subgraph",
    "find_links_from_node",
    "find_links_to_node",
    "find_node_by_id",
    "find_nodes_by_file",
    "get_node_dependencies",
    "get_node_dependents",
    "update_graph_incremental",
]


def __getattr__(name: str) -> object:
    """Load graph implementations only when callers request their public symbol."""

    if name in {"GraphBuilder", "update_graph_incremental"}:
        from arcus.graph.builder import GraphBuilder, update_graph_incremental

        return {
            "GraphBuilder": GraphBuilder,
            "update_graph_incremental": update_graph_incremental,
        }[name]
    if name == "GraphStore":
        from arcus.graph.store import GraphStore

        return GraphStore
    if name in {
        "extract_subgraph",
        "find_links_from_node",
        "find_links_to_node",
        "find_node_by_id",
        "find_nodes_by_file",
        "get_node_dependencies",
        "get_node_dependents",
    }:
        from arcus.graph.query import (
            extract_subgraph,
            find_links_from_node,
            find_links_to_node,
            find_node_by_id,
            find_nodes_by_file,
            get_node_dependencies,
            get_node_dependents,
        )

        return {
            "extract_subgraph": extract_subgraph,
            "find_links_from_node": find_links_from_node,
            "find_links_to_node": find_links_to_node,
            "find_node_by_id": find_node_by_id,
            "find_nodes_by_file": find_nodes_by_file,
            "get_node_dependencies": get_node_dependencies,
            "get_node_dependents": get_node_dependents,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
