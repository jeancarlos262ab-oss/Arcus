"""Replay a saved GitHub pull-request event against a deployed Arcus stack."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

logger = logging.getLogger(__name__)

DEFAULT_PAYLOAD = (
    Path(__file__).parents[1]
    / "tests"
    / "fixtures"
    / "webhooks"
    / "pull_request_opened.json"
)


def replay_webhook(
    webhook_url: str,
    secret: str,
    payload_path: Path,
    *,
    delivery_id: str,
) -> int:
    """Sign and post one saved GitHub event to the deployed webhook.

    Args:
        webhook_url: Deployed ``WebhookUrl`` stack output.
        secret: Webhook HMAC secret matching Secrets Manager.
        payload_path: Saved pull-request event payload.
        delivery_id: Unique GitHub-style delivery identifier.

    Returns:
        Process exit code: zero only when Arcus accepts the event with HTTP 202.
    """

    body = payload_path.read_bytes()
    json.loads(body)
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    request = Request(
        webhook_url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "pull_request",
            "X-GitHub-Delivery": delivery_id,
            "X-Hub-Signature-256": f"sha256={digest}",
        },
    )
    try:
        with urlopen(request, timeout=15) as response:
            response_body = response.read().decode("utf-8")
            logger.info(
                "webhook_replay_completed",
                extra={"status_code": response.status, "response_body": response_body},
            )
            return 0 if response.status == 202 else 1
    except HTTPError as error:
        logger.error(
            "webhook_replay_rejected",
            extra={
                "status_code": error.code,
                "response_body": error.read().decode("utf-8", errors="replace"),
            },
        )
    except URLError as error:
        logger.error(
            "webhook_replay_failed",
            extra={"reason": str(error.reason)},
        )
    return 1


def main() -> int:
    """Load safe CLI/config values and execute one replay."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url",
        default=os.getenv("ARCUS_WEBHOOK_URL", ""),
        help="Deployed WebhookUrl (or set ARCUS_WEBHOOK_URL)",
    )
    parser.add_argument(
        "--payload",
        type=Path,
        default=DEFAULT_PAYLOAD,
        help="Saved GitHub pull_request payload",
    )
    parser.add_argument(
        "--delivery-id",
        default=f"replay-{uuid4()}",
        help="Unique delivery ID for idempotency testing",
    )
    args = parser.parse_args()
    secret = os.getenv("ARCUS_WEBHOOK_SECRET", "")
    if not args.url:
        parser.error("--url or ARCUS_WEBHOOK_URL is required")
    if not secret:
        parser.error("ARCUS_WEBHOOK_SECRET is required")

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    return replay_webhook(
        args.url,
        secret,
        args.payload,
        delivery_id=args.delivery_id,
    )


if __name__ == "__main__":
    raise SystemExit(main())
