"""Addresses, search zones and preferences: `/v1/me/{addresses,zones,preferences}` (P1-T06)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from trovelya.modules.identity.schemas import (
    AddressIn,
    AddressList,
    AddressOut,
    AddressPatch,
    Preferences,
    ZoneIn,
    ZoneList,
    ZoneOut,
    ZonePatch,
)
from trovelya.modules.identity.service import CurrentUser, get_clock
from trovelya.modules.identity.service import places as service
from trovelya.modules.identity.service.auth import Uow, completed_user
from trovelya.shared.clock import Clock

router = APIRouter(prefix="/v1/me", tags=["me"])

Member = Annotated[CurrentUser, Depends(completed_user)]


@router.get("/addresses", operation_id="me_addresses_list")
async def list_addresses(db: Uow, user: Member) -> AddressList:
    rows = await service.list_addresses(db, user=user)
    return AddressList(data=[AddressOut.model_validate(r, from_attributes=True) for r in rows])


@router.post("/addresses", operation_id="me_addresses_create", status_code=201)
async def create_address(body: AddressIn, db: Uow, user: Member) -> AddressOut:
    row = await service.create_address(db, user=user, values=body.model_dump())
    return AddressOut.model_validate(row, from_attributes=True)


@router.patch("/addresses/{address_id}", operation_id="me_addresses_update")
async def update_address(address_id: UUID, body: AddressPatch, db: Uow, user: Member) -> AddressOut:
    changes = body.model_dump(exclude_unset=True)
    row = await service.update_address(db, user=user, address_id=address_id, changes=changes)
    return AddressOut.model_validate(row, from_attributes=True)


@router.delete(
    "/addresses/{address_id}",
    operation_id="me_addresses_delete",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_address(
    address_id: UUID, db: Uow, user: Member, clock: Annotated[Clock, Depends(get_clock)]
) -> None:
    await service.delete_address(db, user=user, address_id=address_id, clock=clock)


@router.get("/zones", operation_id="me_zones_list")
async def list_zones(db: Uow, user: Member) -> ZoneList:
    rows = await service.list_zones(db, user=user)
    return ZoneList(data=[ZoneOut.model_validate(r, from_attributes=True) for r in rows])


@router.post("/zones", operation_id="me_zones_create", status_code=201)
async def create_zone(body: ZoneIn, db: Uow, user: Member) -> ZoneOut:
    values = body.model_dump()
    values["radius_m"] = values.pop("radius_km") * 1000
    row = await service.create_zone(db, user=user, values=values)
    return ZoneOut.model_validate(row, from_attributes=True)


@router.patch("/zones/{zone_id}", operation_id="me_zones_update")
async def update_zone(zone_id: UUID, body: ZonePatch, db: Uow, user: Member) -> ZoneOut:
    changes = body.model_dump(exclude_unset=True)
    if "radius_km" in changes:
        changes["radius_m"] = changes.pop("radius_km") * 1000
    row = await service.update_zone(db, user=user, zone_id=zone_id, changes=changes)
    return ZoneOut.model_validate(row, from_attributes=True)


@router.delete(
    "/zones/{zone_id}", operation_id="me_zones_delete", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_zone(zone_id: UUID, db: Uow, user: Member) -> None:
    await service.delete_zone(db, user=user, zone_id=zone_id)


@router.get("/preferences", operation_id="me_preferences_get")
async def get_preferences(db: Uow, user: Member) -> Preferences:
    return Preferences.model_validate(await service.get_preferences(db, user=user))


@router.put("/preferences", operation_id="me_preferences_put")
async def put_preferences(body: Preferences, db: Uow, user: Member) -> Preferences:
    """Replace all preferences; a field not sent goes back to its default."""
    await service.save_preferences(db, user=user, values=body.model_dump())
    return Preferences.model_validate(await service.get_preferences(db, user=user))
