"""Bounded GitHub pull-request reads and idempotent review comments."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, cast
from urllib.parse import quote

from arcus.errors import PermanentError
from arcus.github.app_auth import HttpTransport, UrlLibTransport

_REVIEW_MARKER = "<!-- arcus-review -->"


class InstallationTokenProvider(Protocol):
    """Authentication boundary used by the GitHub API client."""

    def get_installation_token(self, installation_id: int) -> str:
        """Return a short-lived installation token."""
        ...


@dataclass(frozen=True, slots=True)
class PullRequestData:
    """Bounded PR artifacts consumed by the Fetch PR Lambda."""

    changed_files: list[str]
    diff: str
    files_truncated: bool
    diff_truncated: bool


class GitHubClient:
    """Read PR data and create or update one marked review comment."""

    def __init__(
        self,
        token_provider: InstallationTokenProvider,
        *,
        api_base_url: str = "https://api.github.com",
        transport: HttpTransport | None = None,
        max_changed_files: int = 50,
        max_diff_bytes: int = 524_288,
        max_comment_pages: int = 10,
    ) -> None:
        """Create a client with hard pagination and response-size bounds."""

        if max_changed_files < 1 or max_diff_bytes < 1 or max_comment_pages < 1:
            raise ValueError("GitHub API limits must be positive")
        self._token_provider = token_provider
        self._api_base_url = api_base_url.rstrip("/")
        self._transport = transport or UrlLibTransport()
        self._max_changed_files = max_changed_files
        self._max_diff_bytes = max_diff_bytes
        self._max_comment_pages = max_comment_pages

    def fetch_pull_request(
        self,
        repo_full_name: str,
        pr_number: int,
        installation_id: int,
    ) -> PullRequestData:
        """Fetch a bounded changed-file list and diff for one PR."""

        token = self._token_provider.get_installation_token(installation_id)
        repo = quote(repo_full_name, safe="/")
        headers = _headers(token)
        changed_files: list[str] = []
        files_truncated = False
        page = 1
        while len(changed_files) < self._max_changed_files:
            response = self._transport.request(
                "GET",
                f"{self._api_base_url}/repos/{repo}/pulls/{pr_number}/files"
                f"?per_page=100&page={page}",
                headers=headers,
            )
            files = _json_array(response.body)
            for raw_file in files:
                if len(changed_files) >= self._max_changed_files:
                    files_truncated = True
                    break
                if not isinstance(raw_file, Mapping):
                    raise PermanentError(
                        "GitHub file response was malformed",
                        code="github_invalid_response",
                    )
                filename = cast(Mapping[str, object], raw_file).get("filename")
                if not isinstance(filename, str) or not filename.strip():
                    raise PermanentError(
                        "GitHub file response omitted filename",
                        code="github_invalid_response",
                    )
                changed_files.append(filename)
            if len(files) < 100:
                break
            if len(changed_files) >= self._max_changed_files:
                files_truncated = True
                break
            page += 1

        diff_response = self._transport.request(
            "GET",
            f"{self._api_base_url}/repos/{repo}/pulls/{pr_number}",
            headers={**headers, "Accept": "application/vnd.github.v3.diff"},
            max_response_bytes=self._max_diff_bytes + 1,
        )
        diff_bytes = diff_response.body
        diff_truncated = len(diff_bytes) > self._max_diff_bytes
        if diff_truncated:
            diff_bytes = diff_bytes[: self._max_diff_bytes]
        return PullRequestData(
            changed_files=changed_files,
            diff=diff_bytes.decode("utf-8", errors="replace"),
            files_truncated=files_truncated,
            diff_truncated=diff_truncated,
        )

    def upsert_review_comment(
        self,
        repo_full_name: str,
        pr_number: int,
        installation_id: int,
        markdown: str,
    ) -> str:
        """Create or update the single Arcus marker comment idempotently."""

        token = self._token_provider.get_installation_token(installation_id)
        repo = quote(repo_full_name, safe="/")
        headers = {**_headers(token), "Content-Type": "application/json"}
        comment_id: int | None = None
        scan_exhausted = False
        for page in range(1, self._max_comment_pages + 1):
            comments_response = self._transport.request(
                "GET",
                f"{self._api_base_url}/repos/{repo}/issues/{pr_number}/comments"
                f"?per_page=100&page={page}",
                headers=headers,
            )
            comments = _json_array(comments_response.body)
            for raw_comment in comments:
                if not isinstance(raw_comment, Mapping):
                    continue
                comment = cast(Mapping[str, object], raw_comment)
                body = comment.get("body")
                identifier = comment.get("id")
                if (
                    isinstance(body, str)
                    and _REVIEW_MARKER in body
                    and isinstance(identifier, int)
                ):
                    comment_id = identifier
                    break
            if comment_id is not None or len(comments) < 100:
                break
            scan_exhausted = page == self._max_comment_pages

        if comment_id is None and scan_exhausted:
            raise PermanentError(
                "GitHub comment scan exceeded the configured page limit",
                code="github_comment_scan_exhausted",
            )

        comment_body = f"{_REVIEW_MARKER}\n{markdown}"
        encoded = json.dumps({"body": comment_body}, separators=(",", ":")).encode()
        if comment_id is None:
            method = "POST"
            url = f"{self._api_base_url}/repos/{repo}/issues/{pr_number}/comments"
        else:
            method = "PATCH"
            url = f"{self._api_base_url}/repos/{repo}/issues/comments/{comment_id}"
        response = self._transport.request(
            method,
            url,
            headers=headers,
            body=encoded,
        )
        result = _json_object(response.body)
        comment_url = result.get("html_url")
        if not isinstance(comment_url, str) or not comment_url:
            raise PermanentError(
                "GitHub comment response omitted html_url",
                code="github_invalid_response",
            )
        return comment_url


def _headers(token: str) -> dict[str, str]:
    """Build the standard non-secret GitHub request headers."""

    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "arcus-pr-reviewer",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _json_object(body: bytes) -> Mapping[str, object]:
    """Parse one untrusted GitHub JSON object."""

    payload: object = json.loads(body.decode("utf-8"))
    if not isinstance(payload, Mapping):
        raise PermanentError(
            "GitHub response must be an object",
            code="github_invalid_response",
        )
    return cast(Mapping[str, object], payload)


def _json_array(body: bytes) -> list[object]:
    """Parse one untrusted GitHub JSON array."""

    payload: object = json.loads(body.decode("utf-8"))
    if not isinstance(payload, list):
        raise PermanentError(
            "GitHub response must be an array",
            code="github_invalid_response",
        )
    return cast(list[object], payload)
