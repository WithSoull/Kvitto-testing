from fastapi import APIRouter, status

from app.api.deps import SessionDep
from app.schemas.tariff import TariffOut
from app.services import tariffs as tariffs_service

router = APIRouter(prefix="/tariffs", tags=["tariffs"])


@router.get(
    "",
    response_model=list[TariffOut],
    status_code=status.HTTP_200_OK,
    summary="List tariffs",
    description="All available tariffs, sorted by price. Prices are in kopecks.",
)
async def list_tariffs(session: SessionDep) -> list[TariffOut]:
    tariffs = await tariffs_service.list_tariffs(session)
    return [TariffOut.model_validate(tariff) for tariff in tariffs]
