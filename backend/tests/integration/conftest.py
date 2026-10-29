from collections.abc import AsyncIterator, Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from testcontainers.community.postgres import PostgresContainer

from lawqa.db.migrate import upgrade
from lawqa.db.session import create_engine, create_session_factory

POSTGRES_IMAGE = "postgres:16.6-alpine"


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    with PostgresContainer(POSTGRES_IMAGE, driver="asyncpg") as container:
        url = container.get_connection_url()
        upgrade(url)
        yield url


@pytest.fixture
async def session_factory(postgres_url: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_engine(postgres_url)
    async with engine.begin() as connection:
        await connection.execute(text("TRUNCATE documents CASCADE"))
        await connection.execute(text("UPDATE corpus_state SET version = 0"))
    yield create_session_factory(engine)
    await engine.dispose()
