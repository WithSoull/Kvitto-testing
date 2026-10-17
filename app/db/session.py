from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

engine = create_async_engine(str(get_settings().database_url), pool_pre_ping=True)

# expire_on_commit=False: ORM objects stay readable after commit without an implicit
# (and in async mode, forbidden) lazy reload.
session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session
