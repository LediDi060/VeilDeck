"""Реальные Lua/TTL Redis; TEST_REDIS_URL должен указывать на отдельную БД 15."""

import asyncio
import os

import pytest
from redis.asyncio import Redis

from app.core.ratelimit import check_catalog, release_catalog_audit

pytestmark = pytest.mark.skipif(not os.getenv("TEST_REDIS_URL"), reason="нужен TEST_REDIS_URL (БД 15)")


@pytest.fixture
async def limiter_redis():
    """Очищает только явно выделенную тестовую БД 15."""
    redis = Redis.from_url(os.environ["TEST_REDIS_URL"])
    assert redis.connection_pool.connection_kwargs["db"] == 15
    await redis.flushdb()
    yield redis
    await redis.flushdb()
    await redis.aclose()


async def test_tc_rl_atomic_parallel_requests(limiter_redis):
    """Из 80 параллельных запросов проходят ровно 60, аудит резервируется один раз."""
    results = await asyncio.gather(*(check_catalog(limiter_redis, "a" * 64) for _ in range(80)))
    assert sum(retry == 0 for retry, _ in results) == 60
    assert all(1 <= retry <= 60 for retry, _ in results if retry)
    assert sum(bool(audit) for _, audit in results) == 1
    assert 0 < await limiter_redis.pttl("catalog:{" + "a" * 64 + "}") <= 60_000
    assert await check_catalog(limiter_redis, "b" * 64) == (0, None)


async def test_tc_rl_old_entries_leave_window(limiter_redis):
    """События за пределами окна перестают расходовать лимит."""
    seconds, microseconds = await limiter_redis.time()
    now = seconds * 1000 + microseconds // 1000
    key = "catalog:{" + "c" * 64 + "}"
    await limiter_redis.zadd(key, {str(index): now - 60_001 for index in range(60)})
    assert await check_catalog(limiter_redis, "c" * 64) == (0, None)
    assert await limiter_redis.zcard(key) == 1


async def test_tc_rl_failed_audit_retries_without_releasing_other_owner(limiter_redis):
    """После сбоя БД новая резервация возможна; чужой token не удаляется."""
    ip_hash = "d" * 64
    for _ in range(60):
        await check_catalog(limiter_redis, ip_hash)
    retry, token = await check_catalog(limiter_redis, ip_hash)
    assert retry > 0 and token
    await release_catalog_audit(limiter_redis, ip_hash, "wrong-token")
    assert (await check_catalog(limiter_redis, ip_hash))[1] is None
    await release_catalog_audit(limiter_redis, ip_hash, token)
    retry, replacement = await check_catalog(limiter_redis, ip_hash)
    assert retry > 0 and replacement and replacement != token
    await release_catalog_audit(limiter_redis, ip_hash, token)
    assert (await check_catalog(limiter_redis, ip_hash))[1] is None
