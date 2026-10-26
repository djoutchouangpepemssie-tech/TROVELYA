"""Public position and H3 cells (P2-T03b1, section 8.11, plan P2 E13): drawn by the system's
cryptographic generator, in every direction, never the real position."""

import math
import random

import h3  # pyright: ignore[reportMissingTypeStubs]
import pytest

from trovelya.modules.catalog.service import positions
from trovelya.modules.catalog.service.positions import h3_cells, public_offset

LYON = (45.7578, 4.8320)


def test_offset_drawn_by_the_system_generator() -> None:
    assert isinstance(positions.SYSTEM_RANDOM, random.SystemRandom)
    assert public_offset.__defaults__ == (positions.SYSTEM_RANDOM,)


def test_offset_goes_every_way() -> None:
    rng = random.Random(7)  # noqa: S311  (seeded: the test repeats)
    quadrants: set[tuple[bool, bool]] = set()
    for _ in range(200):
        latitude, longitude = public_offset(*LYON, rng)
        quadrants.add((latitude > LYON[0], longitude > LYON[1]))
        assert (latitude, longitude) != LYON
    assert len(quadrants) == 4


class Fixed(random.Random):
    """Draws the distance, then the bearing, given in advance."""

    def __init__(self, distance: float, bearing: float) -> None:
        super().__init__()
        self.draws = [distance, bearing]

    def uniform(self, a: float, b: float) -> float:
        return self.draws.pop(0)


def test_offset_keeps_longitude_in_range() -> None:
    latitude, longitude = public_offset(0.0, 179.9999, Fixed(500, math.pi / 2))  # due east
    assert -180.0 <= longitude < -179.99 and abs(latitude) < 1e-9


def test_offset_refused_near_the_poles() -> None:
    with pytest.raises(ValueError, match="85 degrees"):
        public_offset(86.0, 25.0)


def test_h3_cells_of_the_real_position() -> None:
    r7, r9 = h3_cells(*LYON)
    assert h3.int_to_str(r7) == h3.latlng_to_cell(*LYON, 7)  # pyright: ignore[reportUnknownMemberType]
    assert h3.int_to_str(r9) == h3.latlng_to_cell(*LYON, 9)  # pyright: ignore[reportUnknownMemberType]
    assert 0 < r9 < 2**63 and 0 < r7 < 2**63  # fits a BIGINT
    assert not math.isclose(r7, r9)
