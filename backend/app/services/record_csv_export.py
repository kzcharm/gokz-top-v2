from __future__ import annotations

import csv
import gzip
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import func, or_
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import async_session_maker
from app.models import (
    KZMode,
    Map,
    Player,
    Record,
    ServerGlobalapi,
    ServerGroup,
    seconds_to_time_ms,
)

STEAMID64_ACCOUNT_ID_BASE = 76_561_197_960_265_728
STEAM_ACCOUNT_ID_MAX = 4_294_967_295

CSV_HEADER = (
    "record_uuid",
    "globalapi_record_id",
    "server_id",
    "steamid64",
    "steamid32",
    "player_name",
    "player_country",
    "map_id",
    "map_name",
    "stage",
    "mode",
    "local_mode",
    "style",
    "runtime_seconds",
    "runtime_ms",
    "teleports",
    "created_at",
    "updated_at",
    "replay_id",
    "is_valid",
)

LOCAL_MODE_BY_KZ_MODE = {
    KZMode.VNL: 0,
    KZMode.SKZ: 1,
    KZMode.KZT: 2,
    KZMode.NKZ: 3,
}

STREAM_BATCH_SIZE = 1_000


@dataclass(frozen=True, slots=True)
class RecordCsvExportResult:
    output_path: Path
    server_ids: tuple[int, ...]
    after: datetime | None
    before: datetime | None
    exported_rows: int
    skipped_invalid_rows: int
    skipped_bad_steamid_rows: int
    compressed_size: int


def parse_datetime_boundary(value: str | None, *, is_end: bool = False) -> datetime | None:
    """Parse an ISO date or datetime as an inclusive UTC boundary."""
    if value is None:
        return None
    try:
        parsed = datetime.combine(
            date.fromisoformat(value), time.max if is_end else time.min
        )
    except ValueError:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"Invalid ISO 8601 date/datetime: {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _format_datetime(value: datetime) -> str:
    normalized = value.astimezone(UTC) if value.tzinfo is not None else value.replace(
        tzinfo=UTC
    )
    return normalized.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _format_runtime_seconds(value: Decimal) -> str:
    return f"{value:.3f}"


async def _resolve_server_ids(
    *,
    session: AsyncSession,
    server_ids: list[int] | None,
    server_groups: list[str] | None,
) -> tuple[int, ...]:
    if bool(server_ids) == bool(server_groups):
        raise ValueError(
            "Use exactly one selector: --server-id or --server-group. "
            "Repeat the selected option for multiple values."
        )

    if server_ids:
        requested_ids = sorted(set(server_ids))
        existing_ids = set(
            (
                await session.exec(
                    select(ServerGlobalapi.id).where(
                        col(ServerGlobalapi.id).in_(requested_ids)
                    )
                )
            ).all()
        )
        missing_ids = sorted(set(requested_ids) - existing_ids)
        if missing_ids:
            missing = ", ".join(str(server_id) for server_id in missing_ids)
            raise ValueError(f"Unknown GlobalAPI server ID(s): {missing}")
        return tuple(requested_ids)

    group_ids: set[uuid.UUID] = set()
    for identifier in server_groups or []:
        normalized = identifier.strip()
        if not normalized:
            raise ValueError("Server group identifiers cannot be blank")

        parsed_id: uuid.UUID | None = None
        try:
            parsed_id = uuid.UUID(normalized)
        except ValueError:
            pass

        conditions = [
            col(ServerGroup.custom_id) == normalized,
            col(ServerGroup.name) == normalized,
        ]
        if parsed_id is not None:
            conditions.append(col(ServerGroup.id) == parsed_id)
        matches = list(
            (
                await session.exec(
                    select(ServerGroup).where(or_(*conditions))
                )
            ).all()
        )
        unique_matches = {group.id: group for group in matches}
        if not unique_matches:
            raise ValueError(f"Unknown server group: {identifier!r}")
        if len(unique_matches) > 1:
            raise ValueError(f"Ambiguous server group identifier: {identifier!r}")
        group_ids.add(next(iter(unique_matches)))

    resolved_ids = sorted(
        set(
            (
                await session.exec(
                    select(ServerGlobalapi.id).where(
                        col(ServerGlobalapi.group_id).in_(group_ids)
                    )
                )
            ).all()
        )
    )
    if not resolved_ids:
        raise ValueError("The selected server group(s) have no GlobalAPI servers")
    return tuple(resolved_ids)


