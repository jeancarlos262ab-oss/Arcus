"""Contract checks for the Step Functions pipeline definition."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PIPELINE = Path(__file__).parents[2] / "infra" / "statemachine" / "pipeline.asl.json"


def _states() -> dict[str, dict[str, Any]]:
    definition = json.loads(PIPELINE.resolve().read_text(encoding="utf-8"))
    return definition["States"]


def test_failed_context_skips_analysis_and_reports() -> None:
    states = _states()
    skip_state = states["SkipAnalysisAfterContextFailure"]

    assert states["RepositoryGraphAvailable"]["Choices"][0]["Next"] == (
        "SkipAnalysisAfterContextFailure"
    )
    assert states["ContextBuilder"]["Next"] == "ContextAvailable"
    assert states["ContextAvailable"]["Choices"][0]["Next"] == (
        "SkipAnalysisAfterContextFailure"
    )
    assert states["MarkRepositoryGraphBootstrapFailed"]["Next"] == (
        "SkipAnalysisAfterContextFailure"
    )
    assert states["MarkContextBuilderFailed"]["Next"] == (
        "SkipAnalysisAfterContextFailure"
    )
    assert skip_state["Next"] == "Reporter"
    for section_name in ("consistency", "bugs", "fixes"):
        assert skip_state["Parameters"][section_name]["status"] == "skipped"
