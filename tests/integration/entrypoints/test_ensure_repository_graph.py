"""Moto integration coverage for lazy, idempotent repository graph bootstrap."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import boto3
from moto import mock_aws

from arcus.agents.context_builder import ContextBuilderAgent
from arcus.config import Settings
from arcus.contracts import AgentStatus, PipelineEnvelope
from arcus.entrypoints.ensure_repository_graph import EnsureRepositoryGraphHandler
from arcus.github.api import GitHubClient
from arcus.graph.bootstrap import RepositoryGraphBootstrapper
from arcus.graph.keys import repository_graph_key, repository_graph_pointer_key
from arcus.storage.artifacts import S3ArtifactStore

FIXTURE = Path(__file__).parents[2] / "fixtures" / "envelopes" / "initial.json"
REGION = "us-east-1"
BUCKET = "arcus-test-context-artifacts"
REPO = "acme/widgets"
BASE_SHA = "def456abc1237890"


class FakeGitHub(GitHubClient):
    """Return a valid private-repository archive without network I/O."""

    def __init__(self, archive: bytes) -> None:
        self._archive = archive
        self.download_count = 0

    def fetch_repository_archive(
        self,
        repo_full_name: str,
        commit_sha: str,
        installation_id: int,
    ) -> bytes:
        assert (repo_full_name, commit_sha, installation_id) == (
            REPO,
            BASE_SHA,
            123456,
        )
        self.download_count += 1
        return self._archive


def _archive() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "widgets-base/src/app.py",
            '"""Application."""\n\ndef run() -> str:\n    return "ok"\n',
        )
    return output.getvalue()


@mock_aws
def test_bootstrap_is_idempotent_and_context_builder_consumes_versioned_graph() -> None:
    s3 = boto3.client("s3", region_name=REGION)
    s3.create_bucket(Bucket=BUCKET)
    archive = _archive()
    github = FakeGitHub(archive)
    artifacts = S3ArtifactStore(
        BUCKET,
        client=s3,
        max_artifact_bytes=5_242_880,
    )
    settings = Settings(
        aws_region=REGION,
        bedrock_model_id="fixture-model",
    )
    bootstrapper = RepositoryGraphBootstrapper(
        github,
        artifacts,
        max_archive_bytes=len(archive),
        max_extracted_bytes=10_000,
        max_files=10,
    )
    handler = EnsureRepositoryGraphHandler(bootstrapper, settings)
    event = json.loads(FIXTURE.read_text(encoding="utf-8"))
    event["pr"]["changed_files"] = ["src/app.py"]

    first = handler.run(event)
    second = handler.run(event)
    first_envelope = PipelineEnvelope.model_validate(first)
    second_envelope = PipelineEnvelope.model_validate(second)

    assert first_envelope.context.status is AgentStatus.PENDING
    assert second_envelope.context.status is AgentStatus.PENDING
    assert github.download_count == 1
    keys = {
        item["Key"] for item in s3.list_objects_v2(Bucket=BUCKET).get("Contents", [])
    }
    assert keys == {
        repository_graph_key(REPO, BASE_SHA),
        repository_graph_pointer_key(REPO),
    }

    context_output = ContextBuilderAgent(artifacts, settings).run(first)
    context_envelope = PipelineEnvelope.model_validate(context_output)

    assert context_envelope.context.status is AgentStatus.OK
    assert context_envelope.context.graph_version == BASE_SHA
    assert context_envelope.context.graph_ref == (
        f"s3://{BUCKET}/{repository_graph_key(REPO, BASE_SHA)}"
    )
