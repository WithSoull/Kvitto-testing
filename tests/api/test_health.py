from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def test_health(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_test_database_is_reachable(db_session: AsyncSession) -> None:
    result = await db_session.execute(text("SELECT current_database()"))

    assert result.scalar_one() == "kvitto_test"
