"""Load the category tree and the common brands (P2-T01b).

Run after the migrations, at every deployment (Railway pre-deploy command) and locally:
    uv run python -m trovelya.scripts.seed_catalog

Idempotent: the files of `modules/catalog/seed` are the source of truth. An invalid file
stops the deployment with the reason and changes nothing.
"""

import asyncio
import sys

from trovelya.core.config import get_settings
from trovelya.core.db import make_engine, make_sessionmaker
from trovelya.modules.catalog.service.seed import (
    SeedError,
    load_seed,
    parse_brands,
    read_seed_file,
)
from trovelya.modules.catalog.service.seed_writer import apply_brands, apply_seed


async def _run() -> int:
    try:
        seed = load_seed()
        brands = parse_brands(read_seed_file("brands.yaml"))
    except SeedError as exc:
        sys.stderr.write(f"Graine refusée : {exc}\n")
        return 1
    engine = make_engine(get_settings().database_url)
    try:
        async with make_sessionmaker(engine)() as db:
            try:
                await apply_seed(db, seed)
                await apply_brands(db, brands)
                await db.commit()
            except SeedError as exc:
                await db.rollback()
                sys.stderr.write(f"Graine refusée : {exc}\n")
                return 1
    finally:
        await engine.dispose()
    sys.stdout.write(
        f"Catalogue chargé : {len(seed.categories)} catégories, {len(seed.attributes)}"
        f" attributs, {len(brands)} marques courantes.\n"
    )
    return 0


def main() -> None:
    sys.exit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
