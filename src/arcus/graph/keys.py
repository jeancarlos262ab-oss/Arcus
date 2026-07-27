"""Stable S3 keys for versioned repository graph artifacts."""

from __future__ import annotations


def repository_graph_key(repo_full_name: str, base_commit_sha: str) -> str:
    """Return the immutable graph key for one repository base commit."""

    return f"graphs/{repo_full_name}/commits/{base_commit_sha}.json"


def repository_graph_pointer_key(repo_full_name: str) -> str:
    """Return the compatibility key containing the most recently built graph."""

    return f"graphs/{repo_full_name}/main.json"
