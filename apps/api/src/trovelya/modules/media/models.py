"""Media value types (section 7.5, ADR-0019). Rows are read and written with SQL in
repository.py."""

from typing import Literal

MediaStatus = Literal["uploading", "processing", "ready", "rejected"]
# P2 handles photos only (decision Q7): of the purposes of 7.5, listing photos and avatars.
UploadPurpose = Literal["listing", "avatar"]
# Formats a browser or a phone produces and the worker can decode; never SVG (scripts), GIF
# or HEIC (the camera input asks the phone for JPEG).
IMAGE_TYPES = frozenset({"image/jpeg", "image/png", "image/webp", "image/avif"})
