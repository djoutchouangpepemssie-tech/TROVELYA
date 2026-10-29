"""Request and response bodies of the catalog module (section 11.5, « Catalogue »)."""

import unicodedata
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
)

from trovelya.modules.catalog.models import (
    AttributeType,
    BrandPolicy,
    ItemCondition,
    ListingStatus,
    TransactionModel,
    Vertical,
)


class CategoryAttributeOut(BaseModel):
    key: str
    required: bool
    filterable: bool


class CategoryOut(BaseModel):
    key: str
    parent_key: str | None
    name: str
    icon: str | None
    position: int
    is_leaf: bool  # listings are published in leaves only
    vertical: Vertical
    transaction_model: TransactionModel
    shipping_allowed: bool
    max_photos: int
    is_restricted: bool  # always reviewed by a person before publication
    brand_policy: BrandPolicy
    allowed_conditions: list[ItemCondition] | None  # None: every condition
    attributes: list[CategoryAttributeOut]  # inherited ones included, in display order


class AttributeValueOut(BaseModel):
    key: str
    name: str


class AttributeOut(BaseModel):
    key: str
    name: str
    type: AttributeType
    unit: str | None
    values: list[AttributeValueOut] | None  # enum attributes only, in display order
    min: float | None = None
    max: float | None = None
    step: float | None = None
    max_length: int | None = None


class CategoryTree(BaseModel):
    """Active categories, parents before their children, and the attributes they use."""

    categories: list[CategoryOut]
    attributes: list[AttributeOut]


class BrandOut(BaseModel):
    name: str
    slug: str


class BrandList(BaseModel):
    brands: list[BrandOut] = Field(max_length=10)


def _printable(value: str) -> str:
    """Line breaks of any system become `\n`; no other control character but tabs (PostgreSQL
    refuses NUL)."""
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    if any(unicodedata.category(c) == "Cc" and c not in "\n\t" for c in value):
        raise ValueError("control characters are not accepted")
    return value


def _one_line(value: str) -> str:
    value = _printable(value)
    if "\n" in value or "\t" in value:
        raise ValueError("one line")
    return value


# An attribute's key as the seed writes them: never echoed back in another shape.
AttributeKey = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$", max_length=64)]
ParcelSize = Literal["xs", "s", "m", "l", "xl"]


class Money(BaseModel):
    """Section 11.1: an amount in minor units and its currency; euros only for now."""

    amount_minor: int = Field(ge=100, le=100_000_000)
    currency: Literal["EUR"] = "EUR"


class ListingLocationIn(BaseModel):
    """One of the seller's addresses or search zones (section 8.11)."""

    source: Literal["address", "zone"]
    id: UUID


def _distinct(media_ids: list[UUID]) -> list[UUID]:
    if len(set(media_ids)) != len(media_ids):
        raise ValueError("each photo once")
    return media_ids


# Trimmed before the lengths are checked (the database checks the same lengths).
Title = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=5, max_length=120),
    AfterValidator(_one_line),
]
Description = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=20, max_length=5000),
    AfterValidator(_printable),
]
# A leaf's key, from /v1/categories (the format the table checks).
CategoryKey = Annotated[
    str, StringConstraints(max_length=200, pattern=r"^[a-z0-9_]+(\.[a-z0-9_]+)*$")
]
BrandName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=80),
    AfterValidator(_one_line),
]
Attributes = Annotated[dict[AttributeKey, Any], Field(max_length=100)]
WeightG = Annotated[int, Field(gt=0, le=1_000_000)]
# E16: the photos in display order, 1 at least; the category says how many at most.
MediaIds = Annotated[list[UUID], Field(min_length=1, max_length=50), AfterValidator(_distinct)]


class ListingDraftIn(BaseModel):
    """A new draft (section 11.5): what the seller says about the item."""

    model_config = ConfigDict(extra="forbid")

    title: Title
    description: Description
    category: CategoryKey
    brand: BrandName | None = None
    condition: ItemCondition
    attributes: Attributes = Field(default_factory=dict[AttributeKey, Any])
    price: Money
    accepts_offers: bool = True
    handover_enabled: bool = True
    shipping_enabled: bool = True
    parcel_size: ParcelSize | None = None
    weight_g: WeightG | None = None
    location: ListingLocationIn
    media_ids: MediaIds


class ListingDraftPatch(BaseModel):
    """The fields of a draft that change (`PATCH`); the others stay. `brand`, `parcel_size` and
    `weight_g` are removed with null; `attributes` and `media_ids` are replaced whole."""

    model_config = ConfigDict(extra="forbid")

    # Absent by default; null is refused by the field's type except for the three clearable
    # fields, so the published schema says the truth.
    title: Annotated[Title, Field(default=None)]
    description: Annotated[Description, Field(default=None)]
    category: Annotated[CategoryKey, Field(default=None)]
    brand: BrandName | None = None
    condition: Annotated[ItemCondition, Field(default=None)]
    attributes: Annotated[Attributes, Field(default=None)]
    price: Annotated[Money, Field(default=None)]
    accepts_offers: Annotated[bool, Field(default=None)]
    handover_enabled: Annotated[bool, Field(default=None)]
    shipping_enabled: Annotated[bool, Field(default=None)]
    parcel_size: ParcelSize | None = None
    weight_g: WeightG | None = None
    location: Annotated[ListingLocationIn, Field(default=None)]
    media_ids: Annotated[MediaIds, Field(default=None)]


class ListingOut(BaseModel):
    """The seller's own view of a listing. Never a coordinate: the place name only (8.11)."""

    id: UUID
    short_id: str
    status: ListingStatus
    version: int  # If-Match value of PATCH /v1/listings/{id}
    title: str
    description: str
    category: str
    brand: str | None
    condition: ItemCondition
    attributes: dict[str, Any]
    price: Money
    accepts_offers: bool
    handover_enabled: bool
    shipping_enabled: bool
    parcel_size: ParcelSize | None
    weight_g: int | None
    place_name: str
    country_code: str
    location: ListingLocationIn
    media_ids: list[UUID]
    created_at: datetime
    updated_at: datetime
