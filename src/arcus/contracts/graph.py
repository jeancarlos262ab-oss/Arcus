"""Authoritative repository graph contract stored in S3."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from arcus.contracts.envelope import ContextConventions


class GraphNodeKind(StrEnum):
    """Kinds of source entities represented in a repository graph."""

    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"


class GraphEdgeType(StrEnum):
    """Supported relationships between graph nodes."""

    DEFINES = "defines"
    IMPORTS = "imports"
    CALLS = "calls"
    INHERITS = "inherits"


class GraphNode(BaseModel):
    """A source entity with a validated location in the repository."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    kind: GraphNodeKind
    file: str = Field(min_length=1)
    name: str = Field(min_length=1)
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    signature: str | None = None
    docstring_present: bool = False

    @model_validator(mode="after")
    def validate_source_range(self) -> GraphNode:
        """Reject graph nodes with inverted source spans."""

        if self.line_end < self.line_start:
            raise ValueError("line_end must be greater than or equal to line_start")
        return self


class GraphLink(BaseModel):
    """A directed, typed relationship between two graph nodes."""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1)
    target: str = Field(min_length=1)
    type: GraphEdgeType


class RepoGraph(BaseModel):
    """Versioned node-link representation persisted for repository context."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"] = "1"
    repo: str = Field(min_length=3, pattern=r"^[^/]+/[^/]+$")
    graph_version: str = Field(min_length=1)
    built_at: datetime
    language: Literal["python"] = "python"
    directed: Literal[True] = True
    conventions: ContextConventions = Field(default_factory=ContextConventions)
    nodes: list[GraphNode] = Field(default_factory=list)
    links: list[GraphLink] = Field(default_factory=list)
