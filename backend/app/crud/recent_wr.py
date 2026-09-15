from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import and_, func, text
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import (
    Map,
    MapCourse,
    MapCourseTier,
    Mode,
    ModeScope,
    Player,
    RecentWrAchievementPublic,
    RecentWrEventCache,
    RecentWrListQuery,
    RecentWrPublic,
    Record,
    RecordType,
    ScheduledTaskState,
    ServerGlobalapi,
    ServerGroup,
    mode_scope_modes,
)

from .record import to_recent_record_public

RECENT_WR_BACKFILL_TASK_NAME = "recent_wr_events_backfill_v3"
RECENT_WR_NOTIFY_CHANNEL = "recent_wr_updates"


@dataclass(frozen=True)
class RecentWrBucketRefreshResult:
    deleted: int
    inserted: int
    updated: int

    @property
    def written(self) -> int:
        return self.inserted + self.updated


async def recent_wr_backfill_is_ready(*, session: AsyncSession) -> bool:
    state = await session.get(ScheduledTaskState, RECENT_WR_BACKFILL_TASK_NAME)
    return state is not None and state.last_successful_at is not None


async def rebuild_recent_wr_bucket(
    *,
    session: AsyncSession,
    map_id: int,
    scope: ModeScope,
    record_type: RecordType,
    notify: bool = False,
) -> RecentWrBucketRefreshResult:
    existing_record_uuids = set(
        (
            await session.exec(
                select(RecentWrEventCache.record_uuid).where(
                    col(RecentWrEventCache.map_id) == map_id,
                    col(RecentWrEventCache.scope) == scope,
                    col(RecentWrEventCache.type) == record_type,
                )
            )
        ).all()
    )
    deleted_result = await session.exec(
        cast(
            Any,
            text(
                """
                DELETE FROM cache.recent_wr_events AS event
                USING record, map
                WHERE event.record_uuid = record.uuid
                  AND event.map_id = map.id
                  AND event.map_id = :map_id
                  AND event.scope = CAST(:scope AS mode_scope)
                  AND event.type = CAST(:record_type AS record_type)
                  AND (
                      record.is_valid = false
                      OR map.validated = false
                      OR EXISTS (
                          SELECT 1
                          FROM ban
                          WHERE ban.steamid64 = record.steamid64
                            AND (
                                ban.expires_at IS NULL
                                OR ban.expires_at >= CURRENT_TIMESTAMP
                            )
                      )
                  )
                RETURNING event.record_uuid
                """
            ),
        ),
        params={
            "map_id": map_id,
            "scope": str(scope),
            "record_type": record_type.value,
        },
    )
    deleted_record_uuids = {row[0] for row in deleted_result.all()}
    surviving_record_uuids = existing_record_uuids - deleted_record_uuids
    insert_sql = text(
        """
        WITH winner AS (
            SELECT
                r.uuid AS record_uuid,
                r.map_id,
                r.time,
                r.created_at,
                pb.course_id
            FROM record_pb AS pb
            JOIN map_course AS course ON course.id = pb.course_id
            JOIN record AS r ON r.uuid = pb.record_uuid
            JOIN map AS m ON m.id = r.map_id
            WHERE course.map_id = :map_id
              AND course.stage = 0
              AND pb.scope = CAST(:scope AS mode_scope)
              AND pb.type = CAST(:record_type AS record_type)
              AND pb.points = 1000
              AND r.is_valid = true
              AND m.validated = true
              AND NOT EXISTS (
                  SELECT 1
                  FROM ban AS b
                  WHERE b.steamid64 = r.steamid64
                    AND (b.expires_at IS NULL OR b.expires_at >= CURRENT_TIMESTAMP)
              )
            LIMIT 1
        )
        INSERT INTO cache.recent_wr_events (
            record_uuid,
            scope,
            type,
            map_id,
            previous_record_uuid,
            previous_time,
            event_created_at
        )
        SELECT
            winner.record_uuid,
            CAST(:scope AS mode_scope),
            CAST(:record_type AS record_type),
            winner.map_id,
            previous.record_uuid,
            previous.time,
            winner.created_at
        FROM winner
        LEFT JOIN LATERAL (
            SELECT
                previous_record.uuid AS record_uuid,
                previous_pb.time
            FROM record_pb AS previous_pb
            JOIN record AS previous_record
              ON previous_record.uuid = previous_pb.record_uuid
            WHERE previous_pb.scope = CAST(:scope AS mode_scope)
              AND previous_pb.course_id = winner.course_id
              AND previous_pb.type = CAST(:record_type AS record_type)
              AND previous_pb.record_uuid <> winner.record_uuid
              AND previous_pb.time > winner.time
              AND previous_record.is_valid = true
              AND NOT EXISTS (
                  SELECT 1
                  FROM ban AS previous_ban
                  WHERE previous_ban.steamid64 = previous_record.steamid64
                    AND (
                        previous_ban.expires_at IS NULL
                        OR previous_ban.expires_at >= CURRENT_TIMESTAMP
                    )
              )
            ORDER BY previous_pb.time ASC, previous_pb.record_uuid ASC
            LIMIT 1
        ) AS previous ON true
        ON CONFLICT (record_uuid, scope, type) DO UPDATE SET
            map_id = EXCLUDED.map_id,
            previous_record_uuid = EXCLUDED.previous_record_uuid,
            previous_time = EXCLUDED.previous_time,
            event_created_at = EXCLUDED.event_created_at
        RETURNING record_uuid
        """
    )
    inserted_result = await session.exec(
        cast(Any, insert_sql),
        params={
            "map_id": map_id,
            "scope": str(scope),
            "record_type": record_type.value,
        },
    )
    resulting_record_uuids = {row[0] for row in inserted_result.all()}
    inserted = len(resulting_record_uuids - surviving_record_uuids)
    updated = len(resulting_record_uuids & surviving_record_uuids)
    deleted = len(deleted_record_uuids)
    if notify and (deleted > 0 or inserted > 0 or updated > 0):
        await session.exec(
            cast(
                Any,
                text(f"SELECT pg_notify('{RECENT_WR_NOTIFY_CHANNEL}', :scope)"),
            ),
            params={"scope": str(scope)},
        )
    return RecentWrBucketRefreshResult(
        deleted=deleted,
        inserted=inserted,
        updated=updated,
    )


