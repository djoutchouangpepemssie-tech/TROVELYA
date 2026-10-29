"""Request and response bodies of the catalog module (section 11.5, « Catalogue »)."""

import unicodedata
from datetime import date, datetime
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


class QualityTip(BaseModel):
    """What would raise the score: `photos` (add `count`), `description` (write more), `brand`,
    `attribute` (fill `attribute`, labelled `label`), worth `gain` points."""

    code: Literal["photos", "description", "brand", "attribute"]
    gain: int
    count: int | None
    attribute: str | None
    label: str | None


class Quality(BaseModel):
    """The listing's quality, 0 to 100 (P2-T07), with its tips, the most rewarding first."""

    score: int = Field(ge=0, le=100)
    tips: list[QualityTip]


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
    published_at: datetime | None  # the last time it went online
    expires_at: datetime | None  # while online: when it expires (Q15)
    quality: Quality


class ModerationReason(BaseModel):
    code: str  # `alcohol`, `weapons`… (8.17), `restricted_category`
    label: str  # in French, for the seller


class ModerationOut(BaseModel):
    """What the moderation decided when the listing was put online (P2-T05b)."""

    outcome: Literal["online", "review", "refused"]
    reasons: list[ModerationReason]
    notice: str | None  # the reminder when contact details were masked (Q12)


class PublishedOut(ListingOut):
    """The listing after `publish` or `renew`, with the moderation's decision."""

    moderation: ModerationOut


class CategoryRef(BaseModel):
    key: str
    name: str


class AttributeShown(BaseModel):
    """An attribute as shown on the page: its label, its value and the value's label (enums)."""

    key: str
    name: str
    value: Any
    value_name: str | None
    unit: str | None


class PhotoVariant(BaseModel):
    format: str
    width: int
    height: int
    url: str


class SellerOut(BaseModel):
    """What the page shows of the seller (level, badges and rank arrive with later phases)."""

    id: UUID
    username: str
    display_name: str
    avatar: list[PhotoVariant] | None
    member_since: date


class ListingPage(BaseModel):
    """The listing page (section 11.5). Never a coordinate (8.11): the place name and, for a
    signed-in visitor with a zone, the distance to the public position, rounded (Q17)."""

    id: UUID
    short_id: str
    status: ListingStatus
    title: str
    description: str
    category: CategoryRef
    brand: str | None
    condition: ItemCondition
    attributes: list[AttributeShown]
    price: Money
    accepts_offers: bool
    handover_enabled: bool
    shipping_enabled: bool
    parcel_size: ParcelSize | None
    weight_g: int | None
    place_name: str
    distance: str | None
    photos: list[list[PhotoVariant]]
    seller: SellerOut
    published_at: datetime | None
    updated_at: datetime


class ListingSummary(BaseModel):
    """A line of the seller's listings (W10): no coordinate, the first photo only."""

    id: UUID
    short_id: str
    status: ListingStatus
    title: str
    price: Money
    cover: list[PhotoVariant] | None
    version: int
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None
    expires_at: datetime | None


class PriceWatch(BaseModel):
    target_minor: int | None  # None: any drop


class PriceWatchIn(BaseModel):
    """Q43: from 1 € to below the current price; none to be told of any drop."""

    target_minor: int | None = Field(default=None, strict=True)


class FavoriteItem(BaseModel):
    """A listing in the member's favorites; `available` False once it left (sold, withdrawn,
    expired, removed, or its seller is not shown)."""

    id: UUID
    short_id: str
    title: str
    price: Money
    cover: list[PhotoVariant] | None
    available: bool
    favorited_at: datetime
    price_watch: PriceWatch | None


class FavoritePage(BaseModel):
    data: list[FavoriteItem]
    next_cursor: str | None
    has_more: bool


class PricePoint(BaseModel):
    at: datetime
    price: Money


class PriceHistory(BaseModel):
    """The prices shown online, from the first time online (Q43), oldest first."""

    prices: list[PricePoint]


class ListingSummaryPage(BaseModel):
    """Section 11.3: a page and the cursor of the next one."""

    data: list[ListingSummary]
    next_cursor: str | None
    has_more: bool


class ReviewDetection(BaseModel):
    """What the anti-circumvention found in a listing (never the original text)."""

    part: str | None  # title or description
    signals: list[str]
    action_taken: str  # masked or queued
    review_status: str


class ReviewItem(BaseModel):
    """A listing awaiting moderation in the staff's queue (P2-T05c1)."""

    id: UUID
    short_id: str
    title: str
    description: str
    category: str
    category_name: str
    price: Money
    seller_id: UUID
    submitted_at: datetime
    reasons: list[ModerationReason]
    reason_text: str | None
    photos: list[list[dict[str, Any]]]
    detections: list[ReviewDetection]


class ReviewQueue(BaseModel):
    items: list[ReviewItem]
    # The closed list a rejection or a removal takes its reason from (`other` needs a text).
    reject_reasons: list[ModerationReason]


class StaffDecisionIn(BaseModel):
    """A rejection or a removal: a reason from the closed list, explained for `other`."""

    reason_code: str = Field(min_length=1, max_length=64)
    reason_text: str | None = Field(default=None, max_length=1000, pattern=r"^[^\x00-\x1f]*$")


class StaffDecisionOut(BaseModel):
    id: UUID
    status: ListingStatus
