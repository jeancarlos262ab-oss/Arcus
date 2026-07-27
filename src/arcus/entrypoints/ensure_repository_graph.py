"""Lambda boundary that lazily ensures base-commit repository graph context."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from functools import lru_cache

from arcus.agents.base import mark_section_failed, parse_envelope, serialize_envelope
from arcus.config import Settings
from arcus.errors import ArcusError
from arcus.graph.bootstrap import RepositoryGraphBootstrapper

logger = logging.getLogger(__name__)


class EnsureRepositoryGraphHandler:
    """Make graph context available while degrading safely to diff-only mode."""

    def __init__(
        self,
        bootstrapper: RepositoryGraphBootstrapper,
        runtime_settings: Settings,
    ) -> None:
        """Create a thin handler with injectable graph and configuration boundaries."""

        self._bootstrapper = bootstrapper
        self._settings = runtime_settings

    def run(self, event: Mapping[str, object]) -> dict[str, object]:
        """Ensure the base graph and return a complete validated envelope."""

        envelope = parse_envelope(event)
        pr = envelope.pr
        try:
            result = self._bootstrapper.ensure(
                pr.repo_full_name,
                pr.base_commit_sha,
                pr.installation_id,
            )
        except Exception as error:
            error_code = (
                error.code
                if isinstance(error, ArcusError)
                else "repository_graph_bootstrap_failed"
            )
            logger.exception(
                "repository_graph_bootstrap_failed",
                extra={
                    "correlation_id": str(envelope.pipeline_run_id),
                    "agent": "ensure_repository_graph",
                    "pr_id": f"{pr.repo_full_name}#{pr.pr_number}",
                    "error_code": error_code,
                    "error_type": type(error).__name__,
                },
            )
            mark_section_failed(
                envelope,
                "context",
                error_code,
                "Repository graph is unavailable; review continues in diff-only mode",
            )
        else:
            logger.info(
                "repository_graph_available",
                extra={
                    "correlation_id": str(envelope.pipeline_run_id),
                    "agent": "ensure_repository_graph",
                    "pr_id": f"{pr.repo_full_name}#{pr.pr_number}",
                    "graph_version": result.graph_version,
                    "cache_hit": result.cache_hit,
                    "node_count": result.node_count,
                    "link_count": result.link_count,
                },
            )
        return serialize_envelope(
            envelope,
            max_bytes=self._settings.max_envelope_bytes,
        )


@lru_cache(maxsize=1)
def _handler() -> EnsureRepositoryGraphHandler:
    """Reuse GitHub and S3 clients across warm Lambda invocations."""

    from arcus.agents.runtime import graph_artifacts, settings
    from arcus.github.runtime import github_client

    runtime_settings = settings()
    bootstrapper = RepositoryGraphBootstrapper(
        github_client(),
        graph_artifacts(),
        max_archive_bytes=runtime_settings.max_repository_archive_bytes,
        max_extracted_bytes=runtime_settings.max_repository_extracted_bytes,
        max_files=runtime_settings.max_repository_files,
    )
    return EnsureRepositoryGraphHandler(bootstrapper, runtime_settings)


def lambda_handler(event: Mapping[str, object], _context: object) -> dict[str, object]:
    """Ensure repository context and return the shared pipeline envelope."""

    return _handler().run(event)
