"""Compute direct-record server readiness from authenticated heartbeat evidence."""

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import (
    KZMode,
    Map,
    MapCourse,
    MapCourseTier,
    Mode,
    Server,
    ServerGroup,
    ServerGroupStatus,
    ServerStatus,
    ServerStatusPut,
)


async def build_records_status(
    session: AsyncSession,
    group: ServerGroup | None,
    server: Server,
    payload: ServerStatusPut,
) -> dict[str, object]:
    evidence = payload.gokz_top_status
    assert evidence is not None
    map_obj = (
        await session.exec(
            select(Map).where(Map.name == payload.map.rsplit("/", 1)[-1])
        )
    ).first()
    course = (
        (
            await session.exec(
                select(MapCourse).where(
                    MapCourse.map_id == map_obj.id, MapCourse.stage == 0
                )
            )
        ).first()
        if map_obj
        else None
    )
    configured_modes = {
        mode.name_short: mode.latest_version
        for mode in (await session.exec(select(Mode))).all()
    }
    filter_modes = (
        set(
            (
                await session.exec(
                    select(MapCourseTier.mode).where(
                        MapCourseTier.course_id == course.id
                    )
                )
            ).all()
        )
        if course
        else set()
    )
    modes = {
        mode.value: bool(
            mode in configured_modes
            and evidence.mode_versions.get(mode.value, 0) > 0
            and configured_modes[mode] == evidence.mode_versions.get(mode.value)
            and (KZMode.KZT if mode == KZMode.NKZ else mode) in filter_modes
        )
        for mode in KZMode
    }
    return {
        "api_key_valid": bool(
            group
            and group.status == ServerGroupStatus.VALIDATED
            and server.group_id == group.id
            and server.status == ServerStatus.ENABLED
        ),
        "plugins_valid": evidence.plugins_valid,
        "settings_enforcer_valid": evidence.settings_enforcer_valid,
        "map_valid": bool(
            map_obj
            and map_obj.validated
            and evidence.bsp_size > 0
            and map_obj.filesize == evidence.bsp_size
            and course
        ),
        "modes": modes,
        "checked_at": payload.observed_at.isoformat(),
    }
