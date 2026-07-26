"""Unit tests for the Bedrock Converse adapter."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError, NoCredentialsError

from arcus.bedrock.client import (
    BedrockClient,
    extract_text,
    parse_findings,
    parse_json_response,
)
from arcus.config import Settings, get_settings
from arcus.contracts import FixBatch
from arcus.errors import BedrockResponseError, PermanentError, TransientError

FIXTURE_DIR = Path(__file__).parents[2] / "fixtures" / "bedrock"


def _load_fixture(name: str) -> dict[str, object]:
    """Load one shared Converse fixture as an untrusted SDK response."""

    payload = json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_invoke_model_uses_configured_model_and_extracts_text() -> None:
    """The adapter should hide the Converse envelope from downstream agents."""

    runtime_client = Mock()
    runtime_client.converse.return_value = _load_fixture("bug_hunter_response.json")
    client = BedrockClient(
        runtime_client=runtime_client,
        settings=Settings(aws_region="eu-west-1", bedrock_model_id="configured-model"),
    )

    result = client.invoke_model("Review this diff")

    assert '"findings"' in result
    runtime_client.converse.assert_called_once_with(
        modelId="configured-model",
        messages=[{"role": "user", "content": [{"text": "Review this diff"}]}],
        inferenceConfig={"maxTokens": 1200, "temperature": 0.0},
    )


def test_transient_bedrock_error_is_retried() -> None:
    """Throttling should retry once and succeed without sleeping in the test."""

    runtime_client = Mock()
    throttled = ClientError(
        {"Error": {"Code": "ThrottlingException", "Message": "try again"}},
        "Converse",
    )
    runtime_client.converse.side_effect = [
        throttled,
        _load_fixture("consistency_checker_response.json"),
    ]
    client = BedrockClient(
        runtime_client=runtime_client,
        max_attempts=2,
        base_delay=0,
        max_delay=0,
    )

    result = client.invoke_model("Review this diff")

    assert '"findings"' in result
    assert runtime_client.converse.call_count == 2


def test_non_retryable_bedrock_error_is_not_retried() -> None:
    """Authentication and request errors must surface immediately."""

    runtime_client = Mock()
    runtime_client.converse.side_effect = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "denied"}},
        "Converse",
    )
    client = BedrockClient(runtime_client=runtime_client)

    with pytest.raises(PermanentError, match="rejected"):
        client.invoke_model("Review this diff")

    runtime_client.converse.assert_called_once()


def test_findings_fixture_is_validated_into_contract_models() -> None:
    """Model JSON should become Finding objects before agents use it."""

    response = _load_fixture("consistency_checker_response.json")
    text = extract_text(response)

    findings = parse_findings(text)

    assert len(findings) == 1
    assert findings[0].title.startswith("Configuration loader")


def test_fix_fixture_is_validated_into_a_bounded_batch_contract() -> None:
    """Fix Suggester returns all existing-ID assignments in one model call."""

    response = _load_fixture("fix_suggester_response.json")
    text = extract_text(response)

    batch = FixBatch.model_validate(parse_json_response(text))

    assert len(batch.fixes) == 2
    assert batch.fixes[1].fix.confidence.value == "high"
    assert "Clamp" in batch.fixes[1].fix.description


def test_malformed_findings_response_is_rejected() -> None:
    """Malformed model output must never reach an agent as an unchecked dict."""

    with pytest.raises(BedrockResponseError, match="valid JSON"):
        parse_findings("not json")


def test_default_client_uses_nova_in_us_east_1_without_real_aws(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The zero-config path should create the required regional Converse client."""

    runtime_client = Mock()
    runtime_client.converse.return_value = _load_fixture("bug_hunter_response.json")
    client_factory = Mock(return_value=runtime_client)
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("BEDROCK_MODEL_ID", raising=False)
    monkeypatch.setattr("arcus.bedrock.client.boto3.client", client_factory)
    get_settings.cache_clear()

    try:
        client = BedrockClient()
        client.invoke_model("Review this diff")
    finally:
        get_settings.cache_clear()

    client_call = client_factory.call_args
    assert client_call.args == ("bedrock-runtime",)
    assert client_call.kwargs["region_name"] == "us-east-1"
    sdk_config = client_call.kwargs["config"]
    assert sdk_config.retries == {"mode": "standard", "total_max_attempts": 1}
    assert sdk_config.connect_timeout == 2
    assert sdk_config.read_timeout == 10
    assert (
        runtime_client.converse.call_args.kwargs["modelId"]
        == "us.amazon.nova-2-lite-v1:0"
    )


