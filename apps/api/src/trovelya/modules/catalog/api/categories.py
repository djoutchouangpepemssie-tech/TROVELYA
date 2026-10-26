"""The category tree and brand suggestions (`/v1/categories`, `/v1/brands`), open to all."""

import hashlib
from typing import Annotated

from fastapi import APIRouter, Query, Request, Response
from pydantic import AfterValidator

from trovelya.core.db import Uow
from trovelya.modules.catalog.schemas import BrandList, CategoryTree
from trovelya.modules.catalog.service import categories as categories_service

router = APIRouter(prefix="/v1", tags=["catalog"])

# Section 11.5: the tree is cached one hour by the CDN; the ETag spares the download when
# nothing changed.
CACHE_CONTROL = "public, max-age=3600"


@router.get(
    "/categories",
    operation_id="catalog_categories",
    response_model=CategoryTree,
    responses={304: {"description": "Unchanged since the ETag sent in If-None-Match"}},
)
async def get_categories(request: Request, db: Uow) -> Response:
    verticals = await request.app.state.flags.is_enabled("verticals")
    tree = await categories_service.category_tree(db, verticals=verticals)
    body = tree.model_dump_json().encode()
    etag = '"' + hashlib.sha256(body).hexdigest()[:32] + '"'
    headers = {"ETag": etag, "Cache-Control": CACHE_CONTROL}
    # A CDN may send the tag back weak (W/"…"); the body is the same either way.
    tags = request.headers.get("if-none-match", "").split(",")
    sent = {tag.strip().removeprefix("W/") for tag in tags}
    if etag in sent or "*" in sent:
        return Response(status_code=304, headers=headers)
    return Response(content=body, media_type="application/json", headers=headers)


def _brand_query(q: str) -> str:
    """Two characters at least once trimmed; no control character (PostgreSQL refuses NUL)."""
    q = q.strip()
    if len(q) < 2 or any(ord(c) < 32 or ord(c) == 127 for c in q):
        raise ValueError("2 to 80 printable characters")
    return q


BrandQuery = Annotated[str, Query(min_length=2, max_length=80), AfterValidator(_brand_query)]


@router.get("/brands", operation_id="catalog_brands")
async def get_brands(db: Uow, q: BrandQuery) -> BrandList:
    """Up to 10 brands: names starting with `q` first, then the closest spellings."""
    return await categories_service.search_brands(db, q)
