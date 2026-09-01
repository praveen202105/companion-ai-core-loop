import asyncio
import os
from uuid import uuid4

import pytest

from companion.request_control import LocalRequestGuard, RedisRequestGuard


async def test_local_rate_limits_match_production_defaults() -> None:
    guard = LocalRequestGuard(per_minute=2, per_day=10)
    session_id = uuid4()

    first = await guard.check_rate_limit(ip_address="127.0.0.1", session_id=session_id)
    second = await guard.check_rate_limit(ip_address="127.0.0.1", session_id=session_id)
    blocked = await guard.check_rate_limit(ip_address="127.0.0.1", session_id=session_id)

    assert first.allowed and second.allowed
    assert not blocked.allowed
    assert blocked.retry_after_seconds is not None


async def test_only_one_request_can_hold_a_session_lock() -> None:
    guard = LocalRequestGuard(per_minute=10, per_day=100)
    session_id = uuid4()
    second_acquired: bool | None = None

    async with guard.session_lock(session_id) as first_acquired:
        async def attempt() -> None:
            nonlocal second_acquired
            async with guard.session_lock(session_id) as acquired:
                second_acquired = acquired

        await asyncio.create_task(attempt())

    assert first_acquired
    assert second_acquired is False


@pytest.mark.skipif(not os.getenv("TEST_REDIS_URL"), reason="Redis integration URL not set")
async def test_redis_rate_limit_and_distributed_lock() -> None:
    guard = RedisRequestGuard(
        url=os.environ["TEST_REDIS_URL"],
        per_minute=1,
        per_day=2,
    )
    session_id = uuid4()
    ip = f"ci-{uuid4()}"

    first = await guard.check_rate_limit(ip_address=ip, session_id=session_id)
    blocked = await guard.check_rate_limit(ip_address=ip, session_id=session_id)
    async with (
        guard.session_lock(session_id) as acquired,
        guard.session_lock(session_id) as second_acquired,
    ):
        assert acquired
        assert not second_acquired

    assert first.allowed
    assert not blocked.allowed
    assert await guard.ready()
