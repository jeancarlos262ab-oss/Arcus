"""Context Builder agent Lambda."""

from __future__ import annotations

import logging
from functools import lru_cache

from arcus.agents.base import BaseAgent
from arcus.agents.runtime import graph_artifacts, settings
from arcus.config import Settings
from arcus.contracts import AgentStatus, ContextSection, PipelineEnvelope, RepoGraph
from arcus.graph.keys import repository_graph_key
from arcus.graph.query import extract_subgraph
from arcus.storage.artifacts import S3ArtifactStore

logger = logging.getLogger(__name__)


class ContextBuilderAgent(BaseAgent):
    """Load an automatically cached graph and persist PR-specific context."""

    section_name = "context"
    failure_code = "context_builder_failed"

    def __init__(
        self,
        artifact_store: S3ArtifactStore,
        runtime_settings: Settings,
    ) -> None:
        """Create the stage with a bounded artifact store."""

        super().__init__(runtime_settings)
        self._artifacts = artifact_store

    def process(self, envelope: PipelineEnvelope) -> PipelineEnvelope:
        """Attach persisted graph references and detected conventions."""

        pr = envelope.pr
        graph_key = repository_graph_key(pr.repo_full_name, pr.base_commit_sha)
        graph_ref = self._artifacts.reference(graph_key)
        graph = RepoGraph.model_validate(self._artifacts.get_json(graph_ref))
        if graph.repo != pr.repo_full_name:
            raise ValueError("repository graph does not match the pull request")
        if graph.graph_version != pr.base_commit_sha:
            raise ValueError("repository graph does not match the PR base commit")

        subgraph = extract_subgraph(graph, pr.changed_files, hops=1)
        subgraph_key = (
            f"prs/{pr.repo_full_name}/{pr.pr_number}/{pr.commit_sha}/subgraph.json"
        )
        subgraph_ref = self._artifacts.put_json(
            subgraph_key,
            subgraph.model_dump(mode="json"),
        )
        envelope.context = ContextSection(
            status=AgentStatus.OK,
            graph_ref=graph_ref,
            graph_version=graph.graph_version,
            relevant_subgraph_ref=subgraph_ref,
            conventions=graph.conventions,
            ran_diff_only=not subgraph.nodes,
        )
        logger.info(
            "context_built",
            extra={
                "correlation_id": str(envelope.pipeline_run_id),
                "agent": self.section_name,
                "pr_id": f"{pr.repo_full_name}#{pr.pr_number}",
                "node_count": len(subgraph.nodes),
                "link_count": len(subgraph.links),
            },
        )
        return envelope


@lru_cache(maxsize=1)
def _agent() -> ContextBuilderAgent:
    """Reuse the stage and AWS clients across warm invocations."""

    return ContextBuilderAgent(graph_artifacts(), settings())


def lambda_handler(event: dict[str, object], _context: object) -> dict[str, object]:
    """Run Context Builder for one validated pipeline envelope."""

    return _agent().run(event)
