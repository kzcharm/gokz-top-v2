import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import case
from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import (
    Map,
    Mode,
    Player,
    RecentRecordCompatPublicV0,
    Record,
    RecordCompatPublicV0,
    RecordListQuery,
    RecordPatch,
    RecordPublic,
    ServerGlobalapi,
    ServerGlobalapiCompatPublicV0,
    TeleportsType,
    WorldRecordCountCompatPublicV0,
    get_datetime_utc,
)


def _record_tie_breakers() -> tuple:
    return (
        col(Record.id).asc().nullslast(),
        col(Record.uuid).asc(),
    )


async def _load_record_context(
    *,
    session: AsyncSession,
    record: Record,
) -> tuple[Player, ServerGlobalapi, Map, Mode]:
    player = await session.get(Player, record.steamid64)
    server = await session.get(ServerGlobalapi, record.server_id)
    map_obj = await session.get(Map, record.map_id)
    mode = await session.get(Mode, record.mode_id)
    if player is None or server is None or map_obj is None or mode is None:
        raise ValueError("Record references missing related entities")
    return player, server, map_obj, mode


def _to_server_globalapi_compat_public_v0(
    *,
    server: ServerGlobalapi,
) -> ServerGlobalapiCompatPublicV0:
    return ServerGlobalapiCompatPublicV0(
        id=server.id,
        port=server.port,
        ip=server.ip,
        name=server.name,
        owner_steamid64=str(server.owner_steamid64),
    )


def to_record_public(
    *,
    record: Record,
    player: Player,
    server: ServerGlobalapi,
    map_obj: Map,
    mode: Mode,
) -> RecordPublic:
    return RecordPublic(
        uuid=record.uuid,
        id=record.id,
        steamid64=str(record.steamid64),
        player_name=player.name,
        player_avatar_hash=player.avatar_hash,
        steam_id=None,
        server_id=record.server_id,
        server_name=server.name or "",
        map_id=record.map_id,
        map_name=map_obj.name,
        mode_id=record.mode_id,
        mode=mode.name,
        stage=record.stage,
        tickrate=128,
        time=float(record.time),
        teleports=record.teleports,
        points=record.points,
        created_on=record.created_on,
        updated_on=record.updated_on,
        updated_by=str(record.updated_by),
        replay_id=record.replay_id,
        is_valid=record.is_valid,
    )


def to_record_compat_public_v0(
    *,
    record: Record,
    player: Player,
    server: ServerGlobalapi,
    map_obj: Map,
    mode: Mode,
) -> RecordCompatPublicV0:
    if record.id is None:
        raise ValueError("Compat responses require a non-null GlobalAPI id")
    return RecordCompatPublicV0(
        id=record.id,
        steamid64=record.steamid64,
        player_name=player.name,
        steam_id=None,
        server_id=record.server_id,
        server_name=server.name or "",
        map_id=record.map_id,
        map_name=map_obj.name,
        mode=mode.name,
        stage=record.stage,
        tickrate=128,
        time=float(record.time),
        teleports=record.teleports,
        points=record.points,
        created_on=record.created_on,
        updated_on=record.updated_on,
        updated_by=record.updated_by,
        record_filter_id=0,
        replay_id=record.replay_id,
        server=_to_server_globalapi_compat_public_v0(server=server),
    )


async def read_records(
    *,
    session: AsyncSession,
    query: RecordListQuery,
) -> tuple[list[Record], int]:
    filters: list[object] = []

    if query.id:
        filters.append(col(Record.id).in_(query.id))
    if query.steamid64 is not None:
        filters.append(col(Record.steamid64) == query.steamid64)
    if query.server_id is not None:
        filters.append(col(Record.server_id) == query.server_id)
    if query.mode_id is not None:
        filters.append(col(Record.mode_id) == query.mode_id)
    if query.map_id is not None:
        filters.append(col(Record.map_id) == query.map_id)
    if query.stage is not None:
        filters.append(col(Record.stage) == query.stage)
    if query.teleports is not None:
        filters.append(col(Record.teleports) == query.teleports)
    if query.replay_id is not None:
        filters.append(col(Record.replay_id) == query.replay_id)
    if query.is_valid is not None:
        filters.append(col(Record.is_valid) == query.is_valid)
    if query.created_since is not None:
        filters.append(col(Record.created_on) >= query.created_since)
    if query.updated_since is not None:
        filters.append(col(Record.updated_on) >= query.updated_since)

    count_statement = select(func.count()).select_from(Record)
    statement = select(Record)
    for condition in filters:
        count_statement = count_statement.where(condition)
        statement = statement.where(condition)

    count = (await session.exec(count_statement)).one()
    statement = (
        statement.order_by(col(Record.created_on).desc(), col(Record.uuid).desc())
        .offset(query.offset)
        .limit(query.limit)
    )
    records = list((await session.exec(statement)).all())
    return records, count


