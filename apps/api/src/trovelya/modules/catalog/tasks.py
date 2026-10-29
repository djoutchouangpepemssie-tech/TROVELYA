"""Catalog jobs run by the worker (workers/main.py)."""

from typing import Any
from uuid import UUID

from trovelya.modules.catalog.service.embeddings import embed_listing, reindex
from trovelya.modules.catalog.service.expiry import expire_listings
from trovelya.modules.catalog.service.retention import purge_ended_listings


async def expire_listings_job(ctx: dict[str, Any]) -> int:
    return await expire_listings(ctx["sessionmaker"], clock=ctx["clock"])


async def purge_ended_listings_job(ctx: dict[str, Any]) -> int:
    return await purge_ended_listings(ctx["sessionmaker"], clock=ctx["clock"])


async def embed_listing_job(ctx: dict[str, Any], listing_id: str) -> bool:
    """ADR-0020: enqueued when a listing goes online; nothing without an embedder."""
    embedder = ctx.get("embedder")
    if embedder is None:
        return False
    return await embed_listing(ctx["sessionmaker"], embedder, UUID(listing_id))


async def reindex_embeddings_job(ctx: dict[str, Any]) -> int:
    embedder = ctx.get("embedder")
    return 0 if embedder is None else await reindex(ctx["sessionmaker"], embedder)
