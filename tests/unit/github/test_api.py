"""Unit coverage for the bounded production GitHub API adapter."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass

import pytest

from arcus.errors import PermanentError
from arcus.github.api import GitHubClient
from arcus.github.app_auth import HttpResponse


class StaticTokenProvider:
    """Return a deterministic installation token without authentication I/O."""

    def get_installation_token(self, installation_id: int) -> str:
        assert installation_id == 123456
        return "test-token"


@dataclass(frozen=True, slots=True)
class RequestRecord:
    """Capture one production-adapter request for behavior assertions."""

    method: str
    url: str
    body: bytes | None


class QueueTransport:
    """Serve bounded raw responses through the real GitHubClient parser."""

    def __init__(self, responses: list[HttpResponse]) -> None:
        self._responses = responses
        self.requests: list[RequestRecord] = []

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        body: bytes | None = None,
        max_response_bytes: int = 1_048_576,
    ) -> HttpResponse:
        assert headers["Authorization"] == "Bearer test-token"
        self.requests.append(RequestRecord(method, url, body))
        if not self._responses:
            raise AssertionError("unexpected GitHub request")
        response = self._responses.pop(0)
        return HttpResponse(
            status=response.status,
            headers=response.headers,
            body=response.body[:max_response_bytes],
        )


def _response(payload: object) -> HttpResponse:
    return HttpResponse(
        status=200,
        headers={},
        body=json.dumps(payload).encode("utf-8"),
    )


def test_comment_upsert_finds_marker_on_a_later_bounded_page() -> None:
    """An existing Arcus comment outside page one must be patched, not duplicated."""

    first_page = [{"id": index, "body": "other"} for index in range(100)]
    transport = QueueTransport(
        [
            _response(first_page),
            _response([{"id": 501, "body": "<!-- arcus-review -->\nold"}]),
            _response({"html_url": "https://github.test/comment/501"}),
        ]
    )
    client = GitHubClient(
        StaticTokenProvider(),
        api_base_url="https://github.test",
        transport=transport,
        max_comment_pages=3,
    )

    url = client.upsert_review_comment("acme/widgets", 42, 123456, "new review")

    assert url == "https://github.test/comment/501"
    assert transport.requests[0].url.endswith("comments?per_page=100&page=1")
    assert transport.requests[1].url.endswith("comments?per_page=100&page=2")
    assert transport.requests[2].method == "PATCH"
    assert transport.requests[2].url.endswith("/issues/comments/501")


def test_comment_upsert_refuses_to_duplicate_after_scan_cap() -> None:
    """A saturated scan must fail closed instead of creating a second comment."""

    transport = QueueTransport(
        [_response([{"id": index, "body": "other"} for index in range(100)])]
    )
    client = GitHubClient(
        StaticTokenProvider(),
        transport=transport,
        max_comment_pages=1,
    )

    with pytest.raises(PermanentError, match="page limit"):
        client.upsert_review_comment("acme/widgets", 42, 123456, "review")

    assert [request.method for request in transport.requests] == ["GET"]


def test_pull_request_fetch_caps_files_and_diff_bytes() -> None:
    """Production response parsing must enforce both configured artifact bounds."""

    transport = QueueTransport(
        [
            _response([{"filename": "src/a.py"}, {"filename": "src/b.py"}]),
            HttpResponse(status=200, headers={}, body=b"0123456789abcdef"),
        ]
    )
    client = GitHubClient(
        StaticTokenProvider(),
        transport=transport,
        max_changed_files=1,
        max_diff_bytes=10,
    )

    result = client.fetch_pull_request("acme/widgets", 42, 123456)

    assert result.changed_files == ["src/a.py"]
    assert result.files_truncated is True
    assert result.diff == "0123456789"
    assert result.diff_truncated is True


def test_repository_archive_download_uses_immutable_ref_and_byte_cap() -> None:
    """Archive downloads must target one SHA and reject a compressed overflow."""

    successful_transport = QueueTransport(
        [HttpResponse(status=200, headers={}, body=b"12345")]
    )
    successful_client = GitHubClient(
        StaticTokenProvider(),
        api_base_url="https://github.test",
        transport=successful_transport,
        max_repository_archive_bytes=5,
    )

    archive = successful_client.fetch_repository_archive(
        "acme/widgets",
        "def456abc1237890",
        123456,
    )

    assert archive == b"12345"
    assert successful_transport.requests[0].url.endswith(
        "/repos/acme/widgets/zipball/def456abc1237890"
    )

    oversized_transport = QueueTransport(
        [HttpResponse(status=200, headers={}, body=b"123456")]
    )
    oversized_client = GitHubClient(
        StaticTokenProvider(),
        transport=oversized_transport,
        max_repository_archive_bytes=5,
    )

    with pytest.raises(PermanentError, match="byte limit"):
        oversized_client.fetch_repository_archive(
            "acme/widgets",
            "def456abc1237890",
            123456,
        )
