from fastapi import APIRouter

router = APIRouter(tags=["service"])


@router.get("/health", summary="Liveness probe")
async def health() -> dict[str, str]:
    return {"status": "ok"}
