from fastapi import APIRouter, status

from app.api.deps import SessionDep
from app.schemas.errors import ErrorDetail
from app.schemas.webhook import BankWebhook, InvalidTransitionResponse, WebhookResult
from app.services import webhooks as webhooks_service

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post(
    "/bank",
    response_model=WebhookResult,
    status_code=status.HTTP_200_OK,
    summary="Bank payment status notification",
    description=(
        "Allowed transitions: pending → succeeded, pending → failed, succeeded → refunded. "
        "Any other transition, including a repeat of the current status, is rejected with 409 "
        "and the status is left unchanged."
    ),
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ErrorDetail, "description": "Payment not found"},
        status.HTTP_409_CONFLICT: {
            "model": InvalidTransitionResponse,
            "description": "Status transition is not allowed",
        },
    },
)
async def bank_webhook(body: BankWebhook, session: SessionDep) -> WebhookResult:
    await webhooks_service.apply_bank_status(session, body.payment_id, body.status)
    return WebhookResult()
