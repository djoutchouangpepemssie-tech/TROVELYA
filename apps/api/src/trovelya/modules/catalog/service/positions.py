"""Where a listing is (section 8.11, plan P2 E13 and E14).

The real position is never shown. The public one is the real one moved 200 to 500 m in a random
direction, drawn once per position source; the distance shown to a visitor is computed on the
public position, then rounded (`round_distance`). H3 cells are computed on the real position
and never leave the server.
"""

import math
import secrets
from random import Random
from typing import Any

import h3  # pyright: ignore[reportMissingTypeStubs]

PUBLIC_OFFSET_MIN_M = 200
PUBLIC_OFFSET_MAX_M = 500
# WGS84, the ellipsoid of the stored GEOGRAPHY(Point, 4326).
_A = 6378137.0
_E2 = 6.69437999014e-3

_SYSTEM_RANDOM = secrets.SystemRandom()
_H3: Any = h3  # untyped library


def public_offset(
    latitude: float, longitude: float, rng: Random = _SYSTEM_RANDOM
) -> tuple[float, float]:
    """The real position moved 200 to 500 m (uniform) in a uniform direction. On the WGS84
    ellipsoid's local radii, exact to well under a meter at these distances."""
    distance = rng.uniform(PUBLIC_OFFSET_MIN_M, PUBLIC_OFFSET_MAX_M)
    bearing = rng.uniform(0.0, 2.0 * math.pi)
    phi = math.radians(latitude)
    sin2 = math.sin(phi) ** 2
    meridian = _A * (1 - _E2) / (1 - _E2 * sin2) ** 1.5  # radius along a meridian
    normal = _A / math.sqrt(1 - _E2 * sin2)  # radius along the parallel's normal
    north, east = distance * math.cos(bearing), distance * math.sin(bearing)
    new_latitude = latitude + math.degrees(north / meridian)
    new_longitude = longitude + math.degrees(east / (normal * math.cos(phi)))
    return new_latitude, (new_longitude + 180.0) % 360.0 - 180.0


def h3_cells(latitude: float, longitude: float) -> tuple[int, int]:
    """Resolutions 7 (about 1.4 km) and 9 (about 170 m) of the real position, as BIGINT."""
    return (
        int(_H3.str_to_int(_H3.latlng_to_cell(latitude, longitude, 7))),
        int(_H3.str_to_int(_H3.latlng_to_cell(latitude, longitude, 9))),
    )


def _nearest(value: float, step: int) -> int:
    """`value` rounded to the nearest multiple of `step`, halves up."""
    return math.floor(value / step + 0.5) * step


def round_distance(meters: float) -> str:
    """Section 8.11: under 1 km "moins de 1 km"; under 10 km to the km; from 10 km to 5 km;
    from 100 km to 10 km. Each step rounds to the nearest value, halves up."""
    if meters < 0:
        raise ValueError("a distance is never negative")
    if meters < 1000:
        return "moins de 1 km"
    km = meters / 1000
    if km < 10:
        shown = _nearest(km, 1)
    elif km < 100:
        shown = _nearest(km, 5)
    else:
        shown = _nearest(km, 10)
    return f"{shown} km"
