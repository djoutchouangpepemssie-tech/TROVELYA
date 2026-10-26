"""Checking and re-encoding an uploaded image (section 13.2, ADR-0019). Pure and synchronous:
the worker runs it in a thread, one image at a time.

Nothing of the original file is served: its first bytes must match the declared type, it is
decoded within a pixel budget, oriented, converted to sRGB, then re-encoded from its pixels
only. EXIF (with GPS), XMP, IPTC, ICC profiles and any trailing bytes (a ZIP appended to a
JPEG) are left behind.
"""

import hashlib
from dataclasses import dataclass
from io import BytesIO
from typing import cast

import structlog
from PIL import Image, ImageCms, ImageOps

logger = structlog.get_logger(__name__)

# 50 Mpx: a 12 Mpx phone photo passes with room to spare; a decompression bomb does not.
MAX_PIXELS = 50_000_000
WIDTHS = (320, 640, 1080, 1600)  # section 11.5, never enlarged
# An avatar is cropped to its centred square (plan P2, T02c) and shown small.
AVATAR_WIDTHS = (320, 640)
FORMATS = ("avif", "webp")
# Work at no more than twice the largest variant: a JPEG is decoded at reduced scale, any other
# image reduced right after decoding (memory and time stay those of a 12 Mpx photo).
WORK_SIDE = 3200
MAX_SIDE = 16_383  # WebP's limit; a very tall variant is fitted inside it
_PIL_FORMAT = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP", "image/avif": "AVIF"}
_SAVE = {
    "avif": {"quality": 60, "speed": 8},
    "webp": {"quality": 80, "method": 4},
}
_SRGB = ImageCms.ImageCmsProfile(
    ImageCms.createProfile("sRGB")  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
)
_ORIENTATION_TAG = 0x0112
_QUARTER_TURNS = {5, 6, 7, 8}  # EXIF orientations that swap width and height
_HIGH_DEPTH = {"I", "I;16", "I;16B", "I;16L", "I;16N", "F"}


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
    """The type the first bytes announce, among the accepted ones. An AVIF still image says
    `avif` as its major brand, or `mif1` with `avif` among its compatible brands; an image
    sequence (`avis`) is not a photo and is refused."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[4:8] == b"ftyp":
        box_end = min(int.from_bytes(data[:4]), len(data), 64)
        compatible = {data[i : i + 4] for i in range(16, box_end - 3, 4)}
        if data[8:12] == b"avif" or (data[8:12] == b"mif1" and b"avif" in compatible):
            return "image/avif"
    return None


def hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def _decode(data: bytes, mime: str) -> tuple[Image.Image, tuple[int, int]]:
    """The decoded image (a JPEG at reduced scale when large) and the file's own dimensions,
    oriented as displayed."""
    image = Image.open(BytesIO(data), formats=[_PIL_FORMAT[mime]])
    width, height = image.size
    if width * height > MAX_PIXELS:
        raise ImageRejectedError("too_many_pixels")
    if image.format == "JPEG":  # DCT scaling; the side that is displayed as the width keeps
        turned = image.getexif().get(_ORIENTATION_TAG) in _QUARTER_TURNS  # WORK_SIDE pixels
        image.draft("RGB", (1, WORK_SIDE) if turned else (WORK_SIDE, 1))
    image.load()
    if image.getexif().get(_ORIENTATION_TAG) in _QUARTER_TURNS:  # PNG may keep it after pixels
        width, height = height, width
    return image, (width, height)


def _prepare(image: Image.Image) -> Image.Image:
    """Oriented, 8-bit RGB or RGBA, reduced to the working width, in sRGB, with no metadata."""
    image = ImageOps.exif_transpose(image)
    if image.mode in _HIGH_DEPTH:  # 16-bit greyscale: scale to 8 bits, do not clip
        image = image.convert("I").point(lambda v: v / 256).convert("L")  # pyright: ignore[reportUnknownMemberType, reportUnknownLambdaType, reportOperatorIssue]
    alpha = image.mode in {"RGBA", "LA", "PA", "RGBa", "La"} or "transparency" in image.info
    mode = "RGBA" if alpha else "RGB"
    icc = image.info.get("icc_profile")
    image = image.convert(mode)  # before reducing: palette and 1-bit images cannot be reduced
    factor = image.width // WORK_SIDE  # the width variants are cut from stays >= WORK_SIDE
    if factor > 1:
        image = image.reduce(factor)
    if icc:
        try:
            source = ImageCms.ImageCmsProfile(BytesIO(icc))
            image = ImageCms.profileToProfile(image, source, _SRGB, outputMode=mode) or image
        except (ImageCms.PyCMSError, OSError):
            pass  # an unusable profile: the pixels are taken as sRGB
    clean = Image.new(mode, image.size)
    clean.paste(image)
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


def _sizes(width: int, height: int, standard: tuple[int, ...]) -> list[tuple[int, int]]:
    """One size per standard width below the image's own, then the image's width capped at the
    largest; each fitted within MAX_SIDE in height and never enlarged."""
    widths = [w for w in standard if w < min(width, standard[-1])] + [min(width, standard[-1])]
    sizes: list[tuple[int, int]] = []
    for target in widths:
        scale = min(target / width, MAX_SIDE / height, 1.0)
        size = (max(1, round(width * scale)), max(1, round(height * scale)))
        if size not in sizes:
            sizes.append(size)
    return sizes


def _encode(image: Image.Image, fmt: str) -> bytes:
    out = BytesIO()
    image.save(out, fmt.upper(), **_SAVE[fmt])
    return out.getvalue()


def _square(image: Image.Image) -> Image.Image:
    side = min(image.size)
    left, top = (image.width - side) // 2, (image.height - side) // 2
    return image.crop((left, top, left + side, top + side))


def _variants(image: Image.Image, standard: tuple[int, ...]) -> list[Variant]:
    resized = [
        image if size == image.size else image.resize(size, Image.Resampling.LANCZOS)  # pyright: ignore[reportUnknownMemberType]
        for size in _sizes(image.width, image.height, standard)
    ]
    return [Variant(fmt, r.width, r.height, _encode(r, fmt)) for fmt in FORMATS for r in resized]


def process_image(
    data: bytes, declared_type: str, *, max_bytes: int, square: bool = False
) -> ProcessedImage:
    """`square`: an avatar, cropped to its centred square, in AVATAR_WIDTHS."""
    if len(data) > max_bytes:
        raise ImageRejectedError("too_large")
    if declared_type not in _PIL_FORMAT or detect_type(data) != declared_type:
        raise ImageRejectedError("type_mismatch")
    try:
        decoded, (width, height) = _decode(data, declared_type)
        with decoded:
            image = _prepare(decoded)
        if square:
            image = _square(image)
        variants = _variants(image, AVATAR_WIDTHS if square else WIDTHS)
        dhash = _dhash(image)
    except (ImageRejectedError, MemoryError):
        raise
    except Image.DecompressionBombError:
        raise ImageRejectedError("too_many_pixels") from None
    except Exception as exc:  # noqa: BLE001 — any decoder error on a hostile or broken file
        # Logged by type, so that a refusal caused by our own code shows up.
        logger.warning("media.image_unreadable", error=type(exc).__name__, mime=declared_type)
        raise ImageRejectedError("unreadable") from None
    return ProcessedImage(
        width=width,
        height=height,
        sha256=hashlib.sha256(data).digest(),
        dhash=dhash,
        variants=variants,
    )
