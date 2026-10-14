"""Атомарное окно Redis: 60 запросов/мин, ключи только из HMAC(IP) (T-01 / SR-25)."""

from uuid import uuid4

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.exceptions import ServiceUnavailable

CATALOG_LIMIT = 60
WINDOW_MS = 60_000
SLIDING_WINDOW = """
local clock = redis.call('TIME')
local now = tonumber(clock[1]) * 1000 + math.floor(tonumber(clock[2]) / 1000)
local window = tonumber(ARGV[1])
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now - window)
if redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[2]) then
  local oldest = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
  local retry = math.max(1, math.ceil((tonumber(oldest[2]) + window - now) / 1000))
  local audit = redis.call('SET', KEYS[2], ARGV[3], 'NX', 'PX', window)
  return {retry, audit and 1 or 0}
end
redis.call('ZADD', KEYS[1], now, ARGV[3])
redis.call('PEXPIRE', KEYS[1], window)
return {0, 0}
"""


async def check_catalog(redis: Redis, ip_hash: str) -> tuple[int, str | None]:
    """Возвращает Retry-After и token резервирования аудита; при сбое закрывает доступ."""
    token = uuid4().hex
    try:
        result = await redis.eval(
            SLIDING_WINDOW,
            2,
            f"catalog:{{{ip_hash}}}",
            f"catalog:{{{ip_hash}}}:audit",
            WINDOW_MS,
            CATALOG_LIMIT,
            token,
        )
    except RedisError:
        raise ServiceUnavailable from None
    return int(result[0]), token if result[1] else None


async def release_catalog_audit(redis: Redis, ip_hash: str, token: str) -> None:
    """При неудаче БД освобождает только собственный marker, не чужую новую резервацию."""
    script = """
    if redis.call('GET', KEYS[1]) == ARGV[1] then
      return redis.call('DEL', KEYS[1])
    end
    return 0
    """
    try:
        await redis.eval(script, 1, f"catalog:{{{ip_hash}}}:audit", token)
    except RedisError:
        raise ServiceUnavailable from None
