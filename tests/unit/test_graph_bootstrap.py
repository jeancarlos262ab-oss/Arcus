"""Unit tests for safe, idempotent repository graph bootstrap."""

from __future__ import annotations

import io
import runpy
import stat
import zipfile
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import cast

import pytest

from arcus.errors import PermanentError
from arcus.graph.bootstrap import (
    RepositoryGraphBootstrapper,
    extract_repository_archive,
)
from arcus.graph.keys import repository_graph_key, repository_graph_pointer_key

SEED_SCRIPT = Path(__file__).parents[2] / "scripts" / "seed_graph.py"

REPO = "acme/widgets"
BASE_SHA = "def456abc1237890"
BUCKET = "arcus-test-context-artifacts"


class FakeGitHub:
    """Return one deterministic repository archive without network access."""

    def __init__(self, archive: bytes) -> None:
        self.archive = archive
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
        return self.archive


class InMemoryArtifacts:
    """Store graph mappings by key for deterministic cache behavior tests."""

    def __init__(self) -> None:
        self.values: dict[str, dict[str, object]] = {}

    def reference(self, key: str) -> str:
        return f"s3://{BUCKET}/{key}"

    def object_exists(self, key: str) -> bool:
        return key in self.values

    def put_json(self, key: str, payload: Mapping[str, object]) -> str:
        self.values[key] = dict(payload)
        return self.reference(key)

    def put_json_if_absent(
        self,
        key: str,
        payload: Mapping[str, object],
    ) -> tuple[str, bool]:
        if key in self.values:
            return self.reference(key), False
        self.values[key] = dict(payload)
        return self.reference(key), True

    def get_json(self, reference: str) -> Mapping[str, object]:
        prefix = f"s3://{BUCKET}/"
        assert reference.startswith(prefix)
        return self.values[reference.removeprefix(prefix)]


def _zip_bytes(files: Mapping[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, body in files.items():
            archive.writestr(name, body)
    return output.getvalue()


def _symlink_zip() -> bytes:
    output = io.BytesIO()
    link = zipfile.ZipInfo("widgets-base/src/link.py")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(link, b"target.py")
    return output.getvalue()


def test_bootstrap_builds_once_and_reuses_the_immutable_graph() -> None:
    archive = _zip_bytes(
        {
            "widgets-base/src/app.py": (
                b'"""Application."""\n\ndef run() -> str:\n    return "ok"\n'
            ),
            "widgets-base/README.md": b"not parsed",
        }
    )
    github = FakeGitHub(archive)
    artifacts = InMemoryArtifacts()
    bootstrapper = RepositoryGraphBootstrapper(
        github,
        artifacts,
        max_archive_bytes=len(archive),
        max_extracted_bytes=10_000,
        max_files=10,
    )

    first = bootstrapper.ensure(REPO, BASE_SHA, 123456)
    second = bootstrapper.ensure(REPO, BASE_SHA, 123456)

    immutable_key = repository_graph_key(REPO, BASE_SHA)
    assert first.cache_hit is False
    assert second.cache_hit is True
    assert first.graph_ref == f"s3://{BUCKET}/{immutable_key}"
    assert first.node_count == 2
    assert github.download_count == 1
    assert set(artifacts.values) == {
        immutable_key,
        repository_graph_pointer_key(REPO),
    }


def test_admin_seed_writes_the_pipeline_key_and_recovery_pointer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The emergency seed path must repair the same key normal onboarding reads."""

    (tmp_path / "app.py").write_text("def run() -> str:\n    return 'ok'\n")
    writes: list[tuple[str, Mapping[str, object]]] = []
    seed_graph = cast(Callable[..., str], runpy.run_path(SEED_SCRIPT)["seed_graph"])

    class FakeArtifactStore:
        def __init__(self, bucket_name: str) -> None:
            self._bucket_name = bucket_name

        def put_json(self, key: str, payload: Mapping[str, object]) -> str:
            writes.append((key, payload))
            return f"s3://{self._bucket_name}/{key}"

    monkeypatch.setitem(seed_graph.__globals__, "S3ArtifactStore", FakeArtifactStore)

    reference = seed_graph(tmp_path, REPO, BASE_SHA, BUCKET)

    assert reference == f"s3://{BUCKET}/{repository_graph_key(REPO, BASE_SHA)}"
    assert [key for key, _ in writes] == [
        repository_graph_key(REPO, BASE_SHA),
        repository_graph_pointer_key(REPO),
    ]
    assert writes[0][1]["graph_version"] == BASE_SHA


def test_archive_extraction_rejects_parent_traversal(tmp_path: Path) -> None:
    archive = _zip_bytes({"widgets-base/../../escape.py": b"pass\n"})

    with pytest.raises(PermanentError, match="unsafe path"):
        extract_repository_archive(
            archive,
            tmp_path,
            max_extracted_bytes=1_000,
            max_files=10,
        )

    assert not (tmp_path.parent / "escape.py").exists()


def test_archive_extraction_rejects_symbolic_links(tmp_path: Path) -> None:
    with pytest.raises(PermanentError, match="symbolic link"):
        extract_repository_archive(
            _symlink_zip(),
            tmp_path,
            max_extracted_bytes=1_000,
            max_files=10,
        )


def test_archive_limits_count_all_entries_and_declared_bytes(tmp_path: Path) -> None:
    too_many = _zip_bytes({"root/a.py": b"pass", "root/b.py": b"pass"})
    with pytest.raises(PermanentError, match="entry limit"):
        extract_repository_archive(
            too_many,
            tmp_path / "files",
            max_extracted_bytes=1_000,
            max_files=1,
        )

    oversized_unsupported_file = _zip_bytes({"root/large.bin": b"123456"})
    with pytest.raises(PermanentError, match="extracted byte limit"):
        extract_repository_archive(
            oversized_unsupported_file,
            tmp_path / "bytes",
            max_extracted_bytes=5,
            max_files=10,
        )
