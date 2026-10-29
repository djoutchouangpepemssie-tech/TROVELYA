"""Catalog jobs run by the worker (workers/main.py)."""

from typing import Any

from trovelya.modules.catalog.service.expiry import expire_listings
from trovelya.modules.catalog.service.retention import purge_ended_listings


async def expire_listings_job(ctx: dict[str, Any]) -> int:
    return await expire_listings(ctx["sessionmaker"], clock=ctx["clock"])


async def purge_ended_listings_job(ctx: dict[str, Any]) -> int:
    return await purge_ended_listings(ctx["sessionmaker"], clock=ctx["clock"])
