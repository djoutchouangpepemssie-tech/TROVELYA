"""What a provider must answer (P2-T06a): a JSON object of this schema, or nothing is kept.
Only the shape is checked here; the catalogue then keeps the values it allows."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Text = Annotated[str, StringConstraints(max_length=500)]
Value = Annotated[str, StringConstraints(max_length=200)] | int | float | bool
Confidence = Annotated[float, Field(ge=0, le=1)]


class ListingSuggestion(BaseModel):
    """Each field may be missing; a field the model added beyond these is ignored."""

    model_config = ConfigDict(strict=True, extra="ignore")

    title: Text | None = None
    category_key: Annotated[str, StringConstraints(max_length=200)] | None = None
    brand: Annotated[str, StringConstraints(max_length=200)] | None = None
    condition: Annotated[str, StringConstraints(max_length=50)] | None = None
    attributes: Annotated[dict[str, Value], Field(max_length=50)] = Field(
        default_factory=dict[str, Value]
    )
    caption: Text | None = None
    confidence: Annotated[dict[str, Confidence], Field(max_length=20)] = Field(
        default_factory=dict[str, Confidence]
    )
