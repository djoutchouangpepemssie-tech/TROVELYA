"""Image checks and re-encoding (P2-T02b1, ADR-0019): a file is decoded only when its first
bytes match the declared type; what comes out is pixels only, in AVIF and WebP."""

import struct
import zlib
from io import BytesIO

import pytest
from PIL import Image, ImageDraw

from trovelya.modules.media.service.images import (
    MAX_PIXELS,
    ImageRejectedError,
    detect_type,
    hamming,
    process_image,
)

MAX_BYTES = 15 * 1024 * 1024
GPS_TAG = 0x8825
ORIENTATION_TAG = 0x0112


def _picture(width: int = 800, height: int = 600) -> Image.Image:
    """A smooth scene with shapes, closer to a photo than flat noise."""
    gradient = Image.linear_gradient("L").resize((width, height))  # pyright: ignore[reportUnknownMemberType]
    image = gradient.convert("RGB")
    draw = ImageDraw.Draw(image)
    draw.ellipse((width // 5, height // 5, width // 2, height // 2), fill=(200, 40, 40))
    draw.rectangle((width // 2, height // 2, width * 9 // 10, height * 9 // 10), fill=(30, 90, 200))
    return image


def _encode(image: Image.Image, fmt: str, **params: object) -> bytes:
    out = BytesIO()
    image.save(out, fmt, **params)
    return out.getvalue()


def _phone_photo(orientation: int = 1) -> bytes:
    """A JPEG as a phone writes it: EXIF with GPS position, orientation, XMP and an ICC profile."""
    image = _picture()
    exif = Image.Exif()
    exif[0x010F] = "PhoneMaker"
    exif[ORIENTATION_TAG] = orientation
    exif[GPS_TAG] = {1: "N", 2: (48.0, 51.0, 24.0), 3: "E", 4: (2.0, 21.0, 7.0)}
    xmp = b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF/>GPSLatitude</x:xmpmeta>'
    return _encode(image, "JPEG", exif=exif, xmp=xmp, icc_profile=_srgb_profile(), quality=90)


def _srgb_profile() -> bytes:
    from PIL import ImageCms

    profile = ImageCms.createProfile("sRGB")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    return ImageCms.ImageCmsProfile(profile).tobytes()  # pyright: ignore[reportUnknownArgumentType]


def _png_header_only(width: int, height: int) -> bytes:
    """A PNG claiming huge dimensions: the header alone must be enough to refuse it."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(b"\0" * 64))


@pytest.mark.parametrize(
    ("fmt", "mime"),
    [("JPEG", "image/jpeg"), ("PNG", "image/png"), ("WEBP", "image/webp"), ("AVIF", "image/avif")],
)
def test_signature_matches_each_accepted_type(fmt: str, mime: str) -> None:
    assert detect_type(_encode(_picture(64, 48), fmt)) == mime
    result = process_image(_encode(_picture(64, 48), fmt), mime, max_bytes=MAX_BYTES)
    assert (result.width, result.height) == (64, 48)


@pytest.mark.parametrize(
    ("data", "declared"),
    [
        (b"#!/bin/sh\nrm -rf /\n" + b"\0" * 64, "image/jpeg"),  # a script renamed .jpg
        (_encode(_picture(64, 48), "PNG"), "image/jpeg"),  # a real PNG declared as JPEG
        (b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>', "image/png"),
        (b"GIF89a" + b"\0" * 64, "image/webp"),
    ],
    ids=["script", "png-as-jpeg", "svg", "gif"],
)
def test_rejects_spoofed_type(data: bytes, declared: str) -> None:
    with pytest.raises(ImageRejectedError) as rejected:
        process_image(data, declared, max_bytes=MAX_BYTES)
    assert rejected.value.reason == "type_mismatch"


def test_rejects_truncated_jpeg() -> None:
    data = _encode(_picture(), "JPEG")
    with pytest.raises(ImageRejectedError) as rejected:
        process_image(data[: len(data) // 2], "image/jpeg", max_bytes=MAX_BYTES)
    assert rejected.value.reason == "unreadable"


@pytest.mark.parametrize("side", [8000, 20_000])
def test_rejects_decompression_bomb(side: int) -> None:
    """Above 50 Mpx (8000 x 8000 = 64 Mpx), refused from the header, before any decoding."""
    assert side * side > MAX_PIXELS
    with pytest.raises(ImageRejectedError) as rejected:
        process_image(_png_header_only(side, side), "image/png", max_bytes=MAX_BYTES)
    assert rejected.value.reason == "too_many_pixels"


def test_rejects_oversized_real_bytes() -> None:
    data = _encode(_picture(64, 48), "PNG")
    with pytest.raises(ImageRejectedError) as rejected:
        process_image(data, "image/png", max_bytes=len(data) - 1)
    assert rejected.value.reason == "too_large"


def test_polyglot_reencoded_without_trailing_bytes() -> None:
    """JPEG followed by a ZIP archive: the image passes, the archive is not carried over."""
    polyglot = _encode(_picture(), "JPEG") + b"PK\x03\x04" + b"payload" * 100 + b"PK\x05\x06"
    result = process_image(polyglot, "image/jpeg", max_bytes=MAX_BYTES)
    assert all(b"PK\x03\x04" not in v.data and b"payload" not in v.data for v in result.variants)


def test_variants_have_no_metadata() -> None:
    result = process_image(_phone_photo(), "image/jpeg", max_bytes=MAX_BYTES)
    assert len(result.variants) == 6  # 800 px wide: 320, 640 and 800, in AVIF and WebP
    for variant in result.variants:
        for marker in (b"Exif", b"PhoneMaker", b"GPSLatitude", b"xmpmeta", b"ICC_PROFILE"):
            assert marker not in variant.data, (variant.format, variant.width, marker)
        with Image.open(BytesIO(variant.data)) as decoded:
            assert not decoded.getexif()
            assert not {"exif", "xmp", "XML:com.adobe.xmp", "icc_profile"} & set(decoded.info)


def test_orientation_applied() -> None:
    """Orientation 6 (rotate 90° clockwise to display): the left of the sensor becomes the top."""
    image = Image.new("RGB", (400, 200), (0, 0, 255))
    image.paste((255, 0, 0), (0, 0, 200, 200))  # left half red
    exif = Image.Exif()
    exif[ORIENTATION_TAG] = 6
    result = process_image(_encode(image, "JPEG", exif=exif), "image/jpeg", max_bytes=MAX_BYTES)
    assert (result.width, result.height) == (200, 400)
    webp = next(v for v in result.variants if v.format == "webp" and v.width == 200)
    with Image.open(BytesIO(webp.data)) as decoded:
        red, _, blue = decoded.convert("RGB").getpixel((100, 20))  # type: ignore[misc]
        assert red > 200 and blue < 60


@pytest.mark.parametrize(
    ("width", "height", "expected"),
    [
        (4000, 3000, [(320, 240), (640, 480), (1080, 810), (1600, 1200)]),
        (500, 375, [(320, 240), (500, 375)]),  # no enlargement
        (200, 100, [(200, 100)]),
        (1600, 900, [(320, 180), (640, 360), (1080, 608), (1600, 900)]),
    ],
)
def test_variant_sizes_and_formats(
    width: int, height: int, expected: list[tuple[int, int]]
) -> None:
    result = process_image(
        _encode(_picture(width, height), "PNG"), "image/png", max_bytes=MAX_BYTES
    )
    for fmt, signature in (("avif", "image/avif"), ("webp", "image/webp")):
        variants = [v for v in result.variants if v.format == fmt]
        assert [(v.width, v.height) for v in variants] == expected
        for variant in variants:
            assert detect_type(variant.data) == signature
            with Image.open(BytesIO(variant.data)) as decoded:
                assert decoded.size == (variant.width, variant.height)


def test_sha256_and_dhash_stable() -> None:
    data = _encode(_picture(), "PNG")
    first = process_image(data, "image/png", max_bytes=MAX_BYTES)
    again = process_image(data, "image/png", max_bytes=MAX_BYTES)
    assert (first.sha256, first.dhash) == (again.sha256, again.dhash)
    assert len(first.sha256) == 32 and 0 <= first.dhash < 2**64
    cropped = _picture().crop((20, 15, 780, 585))  # 5 % trimmed
    other = process_image(_encode(cropped, "PNG"), "image/png", max_bytes=MAX_BYTES)
    assert other.sha256 != first.sha256
    assert hamming(first.dhash, other.dhash) <= 6
    different = process_image(
        _encode(_picture().rotate(180), "PNG"), "image/png", max_bytes=MAX_BYTES
    )
    assert hamming(first.dhash, different.dhash) > 6


def test_transparency_kept() -> None:
    image = Image.new("RGBA", (64, 48), (255, 0, 0, 0))
    result = process_image(_encode(image, "PNG"), "image/png", max_bytes=MAX_BYTES)
    webp = next(v for v in result.variants if v.format == "webp")
    with Image.open(BytesIO(webp.data)) as decoded:
        assert decoded.mode == "RGBA"
