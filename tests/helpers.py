import hashlib
import hmac
import json
from typing import Any

from httpx import AsyncClient, Response

TEST_WEBHOOK_SECRET = "test-webhook-secret"


def sign(body: bytes, secret: str = TEST_WEBHOOK_SECRET) -> str:
    """Independent reference implementation of the bank's X-Signature."""
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


async def post_webhook(
    client: AsyncClient,
    payload: dict[str, Any] | bytes,
    *,
    signature: str | None = "auto",
) -> Response:
    """POST raw bytes to the webhook; signs them unless a signature (or None) is given."""
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    headers: dict[bytes, bytes] = {b"Content-Type": b"application/json"}
    if signature == "auto":
        signature = sign(body)
    if signature is not None:
        # Bytes, so tests can also send non-ASCII garbage, which httpx rejects in a str header.
        headers[b"X-Signature"] = signature.encode()
    return await client.post("/webhooks/bank", content=body, headers=headers)
