"""Compute direct-record server readiness from authenticated heartbeat evidence."""

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import (
    KZMode,
    Map,
    MapCourse,
    Mode,
    Server,
    ServerGroup,
    ServerGroupStatus,
    ServerStatus,
    ServerStatusPut,
)
from app.services.record_replay_policy import effective_record_filter_mode
from app.services.record_submission_policy import (
    available_record_filter_modes,
    mode_version_supported,
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
        await available_record_filter_modes(session, map_id=map_obj.id, stage=0)
        if map_obj and course
        else set()
    )
    modes = {
        mode.value: bool(
            mode_version_supported(
                submitted=evidence.mode_versions.get(mode.value, 0),
                minimum=configured_modes.get(mode),
            )
            and effective_record_filter_mode(mode) in filter_modes
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
