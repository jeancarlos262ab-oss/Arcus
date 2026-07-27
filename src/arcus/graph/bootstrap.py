"""Safe, bounded bootstrap of repository graphs from GitHub ZIP archives."""

from __future__ import annotations

import io
import stat
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from arcus.contracts import RepoGraph
from arcus.errors import PermanentError
from arcus.graph.keys import repository_graph_key, repository_graph_pointer_key
from arcus.graph.store import GraphStore

if TYPE_CHECKING:
    from arcus.github.api import GitHubClient
    from arcus.storage.artifacts import S3ArtifactStore

_COPY_CHUNK_BYTES = 64 * 1024


@dataclass(frozen=True, slots=True)
class GraphBootstrapResult:
    """Describe the graph made available to the next pipeline stage."""

    graph_ref: str
    graph_version: str
    cache_hit: bool
    node_count: int
    link_count: int


class RepositoryGraphBootstrapper:
    """Create an immutable base-commit graph when the S3 cache is empty."""

    def __init__(
        self,
        github: GitHubClient,
        artifact_store: S3ArtifactStore,
        *,
        max_archive_bytes: int,
        max_extracted_bytes: int,
        max_files: int,
    ) -> None:
        """Configure service boundaries and hard archive-extraction budgets."""

        if min(max_archive_bytes, max_extracted_bytes, max_files) < 1:
            raise ValueError("repository archive limits must be positive")
        self._github = github
        self._artifacts = artifact_store
        self._max_archive_bytes = max_archive_bytes
        self._max_extracted_bytes = max_extracted_bytes
        self._max_files = max_files

    def ensure(
        self,
        repo_full_name: str,
        base_commit_sha: str,
        installation_id: int,
    ) -> GraphBootstrapResult:
        """Reuse or safely build the graph identified by repository and base SHA."""

        graph_key = repository_graph_key(repo_full_name, base_commit_sha)
        graph_ref = self._artifacts.reference(graph_key)
        if self._artifacts.object_exists(graph_key):
            graph = self._load_cached_graph(
                graph_ref,
                repo_full_name=repo_full_name,
                base_commit_sha=base_commit_sha,
            )
            return _result(graph_ref, graph, cache_hit=True)

        archive = self._github.fetch_repository_archive(
            repo_full_name,
            base_commit_sha,
            installation_id,
        )
        if len(archive) > self._max_archive_bytes:
            raise PermanentError(
                "Repository archive exceeded the configured compressed byte limit",
                code="repository_archive_too_large",
            )

        from arcus.graph.builder import GraphBuilder

        with tempfile.TemporaryDirectory(prefix="arcus-repository-") as temporary:
            extraction_root = Path(temporary)
            repository_root = extract_repository_archive(
                archive,
                extraction_root,
                max_extracted_bytes=self._max_extracted_bytes,
                max_files=self._max_files,
            )
            graph = GraphBuilder(
                repo_full_name,
                base_commit_sha,
                root_path=repository_root,
            ).parse_directory(repository_root)

        graph_ref, created = self._artifacts.put_json_if_absent(
            graph_key,
            GraphStore.to_dict(graph),
        )
        if not created:
            graph = self._load_cached_graph(
                graph_ref,
                repo_full_name=repo_full_name,
                base_commit_sha=base_commit_sha,
            )
            return _result(graph_ref, graph, cache_hit=True)

        self._artifacts.put_json(
            repository_graph_pointer_key(repo_full_name),
            GraphStore.to_dict(graph),
        )
        return _result(graph_ref, graph, cache_hit=False)

    def _load_cached_graph(
        self,
        graph_ref: str,
        *,
        repo_full_name: str,
        base_commit_sha: str,
    ) -> RepoGraph:
        """Validate that an immutable cache entry has the requested identity."""

        graph = GraphStore.from_dict(self._artifacts.get_json(graph_ref))
        if graph.repo != repo_full_name or graph.graph_version != base_commit_sha:
            raise PermanentError(
                "Cached repository graph identity does not match the pull request",
                code="repository_graph_cache_invalid",
            )
        return graph


