from __future__ import annotations

import asyncio
import hashlib
import secrets
import time
from collections import defaultdict, deque
from collections.abc import AsyncIterator, Awaitable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, Protocol, cast
from uuid import UUID

from pydantic import BaseModel
from redis.asyncio import Redis


class RateLimitDecision(BaseModel):
    allowed: bool
    minute_remaining: int
    daily_remaining: int
    retry_after_seconds: int | None = None


class RequestGuard(Protocol):
    async def check_rate_limit(
        self,
        *,
        ip_address: str,
        user_id: UUID,
    ) -> RateLimitDecision: ...

    def session_lock(self, session_id: UUID) -> Any: ...

    async def ready(self) -> bool: ...


class LocalRequestGuard:
    """Single-process development fallback with the same behavior as Redis controls."""

    def __init__(self, *, per_minute: int, per_day: int) -> None:
        self.per_minute = per_minute
        self.per_day = per_day
        self._minute: dict[str, deque[float]] = defaultdict(deque)
        self._daily: dict[tuple[str, str], int] = defaultdict(int)
        self._locks: dict[UUID, asyncio.Lock] = {}

    async def check_rate_limit(
        self,
        *,
        ip_address: str,
        user_id: UUID,
    ) -> RateLimitDecision:
        now = time.monotonic()
        minute_key = self._hash(ip_address)
        window = self._minute[minute_key]
        while window and window[0] <= now - 60:
            window.popleft()
        day_key = (str(user_id), datetime.now(UTC).date().isoformat())
        daily_count = self._daily[day_key]
        if len(window) >= self.per_minute or daily_count >= self.per_day:
            retry_after = max(1, int(60 - (now - window[0]))) if window else 86_400
            return RateLimitDecision(
                allowed=False,
                minute_remaining=max(0, self.per_minute - len(window)),
                daily_remaining=max(0, self.per_day - daily_count),
                retry_after_seconds=retry_after,
            )
        window.append(now)
        self._daily[day_key] += 1
        return RateLimitDecision(
            allowed=True,
            minute_remaining=self.per_minute - len(window),
            daily_remaining=self.per_day - self._daily[day_key],
        )

    @asynccontextmanager
    async def session_lock(self, session_id: UUID) -> AsyncIterator[bool]:
        lock = self._locks.setdefault(session_id, asyncio.Lock())
        if lock.locked():
            yield False
            return
        await lock.acquire()
        try:
            yield True
        finally:
            lock.release()

    async def ready(self) -> bool:
        return True

    @staticmethod
    def _hash(value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()[:24]


class RedisRequestGuard:
    RATE_SCRIPT = """
    local minute = redis.call('INCR', KEYS[1])
    if minute == 1 then redis.call('EXPIRE', KEYS[1], 60) end
    local daily = redis.call('INCR', KEYS[2])
    if daily == 1 then redis.call('EXPIRE', KEYS[2], 86400) end
    local ttl = redis.call('TTL', KEYS[1])
    return {minute, daily, ttl}
    """
    RELEASE_SCRIPT = """
    if redis.call('GET', KEYS[1]) == ARGV[1] then
      return redis.call('DEL', KEYS[1])
    end
    return 0
    """

    def __init__(
        self,
        *,
        url: str | None = None,
        client: Redis | None = None,
        per_minute: int,
        per_day: int,
    ) -> None:
        if client is None and url is None:
            raise ValueError("Redis URL or client is required")
        self.client = client or Redis.from_url(cast_redis_url(url), decode_responses=True)
        self.per_minute = per_minute
        self.per_day = per_day

    async def check_rate_limit(
        self,
        *,
        ip_address: str,
        user_id: UUID,
    ) -> RateLimitDecision:
        ip_hash = hashlib.sha256(ip_address.encode()).hexdigest()[:24]
        day = datetime.now(UTC).date().isoformat()
        result = await cast(
            Awaitable[Any],
            self.client.eval(
                self.RATE_SCRIPT,
                2,
                f"rate:minute:{ip_hash}",
                f"rate:day:{user_id}:{day}",
            ),
        )
        minute, daily, ttl = [int(value) for value in result]
        allowed = minute <= self.per_minute and daily <= self.per_day
        return RateLimitDecision(
            allowed=allowed,
            minute_remaining=max(0, self.per_minute - minute),
            daily_remaining=max(0, self.per_day - daily),
            retry_after_seconds=None if allowed else max(1, ttl),
        )

    @asynccontextmanager
    async def session_lock(self, session_id: UUID) -> AsyncIterator[bool]:
        key = f"lock:session:{session_id}"
        token = secrets.token_urlsafe(24)
        acquired = bool(await self.client.set(key, token, ex=120, nx=True))
        try:
            yield acquired
        finally:
            if acquired:
                await cast(
                    Awaitable[Any],
                    self.client.eval(self.RELEASE_SCRIPT, 1, key, token),
                )

    async def ready(self) -> bool:
        try:
            return bool(await self.client.ping())
        except Exception:
            return False


def cast_redis_url(url: str | None) -> str:
    if url is None:
        raise ValueError("REDIS_URL is required")
    return url
