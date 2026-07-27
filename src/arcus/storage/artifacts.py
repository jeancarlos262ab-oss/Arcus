"""Bounded S3 storage for diffs, graphs, and subgraphs."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Protocol, cast

from botocore.config import Config


class S3Client(Protocol):
    """Minimal S3 client used by artifact storage."""

    def put_object(
        self, *, Bucket: str, Key: str, Body: bytes, ContentType: str
    ) -> Mapping[str, object]:
        """Persist one bounded artifact."""
        ...

    def get_object(self, *, Bucket: str, Key: str) -> Mapping[str, object]:
        """Load one artifact body."""
        ...

    def head_object(self, *, Bucket: str, Key: str) -> Mapping[str, object]:
        """Inspect one object without downloading its body."""
        ...


class StreamingBody(Protocol):
    """Minimal bounded read surface returned by S3."""

    def read(self, amt: int | None = None) -> bytes:
        """Read at most the requested number of bytes."""
        ...


class S3ArtifactStore:
    """Store bounded UTF-8 and JSON artifacts in one private bucket."""

    def __init__(
        self,
        bucket_name: str,
        *,
        client: S3Client | None = None,
        max_artifact_bytes: int = 524_288,
    ) -> None:
        """Create a store that refuses unexpectedly large reads and writes."""

        if not bucket_name.strip():
            raise ValueError("S3 artifact bucket cannot be empty")
        if max_artifact_bytes < 1:
            raise ValueError("max_artifact_bytes must be at least 1")
        self._bucket_name = bucket_name
        self._max_artifact_bytes = max_artifact_bytes
        if client is None:
            import boto3

            boto3_module = cast(Any, boto3)
            raw_client = boto3_module.client(
                "s3",
                config=Config(retries={"mode": "adaptive", "total_max_attempts": 3}),
            )
            self._client = cast(S3Client, raw_client)
        else:
            self._client = client

    @property
    def bucket_name(self) -> str:
        """Return the configured artifact bucket name."""

        return self._bucket_name

    def reference(self, key: str) -> str:
        """Return the canonical S3 URI for an object key in this store."""

        return f"s3://{self._bucket_name}/{_normalise_key(key)}"

    def object_exists(self, key: str) -> bool:
        """Return whether an object exists without masking authorization failures."""

        from botocore.exceptions import ClientError

        normalised_key = _normalise_key(key)
        try:
            self._client.head_object(Bucket=self._bucket_name, Key=normalised_key)
        except ClientError as error:
            if _client_error_code(error) in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise
        return True

    def put_text(self, key: str, text: str, *, content_type: str = "text/plain") -> str:
        """Store a UTF-8 artifact and return its S3 reference."""

        normalised_key = _normalise_key(key)
        body = self._bounded_body(text)
        self._client.put_object(
            Bucket=self._bucket_name,
            Key=normalised_key,
            Body=body,
            ContentType=content_type,
        )
        return self.reference(normalised_key)

    def put_json(self, key: str, payload: Mapping[str, object]) -> str:
        """Serialize one compact JSON artifact with the same byte guard."""

        return self.put_text(
            key,
            json.dumps(payload, separators=(",", ":")),
            content_type="application/json",
        )

    def put_json_if_absent(
        self,
        key: str,
        payload: Mapping[str, object],
    ) -> tuple[str, bool]:
        """Create an immutable JSON artifact once and report whether it was written."""

        from botocore.exceptions import ClientError

        normalised_key = _normalise_key(key)
        body = self._bounded_body(json.dumps(payload, separators=(",", ":")))
        raw_client = cast(Any, self._client)
        try:
            raw_client.put_object(
                Bucket=self._bucket_name,
                Key=normalised_key,
                Body=body,
                ContentType="application/json",
                IfNoneMatch="*",
            )
        except ClientError as error:
            if _client_error_code(error) in {
                "ConditionalRequestConflict",
                "PreconditionFailed",
            }:
                return self.reference(normalised_key), False
            raise
        return self.reference(normalised_key), True

    def get_text(self, reference: str) -> str:
        """Read one S3 reference without buffering more than the hard limit."""

        bucket, key = parse_s3_reference(reference)
        if bucket != self._bucket_name:
            raise ValueError("artifact reference points to an unexpected bucket")
        response = self._client.get_object(Bucket=bucket, Key=key)
        raw_body = response.get("Body")
        if not hasattr(raw_body, "read"):
            raise ValueError("S3 response did not include a readable body")
        body = cast(StreamingBody, raw_body).read(self._max_artifact_bytes + 1)
        if len(body) > self._max_artifact_bytes:
            raise ValueError("artifact exceeds the configured byte limit")
        return body.decode("utf-8")

    def get_json(self, reference: str) -> Mapping[str, object]:
        """Load one JSON object from S3 and validate its top-level shape."""

        payload: object = json.loads(self.get_text(reference))
        if not isinstance(payload, Mapping):
            raise ValueError("artifact JSON must contain an object")
        return cast(Mapping[str, object], payload)

    def _bounded_body(self, text: str) -> bytes:
        """Encode text only when it fits the configured object budget."""

        body = text.encode("utf-8")
        if len(body) > self._max_artifact_bytes:
            raise ValueError("artifact exceeds the configured byte limit")
        return body


def parse_s3_reference(reference: str) -> tuple[str, str]:
    """Split a validated-looking S3 URI into bucket and key."""

    if not reference.startswith("s3://"):
        raise ValueError("artifact reference must use s3://")
    bucket, separator, key = reference[5:].partition("/")
    if not bucket or separator != "/" or not key:
        raise ValueError("artifact reference must include bucket and key")
    return bucket, key


def _normalise_key(key: str) -> str:
    """Reject absolute or parent-traversing object keys."""

    normalised = key.strip().lstrip("/")
    if not normalised or ".." in normalised.split("/"):
        raise ValueError("artifact key is invalid")
    return normalised


def _client_error_code(error: Any) -> str:
    """Read one botocore error code without assuming the response shape."""

    response = getattr(error, "response", {})
    if not isinstance(response, Mapping):
        return ""
    details = response.get("Error", {})
    code = details.get("Code") if isinstance(details, Mapping) else None
    return str(code) if code is not None else ""
