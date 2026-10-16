import hashlib
import hmac
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_session

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def compute_signature(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


async def verify_signature(
    request: Request,
    x_signature: Annotated[
        str | None,
        Header(description="Hex HMAC-SHA256 of the raw request body, keyed with WEBHOOK_SECRET"),
    ] = None,
) -> None:
    # Sign the raw bytes as received: re-serialized JSON may differ in spacing or key order.
    body = await request.body()
    expected = compute_signature(get_settings().webhook_secret.get_secret_value(), body)
    # compare_digest takes constant time (no timing attack). Comparing bytes also avoids the
    # TypeError it raises for non-ASCII str input, which would otherwise become a 500.
    if x_signature is None or not hmac.compare_digest(x_signature.encode(), expected.encode()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")
