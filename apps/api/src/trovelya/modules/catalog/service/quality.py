"""The quality of a listing, 0 to 100 (section 7.5 `quality_score`, P2-T07, plan Q42): its
photos, description, optional attributes and brand. Pure: what the listing has in, its score
and the tips that would raise it, the most rewarding first. The points are a [PARAM]
(`listings.quality_formula`), checked to total 100."""

from dataclasses import dataclass
from typing import Any, Literal

TipCode = Literal["photos", "description", "brand", "attribute"]


@dataclass(frozen=True, slots=True)
class Formula:
    raw: dict[str, Any]
    first_photo: int
    each_photo: int
    photos_up_to: int
    description: int
    description_from: int
    description_full: int
    attributes: int
    brand: int

    @classmethod
    def parse(cls, raw: dict[str, Any]) -> "Formula":
        """ValueError for a formula that does not total 100 points."""
        photos, description = raw["photos"], raw["description"]
        formula = cls(
            raw=raw,
            first_photo=int(photos["first"]),
            each_photo=int(photos["each"]),
            photos_up_to=int(photos["up_to"]),
            description=int(description["points"]),
            description_from=int(description["from"]),
            description_full=int(description["full"]),
            attributes=int(raw["attributes"]),
            brand=int(raw["brand"]),
        )
        if (
            formula.photo_points(formula.photos_up_to)
            + formula.description
            + formula.attributes
            + formula.brand
            != 100
        ):
            raise ValueError("the quality formula must total 100 points")
        if not 0 <= formula.description_from < formula.description_full:
            raise ValueError("the description's points need from < full")
        return formula

    def photo_points(self, photos: int) -> int:
        kept = min(photos, self.photos_up_to)
        return 0 if kept == 0 else self.first_photo + self.each_photo * (kept - 1)


DEFAULT_FORMULA = Formula.parse(
    {
        "photos": {"first": 15, "each": 5, "up_to": 6},
        "description": {"points": 30, "from": 20, "full": 300},
        "attributes": 20,
        "brand": 10,
    }
)


@dataclass(frozen=True, slots=True)
class Facts:
    """What the listing has in: its photos, the length of its description, the optional
    attributes of its category (`missing_attributes`: key and label of the ones left empty)."""

    photos: int
    description_length: int
    missing_attributes: tuple[tuple[str, str], ...]
    optional_attributes: int
    brand_expected: bool  # the category names a brand (required or optional)
    has_brand: bool


@dataclass(frozen=True, slots=True)
class Tip:
    code: TipCode
    gain: int  # points it would add
    count: int | None = None  # photos to add
    attribute: str | None = None
    label: str | None = None


@dataclass(frozen=True, slots=True)
class Quality:
    score: int
    tips: tuple[Tip, ...]


def quality(facts: Facts, formula: Formula) -> Quality:
    tips: list[Tip] = []
    photos = formula.photo_points(facts.photos)
    if facts.photos < formula.photos_up_to:
        missing = formula.photos_up_to - max(facts.photos, 0)
        tips.append(Tip("photos", formula.photo_points(formula.photos_up_to) - photos, missing))
    span = formula.description_full - formula.description_from
    filled = min(max(facts.description_length - formula.description_from, 0), span) / span
    description = formula.description * filled
    if filled < 1:
        tips.append(Tip("description", max(round(formula.description - description), 1)))
    attributes = float(formula.attributes)
    if facts.optional_attributes:
        each = formula.attributes / facts.optional_attributes
        attributes -= each * len(facts.missing_attributes)
    brand = formula.brand if facts.has_brand or not facts.brand_expected else 0
    if not brand:
        tips.append(Tip("brand", formula.brand))
    for key, label in facts.missing_attributes:
        gain = max(round(formula.attributes / facts.optional_attributes), 1)
        tips.append(Tip("attribute", gain, attribute=key, label=label))
    score = round(photos + description + max(attributes, 0.0) + brand)
    ordered = sorted(tips, key=lambda tip: -tip.gain)  # stable: equal gains keep their order
    return Quality(score=max(0, min(score, 100)), tips=tuple(ordered))
