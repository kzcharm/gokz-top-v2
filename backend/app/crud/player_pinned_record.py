from sqlalchemy.exc import IntegrityError
from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.crud.record import get_pb_record_publics
from app.models import (
    ModeScope,
    PlayerPinnedRecord,
    PlayerPinnedRecordPublic,
    RecordType,
)

MAX_PLAYER_PINNED_RECORDS = 6


async def get_player_pinned_record(
    *,
    session: AsyncSession,
    player_steamid64: int,
    map_id: int,
    stage: int,
    record_type: RecordType,
) -> PlayerPinnedRecord | None:
    statement = (
        select(PlayerPinnedRecord)
        .where(
            col(PlayerPinnedRecord.player_steamid64) == player_steamid64,
            col(PlayerPinnedRecord.map_id) == map_id,
            col(PlayerPinnedRecord.stage) == stage,
            col(PlayerPinnedRecord.type) == record_type,
        )
        .limit(1)
    )
    return (await session.exec(statement)).first()


async def list_player_pinned_records(
    *,
    session: AsyncSession,
    player_steamid64: int,
) -> list[PlayerPinnedRecord]:
    statement = (
        select(PlayerPinnedRecord)
        .where(
            col(PlayerPinnedRecord.player_steamid64) == player_steamid64,
        )
        .order_by(
            col(PlayerPinnedRecord.created_at).desc(),
            col(PlayerPinnedRecord.id).desc(),
        )
    )
    return list((await session.exec(statement)).all())


async def create_player_pinned_record(
    *,
    session: AsyncSession,
    player_steamid64: int,
    map_id: int,
    stage: int,
    record_type: RecordType,
) -> PlayerPinnedRecord:
    existing = await get_player_pinned_record(
        session=session,
        player_steamid64=player_steamid64,
        map_id=map_id,
        stage=stage,
        record_type=record_type,
    )
    if existing is not None:
        return existing

    count_statement = select(func.count()).select_from(PlayerPinnedRecord).where(
        col(PlayerPinnedRecord.player_steamid64) == player_steamid64,
    )
    count = int((await session.exec(count_statement)).one())
    if count >= MAX_PLAYER_PINNED_RECORDS:
        oldest_statement = (
            select(PlayerPinnedRecord)
            .where(
                col(PlayerPinnedRecord.player_steamid64) == player_steamid64,
            )
            .order_by(
                col(PlayerPinnedRecord.created_at).asc(),
                col(PlayerPinnedRecord.id).asc(),
            )
            .limit(1)
        )
        oldest = (await session.exec(oldest_statement)).first()
        if oldest is not None:
            await session.delete(oldest)
            await session.flush()

    pinned_record = PlayerPinnedRecord(
        player_steamid64=player_steamid64,
        map_id=map_id,
        stage=stage,
        type=record_type,
    )
    session.add(pinned_record)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing = await get_player_pinned_record(
            session=session,
            player_steamid64=player_steamid64,
            map_id=map_id,
            stage=stage,
            record_type=record_type,
        )
        if existing is None:
            raise
        return existing

    await session.refresh(pinned_record)
    return pinned_record


async def delete_player_pinned_record(
    *,
    session: AsyncSession,
    player_steamid64: int,
    map_id: int,
    stage: int,
    record_type: RecordType,
) -> bool:
    existing = await get_player_pinned_record(
        session=session,
        player_steamid64=player_steamid64,
        map_id=map_id,
        stage=stage,
        record_type=record_type,
    )
    if existing is None:
        return False

    await session.delete(existing)
    await session.commit()
    return True


async def resolve_player_pinned_records_public(
    *,
    session: AsyncSession,
    player_steamid64: int,
    scope: ModeScope,
) -> list[PlayerPinnedRecordPublic]:
    pinned_records = await list_player_pinned_records(
        session=session,
        player_steamid64=player_steamid64,
    )

    resolved_records: list[PlayerPinnedRecordPublic] = []
    for pinned_record in pinned_records:
        records = await get_pb_record_publics(
            session,
            map_id=pinned_record.map_id,
            map_name=None,
            stage=pinned_record.stage,
            steamid64=player_steamid64,
            scope=scope,
            record_type=pinned_record.type,
            country=None,
            region=None,
            exclude_cheaters=False,
            offset=0,
            limit=1,
        )
        if len(records) == 0:
            continue

        resolved_records.append(
            PlayerPinnedRecordPublic(
                id=pinned_record.id,
                player_steamid64=str(pinned_record.player_steamid64),
                map_id=pinned_record.map_id,
                stage=pinned_record.stage,
                type=pinned_record.type,
                created_at=pinned_record.created_at,
                updated_at=pinned_record.updated_at,
                record=records[0],
            )
        )

    return resolved_records