async def get_record_by_uuid(
    *,
    session: AsyncSession,
    record_uuid: uuid.UUID,
) -> Record | None:
    return await session.get(Record, record_uuid)


async def get_record_by_id(
    *,
    session: AsyncSession,
    record_id: int,
) -> Record | None:
    statement = select(Record).where(col(Record.id) == record_id).limit(1)
    return (await session.exec(statement)).first()


async def update_record_validity(
    *,
    session: AsyncSession,
    record: Record,
    patch: RecordPatch,
) -> Record:
    record.is_valid = patch.is_valid
    record.updated_on = get_datetime_utc()
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return record


async def get_max_record_globalapi_id(*, session: AsyncSession) -> int | None:
    statement = select(func.max(Record.id)).where(Record.id.is_not(None))
    return (await session.exec(statement)).one()


def _apply_teleports_type(
    statement,
    teleports_type: TeleportsType,
):
    if teleports_type == TeleportsType.PRO:
        return statement.where(col(Record.teleports) == 0)
    if teleports_type == TeleportsType.NUB:
        return statement.where(col(Record.teleports) > 0)
    return statement


async def get_pb_records(
    session: AsyncSession,
    *,
    map_id: int | None,
    stage: int,
    steamid64: int | None,
    mode_ids: Sequence[int],
    teleports_type: TeleportsType,
    server_ids: Sequence[int] | None,
) -> list[Record]:
    statement = select(Record).where(col(Record.is_valid).is_(True))
    if mode_ids:
        statement = statement.where(col(Record.mode_id).in_(list(mode_ids)))
    if server_ids:
        statement = statement.where(col(Record.server_id).in_(list(server_ids)))

    if map_id is not None:
        statement = statement.where(
            col(Record.map_id) == map_id,
            col(Record.stage) == stage,
        )
        statement = _apply_teleports_type(statement, teleports_type)
        subquery = (
            statement.with_only_columns(Record.uuid)
            .distinct(col(Record.steamid64))
            .order_by(
                col(Record.steamid64),
                col(Record.time).asc(),
                *_record_tie_breakers(),
            )
            .subquery()
        )
        final_statement = (
            select(Record)
            .join(subquery, col(Record.uuid) == subquery.c.uuid)
            .order_by(
                col(Record.time).asc(),
                *_record_tie_breakers(),
            )
        )
        return list((await session.exec(final_statement)).all())

    if steamid64 is not None:
        statement = statement.where(col(Record.steamid64) == steamid64)
        statement = _apply_teleports_type(statement, teleports_type)
        subquery = (
            statement.with_only_columns(Record.uuid)
            .distinct(col(Record.map_id), col(Record.stage))
            .order_by(
                col(Record.map_id),
                col(Record.stage),
                col(Record.time).asc(),
                *_record_tie_breakers(),
            )
            .subquery()
        )
        final_statement = (
            select(Record)
            .join(subquery, col(Record.uuid) == subquery.c.uuid)
            .order_by(
                col(Record.map_id).asc(),
                col(Record.stage).asc(),
            )
        )
        return list((await session.exec(final_statement)).all())

    return []


def _teleports_bucket_expression():
    return case((col(Record.teleports) == 0, 0), else_=1)


async def get_record_place(
    *,
    session: AsyncSession,
    record: Record,
) -> int:
    teleports_condition = (
        col(Record.teleports) == 0 if record.teleports == 0 else col(Record.teleports) > 0
    )
    better_statement = select(func.count()).select_from(Record).where(
        col(Record.is_valid).is_(True),
        col(Record.id).is_not(None),
        col(Record.map_id) == record.map_id,
        col(Record.mode_id) == record.mode_id,
        col(Record.stage) == record.stage,
        teleports_condition,
        (
            (col(Record.time) < record.time)
            | (
                (col(Record.time) == record.time)
                & (
                    (col(Record.id) < record.id)
                    | (
                        col(Record.id).is_(None)
                        & (col(Record.uuid) < record.uuid)
                    )
                )
            )
        ),
    )
    better_count = (await session.exec(better_statement)).one()
    return better_count + 1


