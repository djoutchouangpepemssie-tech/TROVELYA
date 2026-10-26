"""Request and response bodies of the catalog module (section 11.5, « Catalogue »)."""

from pydantic import BaseModel, Field

from trovelya.modules.catalog.models import (
    AttributeType,
    BrandPolicy,
    ItemCondition,
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
