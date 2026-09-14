from datetime import UTC, datetime

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.models import AppSettingKey, CommunityLinksLocation


@pytest.mark.asyncio
async def test_community_links_setting_defaults_when_row_is_missing(
    db: AsyncSession,
) -> None:
    setting = await crud.get_app_setting(session=db, key=AppSettingKey.COMMUNITY_LINKS)
    assert setting is not None
    await db.delete(setting)
    await db.commit()

    value = await crud.get_community_links_setting(session=db)
    assert value.location == CommunityLinksLocation.NAVBAR


@pytest.mark.asyncio
async def test_community_links_update_upserts_typed_jsonb_value(
    db: AsyncSession,
) -> None:
    setting = await crud.get_app_setting(session=db, key=AppSettingKey.COMMUNITY_LINKS)
    assert setting is not None
    await db.delete(setting)
    await db.commit()

    value = await crud.update_community_links_setting(
        session=db, location=CommunityLinksLocation.FOOTER
    )
    assert value.location == CommunityLinksLocation.FOOTER

    stored = await crud.get_app_setting(session=db, key=AppSettingKey.COMMUNITY_LINKS)
    assert stored is not None
    assert stored.value == {"location": "footer"}


@pytest.mark.asyncio
async def test_qq_secret_rotation_and_deletion_only_touch_secret_row(
    db: AsyncSession,
) -> None:
    created = await crud.create_qq_binding_secret(
        session=db, encrypted_secret="encrypted-first"
    )
    before_rotation = datetime.now(UTC)
    rotated = await crud.rotate_qq_binding_secret(
        session=db, encrypted_secret="encrypted-second"
    )
    assert rotated.encrypted_secret == "encrypted-second"
    assert rotated.created_at == created.created_at
    assert rotated.updated_at >= before_rotation

    with pytest.raises(crud.QQBindingSecretAlreadyConfiguredError):
        await crud.create_qq_binding_secret(
            session=db, encrypted_secret="encrypted-third"
        )

    await crud.delete_qq_binding_secret(session=db)
    assert await crud.get_qq_binding_secret(session=db) is None
    assert (
        await crud.get_app_setting(session=db, key=AppSettingKey.COMMUNITY_LINKS)
        is not None
    )
