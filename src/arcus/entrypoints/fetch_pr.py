"""Fetch PR Lambda that persists a bounded diff before analysis."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from functools import lru_cache

from arcus.agents.base import parse_envelope, serialize_envelope
from arcus.agents.runtime import artifacts, settings
from arcus.config import Settings
from arcus.errors import AgentError
from arcus.github.api import GitHubClient
from arcus.github.runtime import github_client
from arcus.storage.artifacts import S3ArtifactStore

logger = logging.getLogger(__name__)


class FetchPRHandler:
    """Download capped PR data and attach only an S3 reference to the envelope."""

    def __init__(
        self,
        github: GitHubClient,
        artifact_store: S3ArtifactStore,
        runtime_settings: Settings,
    ) -> None:
        """Create a Fetch PR handler with mockable service boundaries."""

        self._github = github
        self._artifacts = artifact_store
        self._settings = runtime_settings

    def run(self, event: Mapping[str, object]) -> dict[str, object]:
        """Fetch, persist, and return a validated bounded envelope."""

        envelope = parse_envelope(event)
        try:
            pull_request = self._github.fetch_pull_request(
                envelope.pr.repo_full_name,
                envelope.pr.pr_number,
                envelope.pr.installation_id,
            )
            key = (
                f"prs/{envelope.pr.repo_full_name}/{envelope.pr.pr_number}/"
                f"{envelope.pr.commit_sha}/diff.patch"
            )
            envelope.pr.changed_files = pull_request.changed_files
            envelope.pr.diff_ref = self._artifacts.put_text(
                key,
                pull_request.diff,
                content_type="text/x-diff",
            )
            if pull_request.files_truncated or pull_request.diff_truncated:
                logger.warning(
                    "fetch_pr_artifacts_truncated",
                    extra={
                        "correlation_id": str(envelope.pipeline_run_id),
                        "agent": "fetch_pr",
                        "pr_id": (
                            f"{envelope.pr.repo_full_name}#{envelope.pr.pr_number}"
                        ),
                        "files_truncated": pull_request.files_truncated,
                        "diff_truncated": pull_request.diff_truncated,
                    },
                )
            return serialize_envelope(
                envelope,
                max_bytes=self._settings.max_envelope_bytes,
            )
        except Exception as error:
            logger.exception(
                "fetch_pr_failed",
                extra={
                    "correlation_id": str(envelope.pipeline_run_id),
                    "agent": "fetch_pr",
                    "pr_id": f"{envelope.pr.repo_full_name}#{envelope.pr.pr_number}",
                    "error_type": type(error).__name__,
                },
            )
            raise AgentError(
                "Fetch PR could not produce bounded artifacts",
                code="fetch_pr_failed",
            ) from error


@lru_cache(maxsize=1)
def _handler() -> FetchPRHandler:
    """Reuse GitHub and S3 clients across warm Lambda invocations."""

    return FetchPRHandler(github_client(), artifacts(), settings())


def lambda_handler(event: Mapping[str, object], _context: object) -> dict[str, object]:
    """Fetch bounded PR artifacts and return the shared envelope."""

    return _handler().run(event)