async def rebuild_recent_wr_events_for_map(
    *,
    session: AsyncSession,
    map_id: int,
    notify: bool = False,
) -> RecentWrBucketRefreshResult:
    deleted = 0
    inserted = 0
    updated = 0
    changed_scopes: set[ModeScope] = set()
    for scope in ModeScope:
        for record_type in RecordType:
            result = await rebuild_recent_wr_bucket(
                session=session,
                map_id=map_id,
                scope=scope,
                record_type=record_type,
                notify=False,
            )
            deleted += result.deleted
            inserted += result.inserted
            updated += result.updated
            if result.deleted or result.inserted or result.updated:
                changed_scopes.add(scope)
    if notify:
        for scope in sorted(changed_scopes, key=lambda value: value.value):
            await session.exec(
                cast(
                    Any,
                    text(f"SELECT pg_notify('{RECENT_WR_NOTIFY_CHANNEL}', :scope)"),
                ),
                params={"scope": scope.value},
            )
    return RecentWrBucketRefreshResult(
        deleted=deleted,
        inserted=inserted,
        updated=updated,
    )


async def rebuild_recent_wr_events_for_maps(
    *,
    session: AsyncSession,
    map_ids: list[int],
    notify: bool = False,
) -> RecentWrBucketRefreshResult:
    if not map_ids:
        return RecentWrBucketRefreshResult(deleted=0, inserted=0, updated=0)

    existing_rows = (
        await session.exec(
            select(
                RecentWrEventCache.record_uuid,
                RecentWrEventCache.scope,
                RecentWrEventCache.type,
            ).where(col(RecentWrEventCache.map_id).in_(map_ids))
        )
    ).all()
    existing_keys = {
        (record_uuid, ModeScope(scope), RecordType(record_type))
        for record_uuid, scope, record_type in existing_rows
    }
    deleted_result = await session.exec(
        cast(
            Any,
            text(
                """
                DELETE FROM cache.recent_wr_events AS event
                USING record, map
                WHERE event.record_uuid = record.uuid
                  AND event.map_id = map.id
                  AND event.map_id = ANY(:map_ids)
                  AND (
                      record.is_valid = false
                      OR map.validated = false
                      OR EXISTS (
                          SELECT 1
                          FROM ban
                          WHERE ban.steamid64 = record.steamid64
                            AND (
                                ban.expires_at IS NULL
                                OR ban.expires_at >= CURRENT_TIMESTAMP
                            )
                      )
                  )
                RETURNING event.record_uuid, event.scope::text, event.type::text
                """
            ),
        ),
        params={"map_ids": map_ids},
    )
    deleted_keys = {
        (record_uuid, ModeScope(scope), RecordType(record_type))
        for record_uuid, scope, record_type in deleted_result.all()
    }
    surviving_keys = existing_keys - deleted_keys
    insert_sql = text(
        """
        WITH winners AS (
            SELECT
                record.uuid AS record_uuid,
                record.map_id,
                record.time,
                record.created_at,
                pb.scope,
                pb.type,
                pb.course_id
            FROM record_pb AS pb
            JOIN map_course AS course ON course.id = pb.course_id
            JOIN record ON record.uuid = pb.record_uuid
            JOIN map ON map.id = record.map_id
            WHERE course.map_id = ANY(:map_ids)
              AND course.stage = 0
              AND pb.points = 1000
              AND record.is_valid = true
              AND map.validated = true
              AND NOT EXISTS (
                  SELECT 1
                  FROM ban
                  WHERE ban.steamid64 = record.steamid64
                    AND (ban.expires_at IS NULL OR ban.expires_at >= CURRENT_TIMESTAMP)
              )
        )
        INSERT INTO cache.recent_wr_events (
            record_uuid,
            scope,
            type,
            map_id,
            previous_record_uuid,
            previous_time,
            event_created_at
        )
        SELECT
            winner.record_uuid,
            winner.scope,
            winner.type,
            winner.map_id,
            previous.record_uuid,
            previous.time,
            winner.created_at
        FROM winners AS winner
        LEFT JOIN LATERAL (
            SELECT
                previous_record.uuid AS record_uuid,
                previous_pb.time
            FROM record_pb AS previous_pb
            JOIN record AS previous_record
              ON previous_record.uuid = previous_pb.record_uuid
            WHERE previous_pb.scope = winner.scope
              AND previous_pb.course_id = winner.course_id
              AND previous_pb.type = winner.type
              AND previous_pb.record_uuid <> winner.record_uuid
              AND previous_pb.time > winner.time
              AND previous_record.is_valid = true
              AND NOT EXISTS (
                  SELECT 1
                  FROM ban AS previous_ban
                  WHERE previous_ban.steamid64 = previous_record.steamid64
                    AND (
                        previous_ban.expires_at IS NULL
                        OR previous_ban.expires_at >= CURRENT_TIMESTAMP
                    )
              )
            ORDER BY previous_pb.time ASC, previous_pb.record_uuid ASC
            LIMIT 1
        ) AS previous ON true
        ON CONFLICT (record_uuid, scope, type) DO UPDATE SET
            map_id = EXCLUDED.map_id,
            previous_record_uuid = EXCLUDED.previous_record_uuid,
            previous_time = EXCLUDED.previous_time,
            event_created_at = EXCLUDED.event_created_at
        RETURNING record_uuid, scope::text, type::text
        """
    )
    result_rows = (
        await session.exec(
            cast(Any, insert_sql),
            params={"map_ids": map_ids},
        )
    ).all()
    resulting_keys = {
        (record_uuid, ModeScope(scope), RecordType(record_type))
        for record_uuid, scope, record_type in result_rows
    }
    inserted = len(resulting_keys - surviving_keys)
    updated = len(resulting_keys & surviving_keys)
    deleted = len(deleted_keys)

    changed_scopes = {key[1] for key in deleted_keys | resulting_keys}
    if notify:
        for scope in sorted(changed_scopes, key=lambda value: value.value):
            await session.exec(
                cast(
                    Any,
                    text(f"SELECT pg_notify('{RECENT_WR_NOTIFY_CHANNEL}', :scope)"),
                ),
                params={"scope": scope.value},
            )
    return RecentWrBucketRefreshResult(
        deleted=deleted,
        inserted=inserted,
        updated=updated,
    )


