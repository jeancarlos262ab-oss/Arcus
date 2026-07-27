"""Ensure shared pipeline modules can be imported together."""

from arcus.agents.base import BaseAgent
from arcus.agents.runtime import artifacts, model, settings
from arcus.bedrock.client import BedrockClient
from arcus.config import Settings
from arcus.storage.artifacts import S3ArtifactStore
from arcus.storage.history import ReviewHistoryStore


def test_probe() -> None:
    assert all((BaseAgent, BedrockClient, Settings, S3ArtifactStore, ReviewHistoryStore, artifacts, model, settings))
