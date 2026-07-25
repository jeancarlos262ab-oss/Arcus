"""Test that contract models can be imported and instantiated."""
import json
from datetime import datetime

import pytest

from arcus.contracts import (
    PipelineEnvelope,
    PRDetails,
    ContextSection,
    ConsistencySection,
    BugsSection,
    FixesSection,
    ReportSection,
    ContextConventions,
    ErrorDetail,
    Finding,
    Fix,
    Node,
    Edge,
    RepoGraph,
)


def test_pipeline_envelope_minimal():
    """Test creating a minimal valid PipelineEnvelope."""
    envelope = PipelineEnvelope(
        pipeline_run_id="test-run-1",
        created_at=datetime(2026, 7, 24, 12, 0, 0),
        pr=PRDetails(
            repo_full_name="owner/repo",
            pr_number=1,
            commit_sha="abc123",
            installation_id=12345,
            diff_ref="s3://bucket/diff.patch",
        ),
        context=ContextSection(status="ok"),
        consistency=ConsistencySection(status="ok"),
        bugs=BugsSection(status="ok"),
        fixes=FixesSection(status="ok"),
        report=ReportSection(status="ok"),
    )

    assert envelope.pipeline_run_id == "test-run-1"
    assert envelope.pr.pr_number == 1
    assert envelope.context.status == "ok"


def test_finding_with_fix():
    """Test creating a Finding with a Fix."""
    finding = Finding(
        id="finding-1",
        agent="bug_hunter",
        type="logic_bug",
        severity="high",
        file="src/main.py",
        line_start=10,
        line_end=15,
        title="Null pointer dereference",
        rationale="Variable not checked for None",
        evidence_refs=["src/config.py:5"],
        fix=Fix(
            description="Add None check",
            suggested_diff="+ if value is None:\n+     return",
            confidence="high",
        ),
    )

    assert finding.type == "logic_bug"
    assert finding.fix is not None
    assert finding.fix.confidence == "high"


def test_repo_graph():
    """Test creating a RepoGraph."""
    graph = RepoGraph(
        nodes=[
            Node(id="f1", type="file", file="main.py", name="main.py"),
            Node(id="fn1", type="function", file="main.py", name="process"),
        ],
        edges=[
            Edge(source="f1", target="fn1", type="contains"),
        ],
    )

    assert len(graph.nodes) == 2
    assert len(graph.edges) == 1
    assert graph.nodes[0].type == "file"


def test_envelope_from_dict():
    """Test loading envelope from JSON-like dict."""
    data = {
        "pipeline_run_id": "run-123",
        "created_at": "2026-07-24T12:00:00",
        "pr": {
            "repo_full_name": "owner/repo",
            "pr_number": 42,
            "commit_sha": "deadbeef",
            "installation_id": 99999,
            "diff_ref": "s3://bucket/diff.patch",
        },
        "context": {"status": "ok"},
        "consistency": {"status": "ok", "findings": []},
        "bugs": {"status": "ok", "findings": []},
        "fixes": {"status": "ok", "findings": []},
        "report": {"status": "ok"},
    }

    envelope = PipelineEnvelope(**data)
    assert envelope.pr.pr_number == 42
    assert envelope.context.status == "ok"


def test_envelope_with_error():
    """Test creating an envelope section with error."""
    section = BugsSection(
        status="failed",
        error=ErrorDetail(code="BEDROCK_TIMEOUT", message="Request timed out"),
    )

    assert section.status == "failed"
    assert section.error.code == "BEDROCK_TIMEOUT"