async def rebuild_recent_wr_events_for_players(
    *,
    session: AsyncSession,
    steamid64s: list[int],
    notify: bool = False,
) -> RecentWrBucketRefreshResult:
    if not steamid64s:
        return RecentWrBucketRefreshResult(deleted=0, inserted=0, updated=0)
    map_ids = (
        await session.exec(
            select(col(Record.map_id))
            .where(
                col(Record.steamid64).in_(steamid64s),
                col(Record.stage) == 0,
            )
            .distinct()
        )
    ).all()
    return await rebuild_recent_wr_events_for_maps(
        session=session,
        map_ids=sorted(map_ids),
        notify=notify,
    )


async def read_recent_wrs(
    *,
    session: AsyncSession,
    query: RecentWrListQuery,
) -> tuple[list[RecentWrPublic], int]:
    scoped_tier = (
        select(func.coalesce(func.min(func.nullif(MapCourseTier.tier, 0)), 0))
        .select_from(MapCourse)
        .join(MapCourseTier, col(MapCourseTier.course_id) == col(MapCourse.id))
        .where(
            col(MapCourse.map_id) == col(RecentWrEventCache.map_id),
            col(MapCourse.stage) == 0,
            col(MapCourseTier.mode).in_(list(mode_scope_modes(query.scope))),
        )
        .correlate(RecentWrEventCache)
        .scalar_subquery()
    )
    filters = [
        col(RecentWrEventCache.scope) == query.scope,
        col(Map.validated).is_(True),
    ]
    if query.map_id is not None:
        filters.append(col(RecentWrEventCache.map_id) == query.map_id)
    if query.type is not None:
        filters.append(col(RecentWrEventCache.type) == query.type)
    if query.tier is not None:
        filters.append(scoped_tier == query.tier)

    base: Any = (
        select(
            col(RecentWrEventCache.record_uuid).label("record_uuid"),
            func.max(col(RecentWrEventCache.event_created_at)).label("created_at"),
        )
        .join(Map, col(Map.id) == col(RecentWrEventCache.map_id))
        .where(*filters)
        .group_by(col(RecentWrEventCache.record_uuid))
    )
    count = int(
        (await session.exec(select(func.count()).select_from(base.subquery()))).one()
    )
    page = (
        base.order_by(
            text("created_at DESC"),
            col(RecentWrEventCache.record_uuid).desc(),
        )
        .offset(query.offset)
        .limit(query.limit)
        .cte("recent_wr_page")
    )
    rows = (
        await session.exec(
            select(  # type: ignore[call-overload]
                Record,
                Player,
                ServerGlobalapi,
                ServerGroup,
                Map,
                Mode,
                RecentWrEventCache,
                scoped_tier.label("tier"),
            )
            .join(page, page.c.record_uuid == col(Record.uuid))
            .join(Player, col(Player.steamid64) == col(Record.steamid64))
            .join(ServerGlobalapi, col(ServerGlobalapi.id) == col(Record.server_id))
            .outerjoin(
                ServerGroup, col(ServerGroup.id) == col(ServerGlobalapi.group_id)
            )
            .join(Map, col(Map.id) == col(Record.map_id))
            .join(Mode, col(Mode.name_short) == col(Record.mode))
            .join(
                RecentWrEventCache,
                and_(
                    col(RecentWrEventCache.record_uuid) == col(Record.uuid),
                    col(RecentWrEventCache.scope) == query.scope,
                ),
            )
            .order_by(
                page.c.created_at.desc(),
                page.c.record_uuid.desc(),
                col(RecentWrEventCache.type).asc(),
            )
        )
    ).all()

    previous_record_uuids = {
        event.previous_record_uuid
        for _, _, _, _, _, _, event, _ in rows
        if event.previous_record_uuid is not None
    }
    previous_player_names: dict[uuid.UUID, str] = {}
    if previous_record_uuids:
        previous_player_rows = (
            await session.exec(
                select(
                    col(Record.uuid),
                    col(Player.alias),
                    col(Player.name),
                )
                .join(Player, col(Player.steamid64) == col(Record.steamid64))
                .where(col(Record.uuid).in_(previous_record_uuids))
            )
        ).all()
        previous_player_names = {
            record_uuid: alias or name
            for record_uuid, alias, name in previous_player_rows
        }

    items: dict[uuid.UUID, RecentWrPublic] = {}
    for record, player, server, server_group, map_obj, mode, event, tier in rows:
        item = items.get(record.uuid)
        if item is None:
            item = RecentWrPublic(
                record=to_recent_record_public(
                    record=record,
                    player=player,
                    server=server,
                    server_group=server_group,
                    map_obj=map_obj,
                    mode=mode,
                    map_tier=tier,
                    points=1000,
                ),
                achievements=[],
            )
            items[record.uuid] = item
        previous_time = (
            float(event.previous_time) if event.previous_time is not None else None
        )
        item.achievements.append(
            RecentWrAchievementPublic(
                type=event.type,
                previous_record_uuid=event.previous_record_uuid,
                previous_player_name=(
                    previous_player_names.get(event.previous_record_uuid)
                    if event.previous_record_uuid is not None
                    else None
                ),
                previous_time=previous_time,
                improvement_seconds=(
                    round(previous_time - float(record.time), 3)
                    if previous_time is not None
                    else None
                ),
            )
        )
    return list(items.values()), count
