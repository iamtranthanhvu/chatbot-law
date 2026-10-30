import time
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from qdrant_client import AsyncQdrantClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from testcontainers.community.postgres import PostgresContainer
from testcontainers.core.container import DockerContainer

from lawqa.db.migrate import upgrade
from lawqa.db.session import create_engine, create_session_factory

POSTGRES_IMAGE = "postgres:16.6-alpine"
QDRANT_IMAGE = "qdrant/qdrant:v1.19.2"


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
        await connection.execute(text("TRUNCATE documents, queries CASCADE"))
        await connection.execute(text("UPDATE corpus_state SET version = 0"))
    yield create_session_factory(engine)
    await engine.dispose()


@pytest.fixture(scope="session")
def qdrant_url() -> Iterator[str]:
    with DockerContainer(QDRANT_IMAGE).with_exposed_ports(6333) as container:
        url = f"http://{container.get_container_host_ip()}:{container.get_exposed_port(6333)}"
        deadline = time.monotonic() + 60
        while True:
            try:
                if httpx.get(f"{url}/readyz", timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            if time.monotonic() > deadline:
                raise TimeoutError("Qdrant container did not become ready")
            time.sleep(0.5)
        yield url


@pytest.fixture
async def qdrant(qdrant_url: str) -> AsyncIterator[AsyncQdrantClient]:
    client = AsyncQdrantClient(url=qdrant_url)
    for collection in (await client.get_collections()).collections:
        await client.delete_collection(collection.name)
    yield client
    await client.close()
