from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Tariff


async def list_tariffs(session: AsyncSession) -> Sequence[Tariff]:
    result = await session.scalars(select(Tariff).order_by(Tariff.price))
    return result.all()
