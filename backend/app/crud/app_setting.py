from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import (
    AppSetting,
    AppSettingKey,
    CommunityLinksLocation,
    CommunityLinksSettingValue,
    GlobalApiRecordsSyncSettingValue,
    QQBindingSecretSettingValue,
    QQBindingSecretStored,
)


class QQBindingSecretAlreadyConfiguredError(ValueError):
    pass


async def get_app_setting(
    *, session: AsyncSession, key: AppSettingKey
) -> AppSetting | None:
    return await session.get(AppSetting, key.value)


async def get_community_links_setting(
    *, session: AsyncSession
) -> CommunityLinksSettingValue:
    setting = await get_app_setting(session=session, key=AppSettingKey.COMMUNITY_LINKS)
    if setting is None:
        return CommunityLinksSettingValue()
    return CommunityLinksSettingValue.model_validate(setting.value)


async def update_community_links_setting(
    *, session: AsyncSession, location: CommunityLinksLocation
) -> CommunityLinksSettingValue:
    value = CommunityLinksSettingValue(location=location)
    setting = await get_app_setting(session=session, key=AppSettingKey.COMMUNITY_LINKS)
    if setting is None:
        setting = AppSetting(
            key=AppSettingKey.COMMUNITY_LINKS.value,
            value=value.model_dump(mode="json"),
        )
    else:
        setting.value = value.model_dump(mode="json")
        setting.updated_at = datetime.now(UTC)
    session.add(setting)
    await session.commit()
    return value


async def get_globalapi_records_sync_setting(
    *, session: AsyncSession
) -> GlobalApiRecordsSyncSettingValue:
    setting = await get_app_setting(
        session=session, key=AppSettingKey.GLOBALAPI_RECORDS_SYNC
    )
    if setting is None:
        return GlobalApiRecordsSyncSettingValue()
    return GlobalApiRecordsSyncSettingValue.model_validate(setting.value)


async def update_globalapi_records_sync_setting(
    *, session: AsyncSession, enabled: bool
) -> GlobalApiRecordsSyncSettingValue:
    value = GlobalApiRecordsSyncSettingValue(enabled=enabled)
    setting = await get_app_setting(
        session=session, key=AppSettingKey.GLOBALAPI_RECORDS_SYNC
    )
    if setting is None:
        setting = AppSetting(
            key=AppSettingKey.GLOBALAPI_RECORDS_SYNC.value,
            value=value.model_dump(mode="json"),
        )
    else:
        setting.value = value.model_dump(mode="json")
        setting.updated_at = datetime.now(UTC)
    session.add(setting)
    await session.commit()
    return value


async def get_qq_binding_secret(
    *, session: AsyncSession
) -> QQBindingSecretStored | None:
    setting = await get_app_setting(
        session=session, key=AppSettingKey.QQ_BINDING_SECRET
    )
    if setting is None:
        return None
    value = QQBindingSecretSettingValue.model_validate(setting.value)
    return QQBindingSecretStored(
        encrypted_secret=value.encrypted_secret,
        created_at=setting.created_at,
        updated_at=setting.updated_at,
    )


async def create_qq_binding_secret(
    *, session: AsyncSession, encrypted_secret: str
) -> QQBindingSecretStored:
    value = QQBindingSecretSettingValue(encrypted_secret=encrypted_secret)
    setting = AppSetting(
        key=AppSettingKey.QQ_BINDING_SECRET.value,
        value=value.model_dump(mode="json"),
    )
    session.add(setting)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise QQBindingSecretAlreadyConfiguredError(
            "QQ binding secret is already configured"
        ) from exc
    await session.refresh(setting)
    return QQBindingSecretStored(
        encrypted_secret=value.encrypted_secret,
        created_at=setting.created_at,
        updated_at=setting.updated_at,
    )


async def rotate_qq_binding_secret(
    *,
    session: AsyncSession,
    encrypted_secret: str,
) -> QQBindingSecretStored:
    setting = await get_app_setting(
        session=session, key=AppSettingKey.QQ_BINDING_SECRET
    )
    if setting is None:
        raise ValueError("QQ binding secret is not configured")
    value = QQBindingSecretSettingValue(encrypted_secret=encrypted_secret)
    setting.value = value.model_dump(mode="json")
    setting.updated_at = datetime.now(UTC)
    session.add(setting)
    await session.commit()
    await session.refresh(setting)
    return QQBindingSecretStored(
        encrypted_secret=value.encrypted_secret,
        created_at=setting.created_at,
        updated_at=setting.updated_at,
    )


async def delete_qq_binding_secret(*, session: AsyncSession) -> None:
    setting = await get_app_setting(
        session=session, key=AppSettingKey.QQ_BINDING_SECRET
    )
    if setting is None:
        return
    await session.delete(setting)
    await session.commit()
