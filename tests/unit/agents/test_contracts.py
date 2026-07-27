"""Contract tests for every real pipeline stage."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import cast
from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError

from arcus.agents.bug_hunter import BugHunterAgent
from arcus.agents.consistency_checker import ConsistencyCheckerAgent
from arcus.agents.context_builder import ContextBuilderAgent
from arcus.agents.fix_suggester import FixSuggesterAgent
from arcus.agents.reporter import ReporterAgent
from arcus.bedrock.client import BedrockClient
from arcus.config import Settings
from arcus.contracts import AgentStatus, PipelineEnvelope
from arcus.entrypoints.ensure_repository_graph import EnsureRepositoryGraphHandler
from arcus.entrypoints.fetch_pr import FetchPRHandler
from arcus.github.api import GitHubClient, PullRequestData
from arcus.graph.bootstrap import GraphBootstrapResult, RepositoryGraphBootstrapper
from arcus.storage.artifacts import S3ArtifactStore
from arcus.storage.history import ReviewHistoryStore

FIXTURES = Path(__file__).parents[2] / "fixtures"


class FakeArtifacts(S3ArtifactStore):
    """In-memory artifact boundary used by stage contract tests."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self._bucket_name = "arcus-dev-context-artifacts"

    def put_text(self, key: str, text: str, *, content_type: str = "text/plain") -> str:
        self.values[key] = text
        return f"s3://arcus-dev-context-artifacts/{key}"

    def put_json(self, key: str, payload: Mapping[str, object]) -> str:
        self.values[key] = json.dumps(payload)
        return f"s3://arcus-dev-context-artifacts/{key}"

    def get_text(self, reference: str) -> str:
        if reference.endswith("diff.patch"):
            return (FIXTURES / "prs" / "example.diff.patch").read_text(encoding="utf-8")
        return (FIXTURES / "graphs" / "example_repo_graph.json").read_text(
            encoding="utf-8"
        )


class FakeGitHub(GitHubClient):
    """Deterministic GitHub boundary for Fetch PR and Reporter."""

    def __init__(self) -> None:
        """Skip production transport construction for this in-memory fake."""

    def fetch_pull_request(
        self, repo_full_name: str, pr_number: int, installation_id: int
    ) -> PullRequestData:
        return PullRequestData(
            changed_files=["src/config.py", "tests/test_config.py"],
            diff=(FIXTURES / "prs" / "example.diff.patch").read_text(encoding="utf-8"),
            files_truncated=False,
            diff_truncated=False,
        )

    def upsert_review_comment(
        self,
        repo_full_name: str,
        pr_number: int,
        installation_id: int,
        markdown: str,
    ) -> str:
        assert "Arcus review" in markdown
        return "https://github.com/acme/widgets/pull/42#issuecomment-1001"


class FakeHistory(ReviewHistoryStore):
    """Capture Reporter history writes without DynamoDB."""

    def __init__(self) -> None:
        self.written: PipelineEnvelope | None = None

    def put(self, envelope: PipelineEnvelope) -> None:
        self.written = envelope


class FailingHistory(FakeHistory):
    """Simulate a terminal Reporter side-effect failure."""

    def put(self, envelope: PipelineEnvelope) -> None:
        raise RuntimeError("history unavailable")


class LargeDiffArtifacts(FakeArtifacts):
    """Return an oversized diff to exercise deterministic prompt budgeting."""

    def get_text(self, reference: str) -> str:
        if reference.endswith("diff.patch"):
            return "+ oversized change\n" * 20_000
        return super().get_text(reference)


def _settings(*, max_prompt_bytes: int = 60_000) -> Settings:
    return Settings(
        aws_region="us-east-1",
        bedrock_model_id="fixture-model",
        max_output_tokens=1200,
        max_prompt_bytes=max_prompt_bytes,
        max_findings_per_stage=10,
        max_findings_total=10,
        max_changed_files=50,
        max_diff_bytes=524_288,
        max_envelope_bytes=240_000,
        max_ai_operations_per_run=3,
    )


