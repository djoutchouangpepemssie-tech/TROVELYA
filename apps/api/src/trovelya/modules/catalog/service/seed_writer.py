"""Writing the validated seed into the catalog tables (P2-T01b).

Idempotent: a category is found by its key, never by its name or place, so renaming or
moving one keeps its id and its listings. A key missing from the file is deactivated, never
deleted. The caller's transaction holds everything; the caller commits.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from trovelya.modules.catalog import repository
from trovelya.modules.catalog.service.seed import CatalogSeed, SeedError


async def apply_seed(db: AsyncSession, seed: CatalogSeed) -> None:
    """Write the seed in the caller's transaction (the caller commits)."""
    await repository.lock_seed(db)
    existing_types = await repository.attribute_types(db)
    for attribute in seed.attributes:
        old_type = existing_types.get(attribute.key)
        if old_type is not None and old_type != attribute.data_type:
            raise SeedError(
                f"attribut {attribute.key} : son type ne peut pas changer"
                f" ({old_type} → {attribute.data_type}), créer une nouvelle clé"
            )
    attribute_ids = {
        attribute.key: await repository.upsert_attribute(
            db,
            key=attribute.key,
            names=attribute.names,
            data_type=attribute.data_type,
            enum_values=(
                [(v.key, v.names) for v in attribute.enum_values] if attribute.enum_values else None
            ),
            unit=attribute.unit,
            constraints=attribute.constraints,
        )
        for attribute in seed.attributes
    }
    # Paths and the tree are checked at commit: moves and swaps may cross paths meanwhile; a
    # new path moves the subtree with it (database trigger).
    category_ids: dict[str, UUID] = {}
    for category in seed.categories:
        category_ids[category.key] = await repository.upsert_category(
            db,
            parent_id=category_ids[category.parent_key] if category.parent_key else None,
            key=category.key,
            path=category.path,
            names=category.names,
            icon=category.icon,
            position=category.position,
            is_active=category.is_active,
            is_restricted=category.is_restricted,
            vertical=category.vertical,
            transaction_model=category.transaction_model,
            shipping_allowed=category.shipping_allowed,
            max_photos=category.max_photos,
            allowed_conditions=(
                list(category.allowed_conditions) if category.allowed_conditions else None
            ),
            brand_policy=category.brand_policy,
        )
    # Categories gone from the file leave the tree inactive where they are.
    await repository.deactivate_categories_except(db, list(category_ids))
    await repository.sync_category_attributes(
        db,
        list(category_ids.values()),
        [
            {
                "category_id": category_ids[category.key],
                "attribute_id": attribute_ids[attribute.key],
                "is_required": attribute.is_required,
                "is_filterable": attribute.is_filterable,
                "position": position,
            }
            for category in seed.categories
            for position, attribute in enumerate(category.attributes)
        ],
    )
