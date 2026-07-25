"""Bedrock client for invoking Claude models with automatic retry and backoff."""
import json
from typing import Any

import boto3
from botocore.exceptions import ClientError
from tenacity import retry, stop_after_attempt, wait_exponential

# Bedrock Runtime client singleton
_bedrock_client: Any = None


def get_bedrock_client() -> Any:
    """Get or create a Bedrock Runtime client."""
    global _bedrock_client
    if _bedrock_client is None:
        _bedrock_client = boto3.client("bedrock-runtime")
    return _bedrock_client


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    reraise=True,
)
def invoke_claude(
    prompt: str,
    system_prompt: str = "Eres un revisor de código experto y riguroso.",
    model_id: str = "anthropic.claude-3-5-sonnet-20241022-v2:0",
    max_tokens: int = 4096,
    temperature: float = 0.0,
) -> str:
    """
    Invoke Anthropic Claude on AWS Bedrock with automatic retry and backoff.

    Args:
        prompt: User message to send to Claude.
        system_prompt: System context for the model.
        model_id: Model ID on Bedrock (default: Claude 3.5 Sonnet).
        max_tokens: Maximum tokens in response.
        temperature: Sampling temperature (0.0 = deterministic).

    Returns:
        The text response from Claude.

    Raises:
        ClientError: If the Bedrock API fails after retries.
    """
    client = get_bedrock_client()

    payload = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": system_prompt,
        "messages": [{"role": "user", "content": prompt}],
    }

    response = client.invoke_model(
        modelId=model_id,
        body=json.dumps(payload),
        contentType="application/json",
        accept="application/json",
    )

    response_body = json.loads(response["body"].read())
    return response_body["content"][0]["text"]
