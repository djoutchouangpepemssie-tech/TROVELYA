"""Image checks and re-encoding (P2-T02b1, ADR-0019): a file is decoded only when its first
bytes match the declared type; what comes out is pixels only, in AVIF and WebP."""

import hashlib
import struct
import zlib
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from PIL import Image, ImageDraw

from trovelya.modules.media.service import images
from trovelya.modules.media.service.images import (
    MAX_PIXELS,
    ImageRejectedError,
    detect_type,
    hamming,
    process_image,
)

MAX_BYTES = 15 * 1024 * 1024
FIXTURES = Path(__file__).parents[2] / "fixtures" / "media"
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


def _phone_photo(orientation: int = 1, width: int = 800) -> bytes:
    """A JPEG as a phone writes it: EXIF with GPS position, orientation, XMP and an ICC profile."""
    image = _picture(width, width * 3 // 4)
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


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def _png_header_only(width: int, height: int) -> bytes:
    """A PNG claiming huge dimensions: the header alone must be enough to refuse it."""
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", zlib.compress(b"\0" * 64))


def _swapped_primaries_profile() -> bytes:
    """A minimal ICC v2 RGB profile whose red and green primaries are sRGB's swapped: a pure
    red pixel tagged with it is, in sRGB, green."""

    def s15(value: float) -> bytes:
        return struct.pack(">i", round(value * 65536))

    def xyz(x: float, y: float, z: float) -> bytes:
        return b"XYZ \0\0\0\0" + s15(x) + s15(y) + s15(z)

    gamma = b"curv\0\0\0\0" + struct.pack(">I", 1) + struct.pack(">H", 0x0233) + b"\0\0"
    red, green, blue = (0.4361, 0.2225, 0.0139), (0.3851, 0.7169, 0.0971), (0.1431, 0.0606, 0.7141)
    tags = [
        (b"wtpt", xyz(0.9642, 1.0, 0.8249)),
        (b"rXYZ", xyz(*green)),
        (b"gXYZ", xyz(*red)),
        (b"bXYZ", xyz(*blue)),
        (b"rTRC", gamma),
        (b"gTRC", gamma),
        (b"bTRC", gamma),
    ]
    offset = 128 + 4 + 12 * len(tags)
    table, data = b"", b""
    for signature, body in tags:
        table += signature + struct.pack(">II", offset + len(data), len(body))
        data += body
    header = (
        struct.pack(">I", offset + len(data))
        + b"\0\0\0\0"
        + bytes([2, 0x10, 0, 0])
        + b"mntrRGB XYZ "
        + b"\0" * 12
        + b"acsp"
        + b"\0" * 24
        + b"\0\0\0\0"
        + xyz(0.9642, 1.0, 0.8249)[8:]
        + b"\0" * 48
    )
    assert len(header) == 128
    return header + struct.pack(">I", len(tags)) + table + data


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
    result = process_image(_phone_photo(width=2000), "image/jpeg", max_bytes=MAX_BYTES)
    assert len(result.variants) == 8  # 320, 640, 1080 and 1600, in AVIF and WebP
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


@pytest.mark.parametrize(
    "fixture",
    ["fuzzed-avif-missing-item.avif", "fuzzed-webp-bad-exif.webp"],
)
def test_broken_files_found_by_fuzzing_are_refused(fixture: str) -> None:
    """Decoder errors of any kind (here RuntimeError and SyntaxError) end in a refusal."""
    data = (FIXTURES / fixture).read_bytes()
    with pytest.raises(ImageRejectedError) as rejected:
        process_image(data, detect_type(data) or "", max_bytes=MAX_BYTES)
    assert rejected.value.reason == "unreadable"


def test_corrupt_exif_in_png_is_refused() -> None:
    """PNG reads its eXIf chunk only when asked (orientation): still a refusal, not a crash."""
    png = _encode(_picture(64, 48), "PNG")
    broken = png[:-12] + _chunk(b"eXIf", b"MM\0o\0\0\0\x08" + b"\xff" * 20) + png[-12:]
    with pytest.raises(ImageRejectedError) as rejected:
        process_image(broken, "image/png", max_bytes=MAX_BYTES)
    assert rejected.value.reason == "unreadable"


@pytest.mark.parametrize(("width", "height"), [(1, 20_000), (1080, 20_000), (1600, 17_000)])
def test_very_tall_image_fits_webp_limits(width: int, height: int) -> None:
    """A long screenshot: every variant fits WebP's 16 383 px, none is enlarged."""
    image = Image.new("RGB", (width, height), (10, 120, 200))
    result = process_image(_encode(image, "PNG"), "image/png", max_bytes=MAX_BYTES)
    assert (result.width, result.height) == (width, height)
    assert result.variants
    for variant in result.variants:
        assert variant.height <= 16_383 and variant.width <= width


def test_sixteen_bit_greyscale_keeps_its_tones() -> None:
    image = Image.new("I;16", (5, 1))
    for x, value in enumerate((2 * 257, 66 * 257, 130 * 257, 194 * 257, 253 * 257)):
        image.putpixel((x, 0), value)
    result = process_image(_encode(image, "PNG"), "image/png", max_bytes=MAX_BYTES)
    webp = next(v for v in result.variants if v.format == "webp")
    with Image.open(BytesIO(webp.data)) as decoded:
        greys = [decoded.convert("L").getpixel((x, 0)) for x in range(5)]
    assert greys == sorted(greys) and greys[0] < 20 and greys[-1] > 235  # type: ignore[operator]


def test_colour_profile_converted_to_srgb() -> None:
    """A red pixel in a profile whose red is sRGB's green comes out green."""
    image = Image.new("RGB", (64, 48), (255, 0, 0))
    data = _encode(image, "PNG", icc_profile=_swapped_primaries_profile())
    result = process_image(data, "image/png", max_bytes=MAX_BYTES)
    webp = next(v for v in result.variants if v.format == "webp")
    with Image.open(BytesIO(webp.data)) as decoded:
        red, green, _ = decoded.convert("RGB").getpixel((32, 24))  # type: ignore[misc]
    assert green > 200 and red < 60


def test_palette_transparency_kept() -> None:
    image = Image.new("P", (64, 48), 0)
    image.putpalette([255, 0, 0, 0, 0, 255])
    result = process_image(_encode(image, "PNG", transparency=0), "image/png", max_bytes=MAX_BYTES)
    webp = next(v for v in result.variants if v.format == "webp")
    with Image.open(BytesIO(webp.data)) as decoded:
        assert decoded.mode == "RGBA" and decoded.getpixel((0, 0))[3] == 0  # type: ignore[index]


def test_dhash_reference_values() -> None:
    """A bit is 1 when a cell is brighter than its right neighbour: a ramp getting brighter to
    the right gives all 0s, its mirror all 1s. An image oriented by EXIF hashes like the same
    image already turned."""
    ramp = Image.linear_gradient("L").rotate(90).resize((90, 80))  # pyright: ignore[reportUnknownMemberType]
    one = process_image(_encode(ramp.convert("RGB"), "PNG"), "image/png", max_bytes=MAX_BYTES)
    mirrored = ramp.transpose(Image.Transpose.FLIP_LEFT_RIGHT).convert("RGB")
    other = process_image(_encode(mirrored, "PNG"), "image/png", max_bytes=MAX_BYTES)
    assert (one.dhash, other.dhash) == (0, 2**64 - 1)
    scene = _picture(400, 300)
    exif = Image.Exif()
    exif[ORIENTATION_TAG] = 6
    tagged = process_image(_encode(scene, "PNG", exif=exif), "image/png", max_bytes=MAX_BYTES)
    turned = scene.transpose(Image.Transpose.ROTATE_270)
    already = process_image(_encode(turned, "PNG"), "image/png", max_bytes=MAX_BYTES)
    assert tagged.dhash == already.dhash
    assert (tagged.width, tagged.height) == (300, 400)


def test_sha256_is_of_the_original_bytes() -> None:
    data = _phone_photo()
    result = process_image(data, "image/jpeg", max_bytes=MAX_BYTES)
    assert result.sha256 == hashlib.sha256(data).digest()


def test_limits_are_inclusive() -> None:
    data = _encode(_picture(64, 48), "PNG")
    assert process_image(data, "image/png", max_bytes=len(data)).width == 64
    with pytest.raises(ImageRejectedError) as rejected:  # exactly 50 Mpx: decoded, not refused
        process_image(_png_header_only(10_000, 5_000), "image/png", max_bytes=MAX_BYTES)
    assert rejected.value.reason == "unreadable"


def test_avif_brands() -> None:
    """A still AVIF may announce `mif1` with `avif` compatible; an image sequence (`avis`) is
    not a photo."""
    avif = _encode(_picture(64, 48), "AVIF")
    assert int.from_bytes(avif[:4]) >= 24
    mif1 = avif[:8] + b"mif1" + avif[12:16] + b"avif" + avif[20:]
    assert detect_type(mif1) == "image/avif"
    assert detect_type(avif[:8] + b"avis" + avif[12:]) is None


@pytest.mark.parametrize("mode", ["P", "1", "I;16"])
def test_large_palette_bilevel_and_16_bit_images_are_processed(mode: str) -> None:
    """A floor plan or a scan wider than the working size: reduced like any other image."""
    image = Image.new(mode, (6500, 6500), 1)
    result = process_image(_encode(image, "PNG"), "image/png", max_bytes=MAX_BYTES)
    assert (result.width, result.height) == (6500, 6500)
    assert max(v.width for v in result.variants) == 1600


class _Recorder:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    def warning(self, event: str, **fields: Any) -> None:
        self.events.append((event, fields))


def test_unreadable_file_is_logged_by_error_type(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = _Recorder()
    monkeypatch.setattr(images, "logger", recorder)
    data = _encode(_picture(), "JPEG")
    with pytest.raises(ImageRejectedError):
        process_image(data[: len(data) // 2], "image/jpeg", max_bytes=MAX_BYTES)
    assert recorder.events == [
        ("media.image_unreadable", {"error": "OSError", "mime": "image/jpeg"})
    ]
