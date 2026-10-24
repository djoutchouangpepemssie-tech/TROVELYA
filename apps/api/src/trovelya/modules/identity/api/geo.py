"""Place search for addresses and search zones (`/v1/geo/*`, P1-T06a).

Signed-in members only, 30 requests per minute each (the geocoder is a shared public
service). `reverse` is for the browser's position, asked only after the `location` consent.
"""

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Query, Request

from trovelya.core.errors import AppError, ErrorCode
from trovelya.core.ratelimit import hit
from trovelya.modules.identity.adapters.geocoder import Geocoder, GeocoderUnavailableError, Place
from trovelya.modules.identity.schemas import PlaceList, PlaceOut
from trovelya.modules.identity.service import CurrentUser
from trovelya.modules.identity.service.auth import completed_user

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1/geo", tags=["geo"])
PER_USER_PER_MINUTE = 30


async def _limited_user(
    request: Request, user: Annotated[CurrentUser, Depends(completed_user)]
) -> CurrentUser:
    try:
        retry_after = await hit(
            request.app.state.redis,
            f"geo:{user.id}",
            limit=PER_USER_PER_MINUTE,
            window_s=60,
        )
    except Exception as exc:  # noqa: BLE001 — fail open, see core/ratelimit.py
        logger.warning("ratelimit.redis_unavailable", error=type(exc).__name__)
        return user
    if retry_after is not None:
        raise AppError(ErrorCode.RATE_LIMITED, 429, headers={"Retry-After": str(retry_after)})
    return user


Member = Annotated[CurrentUser, Depends(_limited_user)]


def _out(place: Place) -> PlaceOut:
    return PlaceOut(
        label=place.label,
        place_name=place.place_name,
        city=place.city,
        postal_code=place.postal_code,
        district=place.district,
        country_code=place.country_code,
        lat=place.lat,
        lon=place.lon,
    )


def _geocoder(request: Request) -> Geocoder:
    geocoder: Geocoder = request.app.state.geocoder
    return geocoder


@router.get("/search", operation_id="geo_search")
async def search(
    request: Request,
    _: Member,
    q: Annotated[str, Query(min_length=3, max_length=200)],
) -> PlaceList:
    """Address or town autocompletion (France)."""
    try:
        places = await _geocoder(request).search(q.strip(), limit=5)
    except GeocoderUnavailableError as exc:
        logger.warning("geocoder.unavailable", error=str(exc))
        raise AppError(ErrorCode.SERVICE_UNAVAILABLE, 503) from exc
    return PlaceList(data=[_out(p) for p in places])


@router.get("/reverse", operation_id="geo_reverse")
async def reverse(
    request: Request,
    _: Member,
    lat: Annotated[float, Query(ge=-90, le=90)],
    lon: Annotated[float, Query(ge=-180, le=180)],
) -> PlaceOut:
    """The place at the browser's position; 404 when there is none (at sea, abroad)."""
    try:
        place = await _geocoder(request).reverse(lat, lon)
    except GeocoderUnavailableError as exc:
        logger.warning("geocoder.unavailable", error=str(exc))
        raise AppError(ErrorCode.SERVICE_UNAVAILABLE, 503) from exc
    if place is None:
        raise AppError(ErrorCode.NOT_FOUND, 404)
    return _out(place)
