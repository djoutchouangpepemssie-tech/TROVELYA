"""Checking and re-encoding an uploaded image (section 13.2, ADR-0019). Pure and synchronous:
the worker runs it in a thread, one image at a time.

Nothing of the original file is served: its first bytes must match the declared type, it is
decoded within a pixel budget, oriented, converted to sRGB, then re-encoded from its pixels
only. EXIF (with GPS), XMP, IPTC, ICC profiles and any trailing bytes (a ZIP appended to a
JPEG) are left behind.
"""

import hashlib
import warnings
from dataclasses import dataclass
from io import BytesIO
from typing import cast

from PIL import Image, ImageCms, ImageOps

# 50 Mpx: a 12 Mpx phone photo passes with room to spare; a decompression bomb does not.
MAX_PIXELS = 50_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS
WIDTHS = (320, 640, 1080, 1600)  # section 11.5, never enlarged
FORMATS = ("avif", "webp")
_PIL_FORMAT = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP", "image/avif": "AVIF"}
_SAVE = {
    "avif": {"quality": 60, "speed": 8},
    "webp": {"quality": 80, "method": 4},
}
_SRGB = ImageCms.ImageCmsProfile(
    ImageCms.createProfile("sRGB")  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
)


class ImageRejectedError(Exception):
    """`reason` is stored as the media's rejection_reason."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class Variant:
    format: str
    width: int
    height: int
    data: bytes


@dataclass(frozen=True, slots=True)
class ProcessedImage:
    width: int
    height: int
    sha256: bytes  # of the original bytes, as uploaded
    dhash: int  # 64-bit difference hash of the oriented image, unsigned
    variants: list[Variant]


def detect_type(data: bytes) -> str | None:
    """The type the first bytes announce, among the accepted ones."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[4:8] == b"ftyp" and data[8:12] in {b"avif", b"avis"}:
        return "image/avif"
    return None


def hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def _decode(data: bytes, mime: str) -> Image.Image:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            image = Image.open(BytesIO(data), formats=[_PIL_FORMAT[mime]])
            if image.width * image.height > MAX_PIXELS:
                raise ImageRejectedError("too_many_pixels")
            image.load()
    except ImageRejectedError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ImageRejectedError("too_many_pixels") from None
    except (OSError, SyntaxError, ValueError, EOFError):
        raise ImageRejectedError("unreadable") from None
    return image


def _to_srgb(image: Image.Image) -> Image.Image:
    """Oriented, in sRGB, RGB or RGBA, with no metadata attached."""
    image = ImageOps.exif_transpose(image)
    alpha = image.mode in {"RGBA", "LA", "PA"} or "transparency" in image.info
    mode = "RGBA" if alpha else "RGB"
    icc = image.info.get("icc_profile")
    if icc:
        try:
            source = ImageCms.ImageCmsProfile(BytesIO(icc))
            image = (
                ImageCms.profileToProfile(image.convert(mode), source, _SRGB, outputMode=mode)
                or image
            )
        except (ImageCms.PyCMSError, OSError):
            pass  # an unusable profile: the pixels are taken as sRGB
    clean = Image.new(mode, image.size)
    clean.paste(image.convert(mode))
    return clean


def _dhash(image: Image.Image) -> int:
    """Each bit: is a cell brighter than its right neighbour, on a 9 x 8 area average (BOX), which
    a slight crop or re-compression barely moves."""
    small = image.convert("L").resize((9, 8), Image.Resampling.BOX)  # pyright: ignore[reportUnknownMemberType]
    pixels = cast(list[int], list(small.get_flattened_data()))  # one int per pixel in mode L
    bits = 0
    for row in range(8):
        for col in range(8):
            left, right = pixels[row * 9 + col], pixels[row * 9 + col + 1]
            bits = (bits << 1) | (left > right)
    return bits


def _widths(width: int) -> list[int]:
    """The standard widths below the image's own, then the image's width capped at the largest."""
    return [w for w in WIDTHS if w < min(width, WIDTHS[-1])] + [min(width, WIDTHS[-1])]


def _encode(image: Image.Image, fmt: str) -> bytes:
    out = BytesIO()
    image.save(out, fmt.upper(), **_SAVE[fmt])
    return out.getvalue()


def process_image(data: bytes, declared_type: str, *, max_bytes: int) -> ProcessedImage:
    if len(data) > max_bytes:
        raise ImageRejectedError("too_large")
    if declared_type not in _PIL_FORMAT or detect_type(data) != declared_type:
        raise ImageRejectedError("type_mismatch")
    with _decode(data, declared_type) as decoded:
        image = _to_srgb(decoded)
    variants: list[Variant] = []
    for fmt in FORMATS:
        for width in _widths(image.width):
            height = max(1, round(image.height * width / image.width))
            resized = (
                image
                if width == image.width
                else image.resize((width, height), Image.Resampling.LANCZOS)  # pyright: ignore[reportUnknownMemberType]
            )
            variants.append(Variant(fmt, width, height, _encode(resized, fmt)))
    return ProcessedImage(
        width=image.width,
        height=image.height,
        sha256=hashlib.sha256(data).digest(),
        dhash=_dhash(image),
        variants=variants,
    )
