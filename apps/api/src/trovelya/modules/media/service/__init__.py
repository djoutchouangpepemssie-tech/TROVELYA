"""Public service of the media module: the only entry point for other modules."""

from trovelya.modules.media.service import avatars as avatars
from trovelya.modules.media.service import gdpr as gdpr
from trovelya.modules.media.service import listing_photos as listing_photos
from trovelya.modules.media.service import uploads as uploads

__all__ = ["avatars", "gdpr", "listing_photos", "uploads"]