def _envelope(name: str) -> dict[str, object]:
    payload = json.loads((FIXTURES / "envelopes" / name).read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _bedrock(
    fixture_name: str, *, runtime_settings: Settings | None = None
) -> tuple[BedrockClient, Mock]:
    response = json.loads(
        (FIXTURES / "bedrock" / fixture_name).read_text(encoding="utf-8")
    )
    runtime = Mock()
    runtime.converse.return_value = response
    return BedrockClient(
        runtime_client=runtime,
        settings=runtime_settings or _settings(),
    ), runtime


def _invoked_prompt(runtime: Mock) -> str:
    """Return the user prompt passed through the mocked Converse boundary."""

    prompt = runtime.converse.call_args.kwargs["messages"][0]["content"][0]["text"]
    assert isinstance(prompt, str)
    return prompt


@pytest.mark.contract
def test_fetch_pr_produces_a_valid_bounded_envelope() -> None:
    artifacts = FakeArtifacts()
    handler = FetchPRHandler(FakeGitHub(), artifacts, _settings())

    output = handler.run(_envelope("initial.json"))
    envelope = PipelineEnvelope.model_validate(output)

    assert envelope.pr.changed_files == ["src/config.py", "tests/test_config.py"]
    assert envelope.pr.diff_ref is not None
    assert len(json.dumps(output).encode()) < _settings().max_envelope_bytes


@pytest.mark.contract
def test_ensure_repository_graph_preserves_a_valid_envelope() -> None:
    bootstrapper = Mock(spec=RepositoryGraphBootstrapper)
    bootstrapper.ensure.return_value = GraphBootstrapResult(
        graph_ref=(
            "s3://arcus-dev-context-artifacts/graphs/acme/widgets/"
            "commits/def456abc1237890.json"
        ),
        graph_version="def456abc1237890",
        cache_hit=False,
        node_count=3,
        link_count=2,
    )
    handler = EnsureRepositoryGraphHandler(bootstrapper, _settings())

    output = handler.run(_envelope("initial.json"))
    envelope = PipelineEnvelope.model_validate(output)

    assert envelope.context.status is AgentStatus.PENDING
    bootstrapper.ensure.assert_called_once_with(
        "acme/widgets",
        "def456abc1237890",
        123456,
    )


@pytest.mark.contract
def test_context_builder_produces_a_valid_envelope() -> None:
    artifacts = FakeArtifacts()
    event = _envelope("initial.json")
    pr = cast(dict[str, object], event["pr"])
    pr["changed_files"] = ["src/config.py"]
    agent = ContextBuilderAgent(artifacts, _settings())

    output = agent.run(event)
    envelope = PipelineEnvelope.model_validate(output)

    assert envelope.context.status is AgentStatus.OK
    assert envelope.context.relevant_subgraph_ref is not None


@pytest.mark.contract
def test_consistency_checker_produces_a_valid_envelope_with_one_call() -> None:
    model, runtime = _bedrock("consistency_checker_response.json")
    agent = ConsistencyCheckerAgent(
        model=model,
        artifact_store=FakeArtifacts(),
        runtime_settings=_settings(),
    )

    output = agent.run(_envelope("context_builder.json"))
    envelope = PipelineEnvelope.model_validate(output)

    assert envelope.consistency.status is AgentStatus.OK
    assert len(envelope.consistency.findings) == 1
    runtime.converse.assert_called_once()
    assert "src/config.py::load_config" in _invoked_prompt(runtime)


@pytest.mark.contract
def test_bug_hunter_produces_a_valid_envelope_with_one_call() -> None:
    model, runtime = _bedrock("bug_hunter_response.json")
    agent = BugHunterAgent(
        model=model,
        artifact_store=FakeArtifacts(),
        runtime_settings=_settings(),
    )

    output = agent.run(_envelope("consistency_checker.json"))
    envelope = PipelineEnvelope.model_validate(output)

    assert envelope.bugs.status is AgentStatus.OK
    assert len(envelope.bugs.findings) == 1
    runtime.converse.assert_called_once()
    assert "src/config.py::load_config" in _invoked_prompt(runtime)


@pytest.mark.contract
def test_fix_suggester_batches_all_findings_into_one_call() -> None:
    model, runtime = _bedrock("fix_suggester_response.json")
    agent = FixSuggesterAgent(model, _settings())

    output = agent.run(_envelope("bug_hunter.json"))
    envelope = PipelineEnvelope.model_validate(output)

    assert envelope.fixes.status is AgentStatus.OK
    assert len(envelope.fixes.findings) == 2
    assert all(finding.fix is not None for finding in envelope.fixes.findings)
    runtime.converse.assert_called_once()


@pytest.mark.contract
def test_reporter_produces_a_valid_envelope_and_one_history_row() -> None:
    history = FakeHistory()
    agent = ReporterAgent(FakeGitHub(), history, _settings())

    output = agent.run(_envelope("fix_suggester.json"))
    envelope = PipelineEnvelope.model_validate(output)

    assert envelope.report.status is AgentStatus.OK
    assert envelope.report.comment_url is not None
    assert history.written is not None


def test_reporter_side_effect_failure_escapes_the_lambda_boundary() -> None:
    """A failed final write must make Step Functions take its failure path."""

    agent = ReporterAgent(FakeGitHub(), FailingHistory(), _settings())

    with pytest.raises(RuntimeError, match="history unavailable"):
        agent.run(_envelope("fix_suggester.json"))


def test_oversized_diff_is_bounded_without_skipping_analysis() -> None:
    """Fetched artifacts larger than the model budget should be truncated safely."""

    runtime_settings = _settings(max_prompt_bytes=2_000)
    model, runtime = _bedrock(
        "consistency_checker_response.json",
        runtime_settings=runtime_settings,
    )
    agent = ConsistencyCheckerAgent(
        model=model,
        artifact_store=LargeDiffArtifacts(),
        runtime_settings=runtime_settings,
    )

    output = agent.run(_envelope("context_builder.json"))
    envelope = PipelineEnvelope.model_validate(output)
    prompt = _invoked_prompt(runtime)

    assert envelope.consistency.status is AgentStatus.OK
    assert len(prompt.encode("utf-8")) <= runtime_settings.max_prompt_bytes
    assert "...[truncated]" in prompt
    assert "src/config.py" in prompt


@pytest.mark.contract
def test_exhausted_bedrock_retry_degrades_without_escaping_agent() -> None:
    throttled = ClientError(
        {"Error": {"Code": "ThrottlingException", "Message": "try again"}},
        "Converse",
    )
    runtime = Mock()
    runtime.converse.side_effect = [throttled] * 5
    model = BedrockClient(
        runtime_client=runtime,
        settings=_settings(),
        base_delay=0,
        max_delay=0,
    )
    agent = BugHunterAgent(
        model=model,
        artifact_store=FakeArtifacts(),
        runtime_settings=_settings(),
    )

    output = agent.run(_envelope("consistency_checker.json"))
    envelope = PipelineEnvelope.model_validate(output)

    assert envelope.bugs.status is AgentStatus.FAILED
    assert envelope.bugs.error is not None
    assert runtime.converse.call_count == 5