def extract_repository_archive(
    archive: bytes,
    destination: Path,
    *,
    max_extracted_bytes: int,
    max_files: int,
) -> Path:
    """Extract only Python source from an untrusted ZIP under strict limits.

    Every archive entry is validated before decompression. Absolute paths, parent
    traversal, links, special files, encryption, duplicate paths, oversized
    archives, and excessive entry counts are rejected. Repository code is only
    written as data and is never imported or executed.

    Args:
        archive: Bounded ZIP bytes returned by the GitHub API.
        destination: Existing isolated directory that receives source files.
        max_extracted_bytes: Maximum declared and actual uncompressed bytes.
        max_files: Maximum total ZIP entries, including directories.

    Returns:
        The extracted repository root, with GitHub's wrapper directory removed.

    Raises:
        PermanentError: If the archive violates any safety invariant.
    """

    if max_extracted_bytes < 1 or max_files < 1:
        raise ValueError("repository extraction limits must be positive")
    destination.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
            entries = zipped.infolist()
            if len(entries) > max_files:
                raise PermanentError(
                    "Repository archive exceeded the configured entry limit",
                    code="repository_archive_too_many_files",
                )
            planned: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
            seen_paths: set[str] = set()
            declared_bytes = 0
            for entry in entries:
                relative_path = _validated_archive_path(entry)
                path_key = relative_path.as_posix().casefold()
                if path_key in seen_paths:
                    raise PermanentError(
                        "Repository archive contains duplicate paths",
                        code="repository_archive_unsafe",
                    )
                seen_paths.add(path_key)
                if entry.is_dir():
                    continue
                declared_bytes += entry.file_size
                if declared_bytes > max_extracted_bytes:
                    raise PermanentError(
                        "Repository archive exceeded the extracted byte limit",
                        code="repository_archive_too_large",
                    )
                planned.append((entry, relative_path))

            actual_bytes = 0
            source_paths: list[PurePosixPath] = []
            destination_root = destination.resolve()
            for entry, relative_path in planned:
                if relative_path.suffix.casefold() != ".py":
                    continue
                target = destination.joinpath(*relative_path.parts)
                resolved_target = target.resolve()
                if not resolved_target.is_relative_to(destination_root):
                    raise PermanentError(
                        "Repository archive path escaped the extraction root",
                        code="repository_archive_unsafe",
                    )
                target.parent.mkdir(parents=True, exist_ok=True)
                with zipped.open(entry, "r") as source, target.open("wb") as output:
                    while chunk := source.read(_COPY_CHUNK_BYTES):
                        actual_bytes += len(chunk)
                        if actual_bytes > max_extracted_bytes:
                            raise PermanentError(
                                "Repository archive exceeded the extracted byte limit",
                                code="repository_archive_too_large",
                            )
                        output.write(chunk)
                source_paths.append(relative_path)
    except PermanentError:
        raise
    except (OSError, RuntimeError, zipfile.BadZipFile, zipfile.LargeZipFile) as error:
        raise PermanentError(
            "Repository archive was not a valid readable ZIP file",
            code="repository_archive_invalid",
        ) from error

    return _repository_root(destination, source_paths)


def _validated_archive_path(entry: zipfile.ZipInfo) -> PurePosixPath:
    """Validate one ZIP path and reject link or special-file metadata."""

    raw_name = entry.filename.replace("\\", "/")
    relative_path = PurePosixPath(raw_name)
    if (
        not raw_name
        or "\x00" in raw_name
        or relative_path.is_absolute()
        or ".." in relative_path.parts
        or (relative_path.parts and relative_path.parts[0].endswith(":"))
    ):
        raise PermanentError(
            "Repository archive contains an unsafe path",
            code="repository_archive_unsafe",
        )
    if entry.flag_bits & 0x1:
        raise PermanentError(
            "Repository archive contains an encrypted entry",
            code="repository_archive_unsafe",
        )
    mode = entry.external_attr >> 16
    if stat.S_ISLNK(mode):
        raise PermanentError(
            "Repository archive contains a symbolic link",
            code="repository_archive_unsafe",
        )
    file_type = stat.S_IFMT(mode)
    if not entry.is_dir() and file_type not in {0, stat.S_IFREG}:
        raise PermanentError(
            "Repository archive contains a special file",
            code="repository_archive_unsafe",
        )
    return relative_path


def _repository_root(
    destination: Path,
    source_paths: list[PurePosixPath],
) -> Path:
    """Remove the single wrapper directory GitHub adds to archive downloads."""

    if not source_paths:
        return destination
    top_levels = {path.parts[0] for path in source_paths if path.parts}
    if len(top_levels) == 1 and all(len(path.parts) > 1 for path in source_paths):
        return destination / next(iter(top_levels))
    return destination


def _result(
    graph_ref: str,
    graph: RepoGraph,
    *,
    cache_hit: bool,
) -> GraphBootstrapResult:
    """Build the small typed result used only for lifecycle logging."""

    return GraphBootstrapResult(
        graph_ref=graph_ref,
        graph_version=graph.graph_version,
        cache_hit=cache_hit,
        node_count=len(graph.nodes),
        link_count=len(graph.links),
    )
