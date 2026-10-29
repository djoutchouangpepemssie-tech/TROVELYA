"""What a provider must answer (P2-T06a): a JSON object of this schema, or nothing is kept.
Only the shape is checked here; the catalogue then keeps the values it allows. What passes can
be stored as JSONB: no NaN nor infinity, no control character (NUL is refused by PostgreSQL)."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

PLAIN = r"^[^\x00-\x08\x0b\x0c\x0e-\x1f\x7f]*$"  # tabs and line breaks allowed

Text = Annotated[str, StringConstraints(min_length=1, max_length=500, pattern=PLAIN)]
Short = Annotated[str, StringConstraints(min_length=1, max_length=200, pattern=PLAIN)]
Key = Annotated[str, StringConstraints(min_length=1, max_length=64, pattern=PLAIN)]
Value = Short | int | float | bool
Confidence = Annotated[float, Field(ge=0, le=1)]


class ListingSuggestion(BaseModel):
    """Each field may be missing; a field the model added beyond these is ignored."""

    model_config = ConfigDict(strict=True, extra="ignore", allow_inf_nan=False)

    title: Text | None = None
    category_key: Short | None = None
    brand: Short | None = None
    condition: Key | None = None
    attributes: Annotated[dict[Key, Value], Field(max_length=50)] = Field(
        default_factory=dict[Key, Value]
    )
    caption: Text | None = None
    confidence: Annotated[dict[Key, Confidence], Field(max_length=20)] = Field(
        default_factory=dict[Key, Confidence]
    )
