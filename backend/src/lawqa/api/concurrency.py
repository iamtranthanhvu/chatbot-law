import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


class BusyError(Exception):
    pass


class GenerationSlots:
    """Caps answers generated at once by this process; a request waits for a slot only so
    long, then gives up with BUSY instead of queueing without bound."""

    def __init__(self, max_concurrent: int, wait_seconds: float) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._wait = wait_seconds

    @asynccontextmanager
    async def slot(self) -> AsyncIterator[None]:
        try:
            await asyncio.wait_for(self._semaphore.acquire(), timeout=self._wait)
        except TimeoutError as error:
            raise BusyError from error
        try:
            yield
        finally:
            self._semaphore.release()
