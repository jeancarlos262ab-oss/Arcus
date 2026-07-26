"""Unit tests for incremental canonical graph updates."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from arcus.contracts import RepoGraph
from arcus.graph import GraphBuilder, update_graph_incremental


def _build(root: Path) -> RepoGraph:
    return GraphBuilder(
        "acme/widgets",
        "commit-one",
        root_path=root,
        built_at=datetime(2026, 7, 21, tzinfo=UTC),
    ).parse_directory(root)


def test_incremental_update_replaces_modified_file_and_version(tmp_path: Path) -> None:
    """Modified files should replace old entities while preserving other files."""

    source = tmp_path / "src"
    source.mkdir()
    first = source / "first.py"
    second = source / "second.py"
    first.write_text("def old_name() -> None:\n    pass\n", encoding="utf-8")
    second.write_text("def untouched() -> None:\n    pass\n", encoding="utf-8")
    graph = _build(tmp_path)
    first.write_text("def new_name() -> None:\n    pass\n", encoding="utf-8")

    updated = update_graph_incremental(
        graph,
        ["src/first.py"],
        root_path=tmp_path,
        graph_version="commit-two",
    )

    names = {node.name for node in updated.nodes}
    assert "new_name" in names
    assert "old_name" not in names
    assert "untouched" in names
    assert updated.graph_version == "commit-two"


def test_incremental_update_removes_deleted_nodes_and_links(tmp_path: Path) -> None:
    """Deleting a file must leave no dangling relationship endpoints."""

    source = tmp_path / "src"
    source.mkdir()
    target = source / "delete_me.py"
    target.write_text("def removed() -> None:\n    pass\n", encoding="utf-8")
    graph = _build(tmp_path)

    updated = update_graph_incremental(
        graph,
        [],
        ["src/delete_me.py"],
        root_path=tmp_path,
    )

    identifiers = {node.id for node in updated.nodes}
    assert not identifiers
    assert updated.links == []