async def get_top_records_v0(
    *,
    session: AsyncSession,
    steamid64: int | None,
    server_id: int | None,
    map_id: int | None,
    map_name: str | None,
    mode_ids: Sequence[int],
    stage: int,
    has_teleports: bool | None,
    player_name: str | None,
    offset: int,
    limit: int,
) -> list[Record]:
    teleports_type = TeleportsType.OVR
    if has_teleports is True:
        teleports_type = TeleportsType.NUB
    elif has_teleports is False:
        teleports_type = TeleportsType.PRO

    resolved_map_id = map_id
    if resolved_map_id is None and map_name is not None:
        map_statement = select(Map).where(col(Map.name) == map_name).limit(1)
        map_obj = (await session.exec(map_statement)).first()
        if map_obj is None:
            return []
        resolved_map_id = map_obj.id

    if player_name:
        player_statement = select(Player.steamid64).where(
            col(Player.name).ilike(f"%{player_name}%")
        )
        player_ids = list((await session.exec(player_statement)).all())
        if not player_ids:
            return []
        if steamid64 is not None and steamid64 not in player_ids:
            return []
        if steamid64 is None:
            # For name searches without an explicit steamid, fall back to direct rows.
            statement = select(Record).where(
                col(Record.is_valid).is_(True),
                col(Record.id).is_not(None),
                col(Record.steamid64).in_(player_ids),
            )
            if resolved_map_id is not None:
                statement = statement.where(col(Record.map_id) == resolved_map_id)
            if server_id is not None:
                statement = statement.where(col(Record.server_id) == server_id)
            if mode_ids:
                statement = statement.where(col(Record.mode_id).in_(list(mode_ids)))
            statement = _apply_teleports_type(statement, teleports_type)
            statement = statement.where(col(Record.stage) == stage)
            statement = statement.order_by(col(Record.time).asc(), *_record_tie_breakers())
            statement = statement.offset(offset).limit(limit)
            return list((await session.exec(statement)).all())

    if resolved_map_id is not None or steamid64 is not None:
        records = await get_pb_records(
            session,
            map_id=resolved_map_id,
            stage=stage,
            steamid64=steamid64,
            mode_ids=mode_ids,
            teleports_type=teleports_type,
            server_ids=[server_id] if server_id is not None else None,
        )
        return records[offset : offset + limit]

    return []


async def get_world_record_counts_v0(
    *,
    session: AsyncSession,
    ids: Sequence[int] | None,
    map_ids: Sequence[int] | None,
    stages: Sequence[int] | None,
    mode_ids: Sequence[int] | None,
    has_teleports: bool | None,
    offset: int,
    limit: int,
) -> list[WorldRecordCountCompatPublicV0]:
    statement = select(Record).where(
        col(Record.is_valid).is_(True),
        col(Record.id).is_not(None),
    )
    if ids:
        statement = statement.where(col(Record.id).in_(list(ids)))
    if map_ids:
        statement = statement.where(col(Record.map_id).in_(list(map_ids)))
    if stages:
        statement = statement.where(col(Record.stage).in_(list(stages)))
    if mode_ids:
        statement = statement.where(col(Record.mode_id).in_(list(mode_ids)))
    if has_teleports is True:
        statement = statement.where(col(Record.teleports) > 0)
        distinct_columns = [col(Record.map_id), col(Record.stage), col(Record.mode_id)]
        order_columns = [
            col(Record.map_id),
            col(Record.stage),
            col(Record.mode_id),
            col(Record.time).asc(),
            *_record_tie_breakers(),
        ]
    elif has_teleports is False:
        statement = statement.where(col(Record.teleports) == 0)
        distinct_columns = [col(Record.map_id), col(Record.stage), col(Record.mode_id)]
        order_columns = [
            col(Record.map_id),
            col(Record.stage),
            col(Record.mode_id),
            col(Record.time).asc(),
            *_record_tie_breakers(),
        ]
    else:
        bucket = _teleports_bucket_expression()
        distinct_columns = [
            col(Record.map_id),
            col(Record.stage),
            col(Record.mode_id),
            bucket,
        ]
        order_columns = [
            col(Record.map_id),
            col(Record.stage),
            col(Record.mode_id),
            bucket,
            col(Record.time).asc(),
            *_record_tie_breakers(),
        ]

    winner_ids = (
        statement.with_only_columns(Record.uuid)
        .distinct(*distinct_columns)
        .order_by(*order_columns)
        .subquery()
    )
    winners_statement = select(Record).join(
        winner_ids, col(Record.uuid) == winner_ids.c.uuid
    )
    winners = list((await session.exec(winners_statement)).all())
    counts: dict[int, int] = {}
    for winner in winners:
        counts[winner.steamid64] = counts.get(winner.steamid64, 0) + 1

    sorted_counts = sorted(
        counts.items(),
        key=lambda item: (-item[1], item[0]),
    )
    sliced_counts = sorted_counts[offset : offset + limit]

    results: list[WorldRecordCountCompatPublicV0] = []
    for player_id, wr_count in sliced_counts:
        player = await session.get(Player, player_id)
        if player is None:
            continue
        results.append(
            WorldRecordCountCompatPublicV0(
                steamid64=player_id,
                player_name=player.name,
                steam_id=None,
                world_records=wr_count,
            )
        )
    return results


