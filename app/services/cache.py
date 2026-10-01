import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Hashable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from cachetools import TTLCache


@dataclass
class Cached:
    value: Any
    fetched_at: datetime
    hit: bool


class AsyncTTLCache:
    """Namespaced in-memory TTL cache with single-flight loading.

    Concurrent callers asking for the same missing key share one upstream
    call instead of stampeding Blinkit.
    """

    def __init__(self, maxsize: int, ttls: dict[str, int]):
        self._caches = {ns: TTLCache(maxsize=maxsize, ttl=ttl) for ns, ttl in ttls.items()}
        self._locks: dict[tuple[str, Hashable], asyncio.Lock] = {}

    @asynccontextmanager
    async def locked(self, ns: str, key: Hashable) -> AsyncIterator[None]:
        lock = self._locks.setdefault((ns, key), asyncio.Lock())
        try:
            async with lock:
                yield
        finally:
            if not lock.locked() and self._locks.get((ns, key)) is lock:
                del self._locks[(ns, key)]

    def peek(self, ns: str, key: Hashable) -> tuple[Any, datetime] | None:
        return self._caches[ns].get(key)

    def put(self, ns: str, key: Hashable, value: Any) -> datetime:
        now = datetime.now(UTC)
        self._caches[ns][key] = (value, now)
        return now

    async def get_or_load(
        self, ns: str, key: Hashable, loader: Callable[[], Awaitable[Any]], *, fresh: bool = False
    ) -> Cached:
        if not fresh and (hit := self.peek(ns, key)) is not None:
            return Cached(hit[0], hit[1], True)
        async with self.locked(ns, key):
            if not fresh and (hit := self.peek(ns, key)) is not None:
                return Cached(hit[0], hit[1], True)
            value = await loader()
            return Cached(value, self.put(ns, key, value), False)

    def clear(self) -> None:
        for c in self._caches.values():
            c.clear()
        self._locks.clear()

    def stats(self) -> dict[str, int]:
        return {ns: len(c) for ns, c in self._caches.items()}
