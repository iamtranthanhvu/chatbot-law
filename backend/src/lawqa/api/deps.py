from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

ReadinessCheck = Callable[[], Awaitable[None]]


@dataclass
class AppContainer:
    """Everything the routes need, built once at startup (or by a test with fakes)."""

    checks: dict[str, ReadinessCheck] = field(default_factory=dict)
    session_factory: async_sessionmaker[AsyncSession] | None = None


def get_container(request: Request) -> AppContainer:
    container: AppContainer = request.app.state.container
    return container


def get_session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    factory = get_container(request).session_factory
    if factory is None:
        raise RuntimeError("database is not configured")
    return factory
