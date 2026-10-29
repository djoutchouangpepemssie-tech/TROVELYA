"""The quality of a listing, 0 to 100 (section 7.5 `quality_score`, P2-T07, plan Q42): its
photos, description, optional attributes and brand. Pure: what the listing has in, its score
and the tips that would raise it, each worth exactly the points it adds, the most rewarding
first. The points are a [PARAM] (`listings.quality_formula`), checked strictly to total 100.

Q42 details: the photos' points are reached at the category's own maximum when it allows fewer
than the formula counts; an attribute set to `false` or 0 is filled (only absent or null is
not); the description is measured with runs of blanks counted as one. Exact arithmetic,
half-points rounded up."""

from dataclasses import dataclass, replace
from fractions import Fraction
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError

TipCode = Literal["photos", "description", "brand", "attribute"]
HALF = Fraction(1, 2)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _Photos(_Strict):
    first: StrictInt = Field(ge=0)
    each: StrictInt = Field(ge=0)
    up_to: StrictInt = Field(ge=1)


class _Description(_Strict):
    points: StrictInt = Field(ge=0)
    from_: StrictInt = Field(ge=0, alias="from")
    full: StrictInt = Field(ge=1)


class Formula(_Strict):
    photos: _Photos
    description: _Description
    attributes: StrictInt = Field(ge=0)
    brand: StrictInt = Field(ge=0)

    @property
    def photo_points(self) -> int:
        return self.photos.first + self.photos.each * (self.photos.up_to - 1)

    @classmethod
    def parse(cls, raw: Any) -> "Formula":
        """ValueError for a malformed formula, or one that does not total 100 points."""
        try:
            formula = cls.model_validate(raw)
        except ValidationError as exc:
            raise ValueError(f"listings.quality_formula is malformed: {exc}") from exc
        if formula.description.from_ >= formula.description.full:
            raise ValueError("listings.quality_formula: the description needs from < full")
        total = formula.photo_points + formula.description.points + formula.attributes
        if total + formula.brand != 100:
            raise ValueError("listings.quality_formula must total 100 points")
        return formula


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
    """What the listing has in. `optional_attributes`: key and label of its category's optional
    attributes; `attributes`: the listing's values."""

    photos: int
    max_photos: int  # the category's maximum
    description: str
    attributes: dict[str, Any]
    optional_attributes: tuple[tuple[str, str], ...]
    brand_expected: bool  # the category names a brand (required or optional)
    has_brand: bool


@dataclass(frozen=True, slots=True)
class Tip:
    code: TipCode
    gain: int  # the points it adds, exactly
    count: int | None = None  # photos to add
    attribute: str | None = None
    label: str | None = None


@dataclass(frozen=True, slots=True)
class Quality:
    score: int
    tips: tuple[Tip, ...]


def _round(value: Fraction) -> int:
    return int(value + HALF) if value >= 0 else 0  # half up


def _photo_points(photos: int, max_photos: int, formula: Formula) -> Fraction:
    target = max(min(formula.photos.up_to, max_photos), 1)
    kept = min(max(photos, 0), target)
    if kept == 0:
        return Fraction(0)

    def base(n: int) -> int:
        return formula.photos.first + formula.photos.each * (n - 1)

    if base(target) == 0:
        return Fraction(formula.photo_points)
    return Fraction(formula.photo_points * base(kept), base(target))


def _filled(value: Any) -> bool:
    return value is not None  # `false` and 0 are answers too (Q42)


def _score(facts: Facts, formula: Formula) -> Fraction:
    photos = _photo_points(facts.photos, facts.max_photos, formula)
    text = formula.description
    length = len(" ".join(facts.description.split()))
    span = text.full - text.from_
    description = Fraction(text.points * min(max(length - text.from_, 0), span), span)
    optional = facts.optional_attributes
    filled = sum(1 for key, _ in optional if _filled(facts.attributes.get(key)))
    attributes = (
        Fraction(formula.attributes * filled, len(optional))
        if optional
        else Fraction(formula.attributes)
    )
    brand = formula.brand if facts.has_brand or not facts.brand_expected else 0
    return photos + description + attributes + brand


def quality(facts: Facts, formula: Formula) -> Quality:
    score = min(_round(_score(facts, formula)), 100)
    target = max(min(formula.photos.up_to, facts.max_photos), 1)
    candidates: list[tuple[Tip, Facts]] = [
        (Tip("photos", 0, max(target - facts.photos, 0)), replace(facts, photos=target)),
        (Tip("description", 0), replace(facts, description="x" * formula.description.full)),
        (Tip("brand", 0), replace(facts, has_brand=True)),
    ]
    for key, label in facts.optional_attributes:
        if not _filled(facts.attributes.get(key)):
            done = replace(facts, attributes=facts.attributes | {key: "set"})
            candidates.append((Tip("attribute", 0, attribute=key, label=label), done))
    tips = [
        replace(tip, gain=gain)
        for tip, followed in candidates
        if (gain := min(_round(_score(followed, formula)), 100) - score) > 0
    ]
    tips.sort(key=lambda tip: -tip.gain)  # stable: equal gains keep their order
    return Quality(score=score, tips=tuple(tips))
