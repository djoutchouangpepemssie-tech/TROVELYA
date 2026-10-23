"""Redis client (cache, locks, rate limits, job queue)."""

from redis.asyncio import Redis


def make_redis(url: str) -> Redis:
    return Redis.from_url(url, decode_responses=False)  # pyright: ignore[reportUnknownMemberType]


async def ping(client: Redis) -> None:
    await client.ping()  # pyright: ignore[reportUnknownMemberType]
