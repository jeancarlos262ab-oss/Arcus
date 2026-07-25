"""Graph models for repository code structure representation."""
from typing import Any

from pydantic import BaseModel, Field


class Node(BaseModel):
    """A node in the repository code graph (function, class, file, etc.)."""

    id: str
    type: str  # "function", "class", "file", etc.
    file: str
    name: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class Edge(BaseModel):
    """An edge connecting two nodes in the graph."""

    source: str
    target: str
    type: str  # "calls", "imports", "defines", etc.


class RepoGraph(BaseModel):
    """Graph representation of a repository's code structure."""

    nodes: list[Node] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)
