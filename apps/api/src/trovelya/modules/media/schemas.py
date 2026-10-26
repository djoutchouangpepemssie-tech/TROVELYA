"""Request and response bodies of the media module (section 11.5, « Catalogue »)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from trovelya.modules.media.models import UploadPurpose


class UploadIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purpose: UploadPurpose
    mime_type: str = Field(max_length=100)
    bytes: int = Field(ge=1, description="Exact size of the file: it is part of the signature")


class UploadOut(BaseModel):
    media_id: UUID
    upload_url: str
    headers: dict[str, str]  # to send exactly as given with the PUT
    expires_at: datetime
