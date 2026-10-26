"""Catalog value types (section 7.5). Rows are read and written with SQL in repository.py."""

from enum import StrEnum
from typing import Literal

Vertical = Literal["goods", "real_estate", "vehicles", "services"]
TransactionModel = Literal["protected_purchase", "contact", "mixed"]
BrandPolicy = Literal["required", "optional", "none"]
AttributeType = Literal["text", "int", "decimal", "enum", "bool", "year"]


class ListingStatus(StrEnum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    ACTIVE = "active"
    RESERVED = "reserved"
    SOLD = "sold"
    WITHDRAWN = "withdrawn"
    REMOVED = "removed"
    EXPIRED = "expired"


class ItemCondition(StrEnum):
    NEW_WITH_TAGS = "new_with_tags"
    NEW_WITHOUT_TAGS = "new_without_tags"
    VERY_GOOD = "very_good"
    GOOD = "good"
    FAIR = "fair"
    FOR_PARTS = "for_parts"
