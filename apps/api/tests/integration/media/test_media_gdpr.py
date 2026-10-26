"""GDPR export of a member's media (P2-T02a1): described, without storage keys nor hashes."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.integration.identity.test_profile import make_account
from trovelya.core.gdpr import registered_exporters
from trovelya.shared.ids import new_id


async def test_media_exported_without_keys_or_hashes(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    owner = await make_account(sessionmaker, completed=True)
    other = await make_account(sessionmaker, completed=True)
    async with sessionmaker() as db:
        for user_id in (owner.id, other.id):
            await db.execute(
                text(
                    "INSERT INTO media (id, owner_id, kind, purpose, storage_key, mime_type,"
                    " bytes, status) VALUES (:id, :owner, 'image', 'listing', :key,"
                    " 'image/jpeg', 1234, 'uploading')"
                ),
                {"id": new_id(), "owner": user_id, "key": new_id().hex},
            )
        await db.commit()
        export = await registered_exporters()["media"](db, owner.id)
    [media] = export["media"]
    assert (media["purpose"], media["mime_type"], media["bytes"]) == ("listing", "image/jpeg", 1234)
    assert not {"storage_key", "sha256", "perceptual_hash", "owner_id"} & set(media)
