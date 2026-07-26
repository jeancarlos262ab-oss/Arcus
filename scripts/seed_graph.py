"""Build and upload the canonical graph consumed by Context Builder."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from arcus.graph import GraphBuilder
from arcus.storage.artifacts import S3ArtifactStore

logger = logging.getLogger(__name__)


def seed_graph(
    repository_path: Path,
    repo_full_name: str,
    graph_version: str,
    bucket_name: str,
) -> str:
    """Build one Python repository graph and persist its stable main reference.

    Args:
        repository_path: Local checkout root to parse.
        repo_full_name: GitHub ``owner/repository`` identifier.
        graph_version: Base commit represented by the graph.
        bucket_name: Deployed context-artifacts bucket.

    Returns:
        S3 URI consumed by Context Builder.
    """

    graph = GraphBuilder(
        repo_full_name,
        graph_version,
        root_path=repository_path,
    ).parse_directory(repository_path)
    reference = S3ArtifactStore(bucket_name).put_json(
        f"graphs/{repo_full_name}/main.json",
        graph.model_dump(mode="json"),
    )
    logger.info(
        "repository_graph_seeded",
        extra={
            "repo": repo_full_name,
            "graph_version": graph_version,
            "node_count": len(graph.nodes),
            "link_count": len(graph.links),
            "reference": reference,
        },
    )
    return reference


def main() -> int:
    """Parse CLI values and seed one graph into a configured dev/demo bucket."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository_path", type=Path)
    parser.add_argument("repo_full_name")
    parser.add_argument("graph_version")
    parser.add_argument("bucket_name")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    seed_graph(
        args.repository_path.resolve(),
        args.repo_full_name,
        args.graph_version,
        args.bucket_name,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