async def get_recent_top_records_v0(
    *,
    session: AsyncSession,
    steamid64: int | None,
    map_id: int | None,
    map_name: str | None,
    mode_ids: Sequence[int],
    stage: int | None,
    has_teleports: bool | None,
    created_since: datetime | None,
    place_top_at_least: int | None,
    place_top_overall_at_least: int | None,
    offset: int,
    limit: int,
) -> list[RecentRecordCompatPublicV0]:
    statement = select(Record).where(
        col(Record.is_valid).is_(True),
        col(Record.id).is_not(None),
    )
    if steamid64 is not None:
        statement = statement.where(col(Record.steamid64) == steamid64)
    if map_id is not None:
        statement = statement.where(col(Record.map_id) == map_id)
    if map_id is None and map_name is not None:
        statement = statement.join(Map, col(Record.map_id) == col(Map.id)).where(
            col(Map.name) == map_name
        )
    if mode_ids:
        statement = statement.where(col(Record.mode_id).in_(list(mode_ids)))
    if stage is not None:
        statement = statement.where(col(Record.stage) == stage)
    if has_teleports is True:
        statement = statement.where(col(Record.teleports) > 0)
    elif has_teleports is False:
        statement = statement.where(col(Record.teleports) == 0)
    if created_since is not None:
        statement = statement.where(col(Record.created_on) >= created_since)

    statement = statement.order_by(
        col(Record.created_on).desc(),
        col(Record.id).desc().nullslast(),
        col(Record.uuid).desc(),
    )
    recent_records = list((await session.exec(statement)).all())

    results: list[RecentRecordCompatPublicV0] = []
    for record in recent_records:
        place = await get_record_place(session=session, record=record)

        overall_statement = select(func.count()).select_from(Record).where(
            col(Record.is_valid).is_(True),
            col(Record.id).is_not(None),
            col(Record.map_id) == record.map_id,
            col(Record.mode_id) == record.mode_id,
            col(Record.stage) == record.stage,
            (
                (col(Record.time) < record.time)
                | (
                    (col(Record.time) == record.time)
                    & (
                        (col(Record.id) < record.id)
                        | (
                            col(Record.id).is_(None)
                            & (col(Record.uuid) < record.uuid)
                        )
                    )
                )
            ),
        )
        place_overall = (await session.exec(overall_statement)).one() + 1

        if place_top_at_least is not None and place > place_top_at_least:
            continue
        if (
            place_top_overall_at_least is not None
            and place_overall > place_top_overall_at_least
        ):
            continue

        player, server, map_obj, mode = await _load_record_context(
            session=session,
            record=record,
        )
        compat = to_record_compat_public_v0(
            record=record,
            player=player,
            server=server,
            map_obj=map_obj,
            mode=mode,
        )
        results.append(
            RecentRecordCompatPublicV0(
                **compat.model_dump(),
                place=place,
                place_overall=place_overall,
                top_100=place <= 100,
                top_100_overall=place_overall <= 100,
            )
        )

    return results[offset : offset + limit]
