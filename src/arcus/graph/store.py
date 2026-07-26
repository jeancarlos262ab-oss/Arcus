"""Serialization helpers for the canonical repository graph contract."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from arcus.contracts import RepoGraph


class GraphStore:
    """Serialize and validate repository graphs at persistence boundaries."""

    @staticmethod
    def to_json(graph: RepoGraph) -> str:
        """Serialize a graph as compact UTF-8 JSON."""

        return graph.model_dump_json()

    @staticmethod
    def from_json(json_text: str) -> RepoGraph:
        """Validate a graph loaded from untrusted JSON text."""

        return RepoGraph.model_validate_json(json_text)

    @staticmethod
    def to_file(graph: RepoGraph, file_path: Path) -> None:
        """Write a validated graph to a UTF-8 file."""

        file_path.write_text(GraphStore.to_json(graph), encoding="utf-8")

    @staticmethod
    def from_file(file_path: Path) -> RepoGraph:
        """Read and validate a graph from a UTF-8 file."""

        return GraphStore.from_json(file_path.read_text(encoding="utf-8"))

    @staticmethod
    def to_dict(graph: RepoGraph) -> dict[str, object]:
        """Return a JSON-compatible object suitable for S3ArtifactStore."""

        return graph.model_dump(mode="json")

    @staticmethod
    def from_dict(data: Mapping[str, object]) -> RepoGraph:
        """Validate a graph loaded from an SDK mapping."""

        return RepoGraph.model_validate(data)
