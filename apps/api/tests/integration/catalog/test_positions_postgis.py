"""The public offset measured by PostGIS on the WGS84 ellipsoid, as the database will measure
distances (plan P2, G5): always 200 to 500 m from the real position."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from trovelya.modules.catalog.service.positions import public_offset

# Lisbon, Paris, Lyon, Helsinki and Rovaniemi (north of the Arctic circle).
PLACES = [(38.72, -9.14), (48.8566, 2.3522), (45.7578, 4.8320), (60.17, 24.94), (66.5, 25.73)]


async def test_public_offset_between_200_and_500_m(engine: AsyncEngine) -> None:
    real: list[tuple[float, float]] = []
    public: list[tuple[float, float]] = []
    for draw in range(10_000):
        place = PLACES[draw % len(PLACES)]
        real.append(place)
        public.append(public_offset(*place))
    async with engine.connect() as conn:
        shortest, longest = (
            await conn.execute(
                text(
                    "SELECT min(d), max(d) FROM ("
                    " SELECT ST_Distance(ST_MakePoint(rx, ry)::geography,"
                    " ST_MakePoint(px, py)::geography) AS d"
                    " FROM unnest(CAST(:rx AS float8[]), CAST(:ry AS float8[]),"
                    " CAST(:px AS float8[]), CAST(:py AS float8[])) AS t(rx, ry, px, py)) s"
                ),
                {
                    "rx": [lon for _, lon in real],
                    "ry": [lat for lat, _ in real],
                    "px": [lon for _, lon in public],
                    "py": [lat for lat, _ in public],
                },
            )
        ).one()
    assert shortest >= 200 and longest <= 500
    assert shortest < 230 and longest > 470  # the whole band is used
