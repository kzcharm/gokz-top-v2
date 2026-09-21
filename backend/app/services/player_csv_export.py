from __future__ import annotations

import csv
import gzip
import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import case, exists, func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import async_session_maker
from app.models import Ban, Player, PlayerSession, Record
from app.services.record_csv_export import (
    STEAM_ACCOUNT_ID_MAX,
    STEAMID64_ACCOUNT_ID_BASE,
    STREAM_BATCH_SIZE,
    _format_datetime,
    _resolve_server_ids,
    _selection_predicates,
    parse_datetime_boundary,
)

CSV_HEADER = (
    "steamid32",
    "steamid64",
    "alias",
    "cheater",
    "ip",
    "last_played_at",
    "country",
    "created_at",
)


@dataclass(frozen=True, slots=True)
class PlayerCsvExportResult:
    output_path: Path
    server_ids: tuple[int, ...]
    after: datetime | None
    before: datetime | None
    exported_players: int
    compressed_size: int


def _timestamp_choice(
    *,
    record_timestamp: Any,
    session_timestamp: Any,
    prefer_latest: bool,
) -> Any:
    chooser = func.greatest if prefer_latest else func.least
    return case(
        (session_timestamp.is_(None), record_timestamp),
        else_=chooser(record_timestamp, session_timestamp),
    )


async def _write_csv(
    *,
    session: AsyncSession,
    output_path: Path,
    server_ids: tuple[int, ...],
    after: datetime | None,
    before: datetime | None,
    force: bool,
) -> int:
    if output_path.suffixes[-2:] != [".csv", ".gz"]:
        raise ValueError("--output must end with .csv.gz")
    if output_path.exists() and not force:
        raise ValueError(f"Output file already exists: {output_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(
        f".{output_path.name}.{uuid.uuid4().hex}.part"
    )
    record_selection = _selection_predicates(
        server_ids=server_ids,
        after=after,
        before=before,
    )
    record_activity = (
        select(
            col(Record.steamid64).label("steamid64"),
            func.min(col(Record.created_at)).label("first_record_at"),
            func.max(col(Record.created_at)).label("last_record_at"),
        )
        .where(
            *record_selection,
            col(Record.is_valid).is_(True),
            col(Record.steamid64) >= STEAMID64_ACCOUNT_ID_BASE,
            col(Record.steamid64)
            <= STEAMID64_ACCOUNT_ID_BASE + STEAM_ACCOUNT_ID_MAX,
        )
        .group_by(col(Record.steamid64))
        .subquery()
    )

    latest_ip = (
        select(func.host(col(PlayerSession.ip_address)))
        .where(col(PlayerSession.player_steamid64) == col(Player.steamid64))
        .order_by(
            col(PlayerSession.connected_at).desc(),
            col(PlayerSession.id).desc(),
        )
        .limit(1)
        .scalar_subquery()
    )
    first_session_at = (
        select(func.min(col(PlayerSession.connected_at)))
        .where(col(PlayerSession.player_steamid64) == col(Player.steamid64))
        .scalar_subquery()
    )
    last_session_at = (
        select(func.max(col(PlayerSession.disconnect_at)))
        .where(col(PlayerSession.player_steamid64) == col(Player.steamid64))
        .scalar_subquery()
    )
    permanent_ban_exists = exists(
        select(Ban.uuid).where(
            col(Ban.steamid64) == col(Player.steamid64),
            col(Ban.expires_at).is_(None),
        )
    )
    display_name = func.coalesce(func.nullif(col(Player.alias), ""), col(Player.name))
    export_rows = (
        select(
            col(Player.steamid64).label("steamid64"),
            display_name.label("alias"),
            case((permanent_ban_exists, 1), else_=0).label("cheater"),
            latest_ip.label("ip"),
            _timestamp_choice(
                record_timestamp=record_activity.c.last_record_at,
                session_timestamp=last_session_at,
                prefer_latest=True,
            ).label("last_played_at"),
            col(Player.country).label("country"),
            _timestamp_choice(
                record_timestamp=record_activity.c.first_record_at,
                session_timestamp=first_session_at,
                prefer_latest=False,
            ).label("created_at"),
        )
        .join(
            record_activity,
            record_activity.c.steamid64 == col(Player.steamid64),
        )
        .subquery()
    )
    statement = (
        select(export_rows)
        .order_by(export_rows.c.steamid64.asc())
        .execution_options(yield_per=STREAM_BATCH_SIZE)
    )

    exported_players = 0
    try:
        result = await session.stream(statement)
        with gzip.open(
            temporary_path,
            "wt",
            encoding="utf-8",
            newline="",
            compresslevel=6,
        ) as output_file:
            writer = csv.writer(output_file)
            writer.writerow(CSV_HEADER)
            async for row in result:
                writer.writerow(
                    (
                        row.steamid64 - STEAMID64_ACCOUNT_ID_BASE,
                        row.steamid64,
                        row.alias,
                        row.cheater,
                        row.ip,
                        _format_datetime(row.last_played_at),
                        row.country,
                        _format_datetime(row.created_at),
                    )
                )
                exported_players += 1
        if output_path.exists() and not force:
            raise ValueError(f"Output file already exists: {output_path}")
        os.replace(temporary_path, output_path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise
    return exported_players


async def export_players_to_csv(
    *,
    output_path: Path,
    server_ids: list[int] | None,
    server_groups: list[str] | None,
    after: str | None,
    before: str | None,
    force: bool,
) -> PlayerCsvExportResult:
    after_dt = parse_datetime_boundary(after)
    before_dt = parse_datetime_boundary(before, is_end=True)
    if after_dt is not None and before_dt is not None and after_dt > before_dt:
        raise ValueError("--after must be earlier than or equal to --before")

    async with async_session_maker() as session:
        resolved_server_ids = await _resolve_server_ids(
            session=session,
            server_ids=server_ids,
            server_groups=server_groups,
        )
        exported_players = await _write_csv(
            session=session,
            output_path=output_path,
            server_ids=resolved_server_ids,
            after=after_dt,
            before=before_dt,
            force=force,
        )
    return PlayerCsvExportResult(
        output_path=output_path,
        server_ids=resolved_server_ids,
        after=after_dt,
        before=before_dt,
        exported_players=exported_players,
        compressed_size=output_path.stat().st_size,
    )
