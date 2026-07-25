"""Graph storage: JSON serialization for RepoGraph persistence and S3 integration."""
import json
from pathlib import Path
from typing import Any

from arcus.contracts import Edge, Node, RepoGraph


class GraphStore:
    """Store and retrieve RepoGraph from JSON format (S3-compatible)."""

    @staticmethod
    def to_json(graph: RepoGraph) -> str:
        """
        Serialize a RepoGraph to JSON string.

        Args:
            graph: RepoGraph instance to serialize.

        Returns:
            JSON string representation of the graph.
        """
        data = {
            "nodes": [
                {
                    "id": node.id,
                    "type": node.type,
                    "file": node.file,
                    "name": node.name,
                    "metadata": node.metadata,
                }
                for node in graph.nodes
            ],
            "edges": [
                {
                    "source": edge.source,
                    "target": edge.target,
                    "type": edge.type,
                }
                for edge in graph.edges
            ],
        }
        return json.dumps(data, indent=2)

    @staticmethod
    def from_json(json_str: str) -> RepoGraph:
        """
        Deserialize a RepoGraph from JSON string.

        Args:
            json_str: JSON string to deserialize.

        Returns:
            RepoGraph instance.

        Raises:
            json.JSONDecodeError: If JSON is invalid.
            ValueError: If graph structure is invalid.
        """
        data = json.loads(json_str)

        if not isinstance(data, dict):
            raise ValueError("JSON must be a dictionary")

        if "nodes" not in data or "edges" not in data:
            raise ValueError("JSON must contain 'nodes' and 'edges' keys")

        nodes = [
            Node(
                id=node_data["id"],
                type=node_data["type"],
                file=node_data["file"],
                name=node_data["name"],
                metadata=node_data.get("metadata", {}),
            )
            for node_data in data["nodes"]
        ]

        edges = [
            Edge(
                source=edge_data["source"],
                target=edge_data["target"],
                type=edge_data["type"],
            )
            for edge_data in data["edges"]
        ]

        return RepoGraph(nodes=nodes, edges=edges)

    @staticmethod
    def to_file(graph: RepoGraph, file_path: Path) -> None:
        """
        Write a RepoGraph to a JSON file.

        Args:
            graph: RepoGraph instance to write.
            file_path: Path where to write the JSON file.

        Raises:
            IOError: If file cannot be written.
        """
        json_str = GraphStore.to_json(graph)
        with open(file_path, "w") as f:
            f.write(json_str)

    @staticmethod
    def from_file(file_path: Path) -> RepoGraph:
        """
        Read a RepoGraph from a JSON file.

        Args:
            file_path: Path to the JSON file to read.

        Returns:
            RepoGraph instance.

        Raises:
            IOError: If file cannot be read.
            json.JSONDecodeError: If JSON is invalid.
            ValueError: If graph structure is invalid.
        """
        with open(file_path) as f:
            json_str = f.read()
        return GraphStore.from_json(json_str)

    @staticmethod
    def to_dict(graph: RepoGraph) -> dict[str, Any]:
        """
        Convert a RepoGraph to a dictionary (for S3 metadata compatibility).

        Args:
            graph: RepoGraph instance to convert.

        Returns:
            Dictionary representation of the graph.
        """
        return {
            "nodes": [
                {
                    "id": node.id,
                    "type": node.type,
                    "file": node.file,
                    "name": node.name,
                    "metadata": node.metadata,
                }
                for node in graph.nodes
            ],
            "edges": [
                {
                    "source": edge.source,
                    "target": edge.target,
                    "type": edge.type,
                }
                for edge in graph.edges
            ],
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> RepoGraph:
        """
        Convert a dictionary to a RepoGraph.

        Args:
            data: Dictionary containing 'nodes' and 'edges'.

        Returns:
            RepoGraph instance.

        Raises:
            ValueError: If dictionary structure is invalid.
        """
        if not isinstance(data, dict):
            raise ValueError("Data must be a dictionary")

        if "nodes" not in data or "edges" not in data:
            raise ValueError("Data must contain 'nodes' and 'edges' keys")

        nodes = [
            Node(
                id=node_data["id"],
                type=node_data["type"],
                file=node_data["file"],
                name=node_data["name"],
                metadata=node_data.get("metadata", {}),
            )
            for node_data in data["nodes"]
        ]

        edges = [
            Edge(
                source=edge_data["source"],
                target=edge_data["target"],
                type=edge_data["type"],
            )
            for edge_data in data["edges"]
        ]

        return RepoGraph(nodes=nodes, edges=edges)