def _selection_predicates(
    *,
    server_ids: tuple[int, ...],
    after: datetime | None,
    before: datetime | None,
) -> list[Any]:
    predicates: list[Any] = [col(Record.server_id).in_(server_ids)]
    if after is not None:
        predicates.append(col(Record.created_at) >= after)
    if before is not None:
        predicates.append(col(Record.created_at) <= before)
    return predicates


def _bad_steamid_predicate() -> Any:
    return or_(
        col(Record.steamid64) < STEAMID64_ACCOUNT_ID_BASE,
        col(Record.steamid64)
        > STEAMID64_ACCOUNT_ID_BASE + STEAM_ACCOUNT_ID_MAX,
    )


async def _get_exclusion_counts(
    *,
    session: AsyncSession,
    selection_predicates: list[Any],
) -> tuple[int, int]:
    bad_steamid = _bad_steamid_predicate()
    invalid_rows, bad_steamid_rows = (
        await session.exec(
            select(
                func.count()
                .filter(col(Record.is_valid).is_(False))
                .label("invalid_rows"),
                func.count()
                .filter(col(Record.is_valid).is_(True), bad_steamid)
                .label("bad_steamid_rows"),
            )
            .select_from(Record)
            .where(*selection_predicates)
        )
    ).one()
    return int(invalid_rows), int(bad_steamid_rows)


async def _write_csv(
    *,
    session: AsyncSession,
    output_path: Path,
    selection_predicates: list[Any],
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
    player_name = func.coalesce(func.nullif(col(Player.alias), ""), col(Player.name))
    statement = (
        select(
            Record,
            player_name.label("player_name"),
            col(Player.country),
            col(Map.name).label("map_name"),
        )
        .join(Player, col(Player.steamid64) == col(Record.steamid64))
        .join(Map, col(Map.id) == col(Record.map_id))
        .where(
            *selection_predicates,
            col(Record.is_valid).is_(True),
            ~_bad_steamid_predicate(),
        )
        .order_by(
            col(Record.created_at).asc(),
            col(Record.id).asc().nullslast(),
            col(Record.uuid).asc(),
        )
        .execution_options(yield_per=STREAM_BATCH_SIZE)
    )

    exported_rows = 0
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
                record, display_name, player_country, map_name = row
                writer.writerow(
                    (
                        str(record.uuid),
                        record.id,
                        record.server_id,
                        record.steamid64,
                        record.steamid64 - STEAMID64_ACCOUNT_ID_BASE,
                        display_name,
                        player_country,
                        record.map_id,
                        map_name,
                        record.stage,
                        record.mode.value,
                        LOCAL_MODE_BY_KZ_MODE[record.mode],
                        0,
                        _format_runtime_seconds(record.time),
                        seconds_to_time_ms(record.time),
                        record.teleports,
                        _format_datetime(record.created_at),
                        _format_datetime(record.updated_at),
                        record.replay_id,
                        "true" if record.is_valid else "false",
                    )
                )
                exported_rows += 1
        if output_path.exists() and not force:
            raise ValueError(f"Output file already exists: {output_path}")
        os.replace(temporary_path, output_path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise
    return exported_rows


async def export_records_to_csv(
    *,
    output_path: Path,
    server_ids: list[int] | None,
    server_groups: list[str] | None,
    after: str | None,
    before: str | None,
    force: bool,
) -> RecordCsvExportResult:
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
        predicates = _selection_predicates(
            server_ids=resolved_server_ids,
            after=after_dt,
            before=before_dt,
        )
        skipped_invalid_rows, skipped_bad_steamid_rows = (
            await _get_exclusion_counts(
                session=session,
                selection_predicates=predicates,
            )
        )
        exported_rows = await _write_csv(
            session=session,
            output_path=output_path,
            selection_predicates=predicates,
            force=force,
        )

    return RecordCsvExportResult(
        output_path=output_path,
        server_ids=resolved_server_ids,
        after=after_dt,
        before=before_dt,
        exported_rows=exported_rows,
        skipped_invalid_rows=skipped_invalid_rows,
        skipped_bad_steamid_rows=skipped_bad_steamid_rows,
        compressed_size=output_path.stat().st_size,
    )
