"""A second event loop in a background thread, for synchronous hypothesis tests.

Hypothesis cannot drive `async def` tests; property tests submit coroutines to this loop,
which owns its own engine.
"""

import asyncio
import threading
from collections.abc import Coroutine, Iterator
from typing import Any, TypeVar

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trovelya.core.db import make_engine, make_sessionmaker

T = TypeVar("T")


class LoopThread:
    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self._thread.start()
        self.sessionmaker: async_sessionmaker[AsyncSession]

    def run(self, coro: Coroutine[Any, Any, T]) -> T:
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout=60)

    def stop(self) -> None:
        self.loop.call_soon_threadsafe(self.loop.stop)
        self._thread.join(timeout=5)


@pytest.fixture(scope="session")
def loop_thread(migrated_url: str) -> Iterator[LoopThread]:
    thread = LoopThread()
    engine = make_engine(migrated_url)
    thread.sessionmaker = make_sessionmaker(engine)
    yield thread
    thread.run(engine.dispose())
    thread.stop()