def test_default_retry_policy_uses_five_attempts_with_full_jitter() -> None:
    """Default retries should use four exponentially growing full-jitter delays."""

    runtime_client = Mock()
    throttled = ClientError(
        {"Error": {"Code": "ThrottlingException", "Message": "try again"}},
        "Converse",
    )
    runtime_client.converse.side_effect = [throttled] * 5
    jitter_ranges: list[tuple[float, float]] = []
    sleeps: list[float] = []

    def choose_upper_bound(lower: float, upper: float) -> float:
        jitter_ranges.append((lower, upper))
        return upper

    client = BedrockClient(
        runtime_client=runtime_client,
        sleep=sleeps.append,
        random_uniform=choose_upper_bound,
    )

    with pytest.raises(TransientError, match="temporarily"):
        client.invoke_model("Review this diff")

    assert runtime_client.converse.call_count == 5
    assert jitter_ranges == [(0.0, 1.0), (0.0, 2.0), (0.0, 4.0), (0.0, 8.0)]
    assert sleeps == [1.0, 2.0, 4.0, 8.0]


def test_retry_delay_ceiling_is_capped_at_eight_seconds() -> None:
    """Longer override policies must keep all attempts inside the Lambda deadline."""

    runtime_client = Mock()
    throttled = ClientError(
        {"Error": {"Code": "ThrottlingException", "Message": "try again"}},
        "Converse",
    )
    runtime_client.converse.side_effect = [throttled] * 7
    jitter_ceilings: list[float] = []

    def choose_no_delay(_lower: float, upper: float) -> float:
        jitter_ceilings.append(upper)
        return 0.0

    client = BedrockClient(
        runtime_client=runtime_client,
        max_attempts=7,
        sleep=lambda _delay: None,
        random_uniform=choose_no_delay,
    )

    with pytest.raises(TransientError):
        client.invoke_model("Review this diff")

    assert jitter_ceilings == [1.0, 2.0, 4.0, 8.0, 8.0, 8.0]


def test_transient_transport_error_is_retried() -> None:
    """A network connection failure should retry through the same policy."""

    runtime_client = Mock()
    runtime_client.converse.side_effect = [
        EndpointConnectionError(
            endpoint_url="https://bedrock-runtime.us-east-1.amazonaws.com"
        ),
        _load_fixture("consistency_checker_response.json"),
    ]
    client = BedrockClient(
        runtime_client=runtime_client,
        max_attempts=2,
        base_delay=0,
        max_delay=0,
    )

    result = client.invoke_model("Review this diff")

    assert '"findings"' in result
    assert runtime_client.converse.call_count == 2


def test_permanent_sdk_error_is_not_retried() -> None:
    """Missing credentials are an auth failure, not a transient transport failure."""

    runtime_client = Mock()
    runtime_client.converse.side_effect = NoCredentialsError()
    client = BedrockClient(runtime_client=runtime_client)

    with pytest.raises(PermanentError, match="SDK"):
        client.invoke_model("Review this diff")

    runtime_client.converse.assert_called_once()


def test_malformed_converse_envelope_is_rejected() -> None:
    """An incomplete provider envelope must fail before text reaches an agent."""

    with pytest.raises(BedrockResponseError, match="output.message"):
        extract_text({"output": {}})


def test_valid_json_that_violates_finding_contract_is_rejected() -> None:
    """Syntactically valid generated JSON still must pass the Pydantic contract."""

    with pytest.raises(BedrockResponseError, match="contract validation"):
        parse_findings('{"findings": [{"unexpected": true}]}')


def test_completion_log_omits_prompt_and_response(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Operational metrics must not expose review input or generated model content."""

    runtime_client = Mock()
    runtime_client.converse.return_value = _load_fixture("bug_hunter_response.json")
    client = BedrockClient(runtime_client=runtime_client)
    prompt = "PRIVATE DIFF CONTENT"

    with caplog.at_level("INFO", logger="arcus.bedrock.client"):
        response_text = client.invoke_model(prompt)

    assert prompt not in caplog.text
    assert response_text not in caplog.text


def test_prompt_and_output_limits_reject_before_converse() -> None:
    """Over-budget requests must not consume a Bedrock invocation."""

    runtime_client = Mock()
    client = BedrockClient(
        runtime_client=runtime_client,
        settings=Settings(
            aws_region="us-east-1",
            bedrock_model_id="model",
            max_output_tokens=100,
            max_prompt_bytes=4,
        ),
    )

    with pytest.raises(PermanentError, match="prompt exceeds"):
        client.invoke_model("ééé")
    with pytest.raises(PermanentError, match="between 1 and 100"):
        client.invoke_model("ok", max_tokens=101)

    runtime_client.converse.assert_not_called()


def test_findings_limit_rejects_oversized_model_response() -> None:
    """The parser must reject rather than silently truncate generated findings."""

    finding = {
        "id": "323e4567-e89b-42d3-a456-426614174002",
        "agent": "bug_hunter",
        "type": "logic_bug",
        "severity": "high",
        "file": "src/a.py",
        "line_start": 1,
        "line_end": 1,
        "title": "Bug",
        "rationale": "Reason",
        "evidence_refs": [],
        "fix": None,
    }

    with pytest.raises(BedrockResponseError, match="exceeds the limit"):
        parse_findings(json.dumps({"findings": [finding, finding]}), max_findings=1)
