from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, text, update
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.core.db import async_session_maker
from app.crud.record import recompute_record_pbs_for_keys
from app.models import (
    Ban,
    MapCourse,
    ModeScope,
    Player,
    PlayerStatCache,
    Record,
    RecordPb,
    RecordType,
    get_datetime_utc,
    mode_scope_modes,
    mode_scope_to_id,
)
from app.tasks.build import rating as rating_task

DEFAULT_SOURCE_STEAMID64 = 76561198764013745
DEFAULT_TARGET_STEAMID64 = 76561199019610922
DEFAULT_AUDIT_FILENAME = (
    "2026-06-14_76561198764013745_to_76561199019610922.jsonl"
)


@dataclass(frozen=True, slots=True)
class RecordTransferResult:
    source_steamid64: int
    target_steamid64: int
    dry_run: bool
    audit_path: Path
    summary_path: Path
    source_records_before: int
    target_records_before: int
    source_records_after: int
    target_records_after: int
    transferred_records: int
    touched_pb_keys: int
    touched_courses: int
    source_record_pb_after: int
    leaderboard_created: int
    leaderboard_updated: int
    player_stats_deleted: int
    checksum: str
    rating_rows_selected: int
    rating_rows_created: int
    rating_rows_updated: int


def default_audit_path() -> Path:
    repo_root = Path(__file__).resolve().parents[3]
    return repo_root / ".temp" / "record-transfers" / DEFAULT_AUDIT_FILENAME


def _json_default(value: object) -> str:
    return str(value)


def parse_datetime_boundary(value: str | None, *, is_end: bool = False) -> datetime | None:
    """Parse an ISO date or datetime as an inclusive UTC boundary."""
    if value is None:
        return None
    try:
        parsed = datetime.combine(
            date.fromisoformat(value), time.max if is_end else time.min
        )
    except ValueError:
        parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _record_audit_payload(
    *,
    record: Record,
    source_steamid64: int,
    target_steamid64: int,
) -> dict[str, Any]:
    return {
        "record_uuid": str(record.uuid),
        "id": record.id,
        "old_steamid64": str(source_steamid64),
        "new_steamid64": str(target_steamid64),
        "server_id": record.server_id,
        "mode": record.mode.value,
        "mode_id": record.mode_id,
        "map_id": record.map_id,
        "stage": record.stage,
        "time": str(record.time),
        "teleports": record.teleports,
        "points": record.points,
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
        "updated_by": record.updated_by,
        "replay_id": record.replay_id,
        "is_valid": record.is_valid,
    }


def _write_audit_files(
    *,
    audit_path: Path,
    records: list[Record],
    source_steamid64: int,
    target_steamid64: int,
    dry_run: bool,
) -> tuple[Path, str]:
    if audit_path.exists():
        raise RuntimeError(f"Audit file already exists: {audit_path}")
    audit_path.parent.mkdir(parents=True, exist_ok=True)

    checksum = hashlib.sha256()
    with audit_path.open("w", encoding="utf-8") as audit_file:
        for record in records:
            line = json.dumps(
                _record_audit_payload(
                    record=record,
                    source_steamid64=source_steamid64,
                    target_steamid64=target_steamid64,
                ),
                default=_json_default,
                sort_keys=True,
                separators=(",", ":"),
            )
            audit_file.write(f"{line}\n")
            checksum.update(line.encode("utf-8"))
            checksum.update(b"\n")

    summary_path = audit_path.with_suffix(".summary.json")
    summary_payload = {
        "source_steamid64": str(source_steamid64),
        "target_steamid64": str(target_steamid64),
        "dry_run": dry_run,
        "record_count": len(records),
        "sha256": checksum.hexdigest(),
        "audit_path": str(audit_path),
        "created_at": get_datetime_utc().isoformat(),
    }
    with summary_path.open("w", encoding="utf-8") as summary_file:
        json.dump(summary_payload, summary_file, indent=2, sort_keys=True)
        summary_file.write("\n")

    return summary_path, checksum.hexdigest()


async def _count_records(
    *,
    session: AsyncSession,
    steamid64: int,
    after: datetime | None = None,
    before: datetime | None = None,
) -> int:
    conditions = [col(Record.steamid64) == steamid64]
    if after is not None:
        conditions.append(col(Record.created_at) >= after)
    if before is not None:
        conditions.append(col(Record.created_at) <= before)
    return int(
        (
            await session.exec(
                select(func.count()).select_from(Record).where(*conditions)
            )
        ).one()
    )


async def _count_record_pbs(*, session: AsyncSession, steamid64: int) -> int:
    return int(
        (
            await session.exec(
                select(func.count()).select_from(RecordPb).where(
                    col(RecordPb.steamid64) == steamid64
                )
            )
        ).one()
    )


async def _load_source_records(
    *,
    session: AsyncSession,
    source_steamid64: int,
    after: datetime | None = None,
    before: datetime | None = None,
) -> list[Record]:
    conditions = [col(Record.steamid64) == source_steamid64]
    if after is not None:
        conditions.append(col(Record.created_at) >= after)
    if before is not None:
        conditions.append(col(Record.created_at) <= before)
    return list(
        (
            await session.exec(
                select(Record)
                .where(*conditions)
                .order_by(
                    col(Record.created_at).asc(),
                    col(Record.id).asc().nullslast(),
                    col(Record.uuid).asc(),
                )
            )
        ).all()
    )


async def _ensure_player_exists(*, session: AsyncSession, steamid64: int) -> None:
    player = await session.get(Player, steamid64)
    if player is None:
        raise RuntimeError(f"Player does not exist: {steamid64}")


async def _ensure_target_not_mirrored_banned(
    *,
    session: AsyncSession,
    target_steamid64: int,
) -> None:
    now = get_datetime_utc()
    active_ban = (
        await session.exec(
            select(Ban)
            .where(
                col(Ban.steamid64) == target_steamid64,
                col(Ban.id).is_not(None),
                (col(Ban.expires_at).is_(None)) | (col(Ban.expires_at) > now),
            )
            .limit(1)
        )
    ).first()
    if active_ban is not None:
        raise RuntimeError(
            "Target player has an active mirrored ban: "
            f"{target_steamid64} ban_uuid={active_ban.uuid} ban_id={active_ban.id}"
        )


async def _load_course_ids_by_record_key(
    *,
    session: AsyncSession,
    records: list[Record],
) -> dict[tuple[int, int], int]:
    course_keys = sorted({(record.map_id, record.stage) for record in records})
    if not course_keys:
        return {}

    rows = (
        await session.exec(
            select(MapCourse)
            .where(
                col(MapCourse.map_id).in_([map_id for map_id, _stage in course_keys]),
                col(MapCourse.stage).in_([stage for _map_id, stage in course_keys]),
            )
            .order_by(col(MapCourse.map_id), col(MapCourse.stage), col(MapCourse.id))
        )
    ).all()
    return {
        (course.map_id, course.stage): course.id
        for course in rows
        if course.id is not None
    }


def _scope_ids_for_record(record: Record) -> tuple[int, ...]:
    return tuple(
        mode_scope_to_id(scope)
        for scope in ModeScope
        if record.mode in mode_scope_modes(scope)
    )


def _pb_keys_for_records(
    *,
    records: list[Record],
    course_ids_by_record_key: dict[tuple[int, int], int],
    source_steamid64: int,
    target_steamid64: int,
) -> set[tuple[int, int, int, RecordType]]:
    keys: set[tuple[int, int, int, RecordType]] = set()
    for record in records:
        course_id = course_ids_by_record_key.get((record.map_id, record.stage))
        if course_id is None or not record.is_valid:
            continue
        record_types = [RecordType.NUB]
        if record.teleports == 0:
            record_types.append(RecordType.PRO)
        for scope_id in _scope_ids_for_record(record):
            for record_type in record_types:
                keys.add((scope_id, course_id, source_steamid64, record_type))
                keys.add((scope_id, course_id, target_steamid64, record_type))
    return keys


async def transfer_records(
    *,
    source_steamid64: int = DEFAULT_SOURCE_STEAMID64,
    target_steamid64: int = DEFAULT_TARGET_STEAMID64,
    audit_path: Path | None = None,
    after: str | None = None,
    before: str | None = None,
    dry_run: bool,
) -> RecordTransferResult:
    after_dt = parse_datetime_boundary(after)
    before_dt = parse_datetime_boundary(before, is_end=True)
    if after_dt is not None and before_dt is not None and after_dt > before_dt:
        raise ValueError("after must be earlier than or equal to before")
    resolved_audit_path = audit_path or default_audit_path()
    if dry_run:
        resolved_audit_path = resolved_audit_path.with_name(
            f"{resolved_audit_path.stem}.dry-run{resolved_audit_path.suffix}"
        )

    async with async_session_maker() as session:
        await _ensure_player_exists(session=session, steamid64=source_steamid64)
        await _ensure_player_exists(session=session, steamid64=target_steamid64)
        await _ensure_target_not_mirrored_banned(
            session=session,
            target_steamid64=target_steamid64,
        )

        source_records_before = await _count_records(
            session=session,
            steamid64=source_steamid64,
        )
        target_records_before = await _count_records(
            session=session,
            steamid64=target_steamid64,
        )
        records = await _load_source_records(
            session=session,
            source_steamid64=source_steamid64,
            after=after_dt,
            before=before_dt,
        )
        if not records:
            raise RuntimeError(f"No source records found for {source_steamid64}")

        await crud.ensure_map_courses_for_valid_records(session=session)
        course_ids_by_record_key = await _load_course_ids_by_record_key(
            session=session,
            records=records,
        )
        pb_keys = _pb_keys_for_records(
            records=records,
            course_ids_by_record_key=course_ids_by_record_key,
            source_steamid64=source_steamid64,
            target_steamid64=target_steamid64,
        )

        summary_path, checksum = _write_audit_files(
            audit_path=resolved_audit_path,
            records=records,
            source_steamid64=source_steamid64,
            target_steamid64=target_steamid64,
            dry_run=dry_run,
        )

        if dry_run:
            source_records_after = source_records_before
            target_records_after = target_records_before
            source_record_pb_after = await _count_record_pbs(
                session=session,
                steamid64=source_steamid64,
            )
            await session.rollback()
            return RecordTransferResult(
                source_steamid64=source_steamid64,
                target_steamid64=target_steamid64,
                dry_run=True,
                audit_path=resolved_audit_path,
                summary_path=summary_path,
                source_records_before=source_records_before,
                target_records_before=target_records_before,
                source_records_after=source_records_after,
                target_records_after=target_records_after,
                transferred_records=len(records),
                touched_pb_keys=len(pb_keys),
                touched_courses=len(
                    {
                        (scope_id, course_id, record_type)
                        for scope_id, course_id, _steamid64, record_type in pb_keys
                    }
                ),
                source_record_pb_after=source_record_pb_after,
                leaderboard_created=0,
                leaderboard_updated=0,
                player_stats_deleted=0,
                checksum=checksum,
                rating_rows_selected=0,
                rating_rows_created=0,
                rating_rows_updated=0,
            )

        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
            params={
                "lock_key": (
                    "record-transfer:"
                    f"{source_steamid64}:"
                    f"{target_steamid64}"
                )
            },
        )
        updated_result = await session.exec(
            update(Record)
            .where(
                col(Record.uuid).in_([record.uuid for record in records])
            )
            .values(steamid64=target_steamid64)
        )
        transferred_records = int(updated_result.rowcount or 0)
        if transferred_records != len(records):
            raise RuntimeError(
                "Transfer row count mismatch: "
                f"updated={transferred_records} expected={len(records)}"
            )

        await recompute_record_pbs_for_keys(session=session, keys=pb_keys)

        leaderboard_keys = [
            (mode_scope_to_id(scope), steamid64)
            for scope in ModeScope
            for steamid64 in (source_steamid64, target_steamid64)
        ]
        leaderboard_created, leaderboard_updated = (
            await crud.rebuild_leaderboard_players_for_keys(
                session=session,
                keys=leaderboard_keys,
            )
        )

        deleted_stats = await session.exec(
            delete(PlayerStatCache).where(
                col(PlayerStatCache.steamid64).in_(
                    [source_steamid64, target_steamid64]
                )
            )
        )
        player_stats_deleted = int(deleted_stats.rowcount or 0)

        source_records_after = await _count_records(
            session=session,
            steamid64=source_steamid64,
        )
        target_records_after = await _count_records(
            session=session,
            steamid64=target_steamid64,
        )
        source_record_pb_after = await _count_record_pbs(
            session=session,
            steamid64=source_steamid64,
        )
        if source_records_after != source_records_before - transferred_records:
            raise RuntimeError(
                "Source record count mismatch after transfer: "
                f"after={source_records_after} expected={source_records_before - transferred_records}"
            )
        minimum_target_records_after = target_records_before + transferred_records
        if target_records_after < minimum_target_records_after:
            raise RuntimeError(
                "Target record count mismatch after transfer: "
                f"after={target_records_after} minimum={minimum_target_records_after}"
            )
        await session.commit()

    rating_result = await rating_task.rebuild_ratings(
        scope_ids=[mode_scope_to_id(scope) for scope in ModeScope],
        scopes=None,
        steamid64s=[source_steamid64, target_steamid64],
        limit=None,
        full=False,
    )

    return RecordTransferResult(
        source_steamid64=source_steamid64,
        target_steamid64=target_steamid64,
        dry_run=False,
        audit_path=resolved_audit_path,
        summary_path=summary_path,
        source_records_before=source_records_before,
        target_records_before=target_records_before,
        source_records_after=source_records_after,
        target_records_after=target_records_after,
        transferred_records=transferred_records,
        touched_pb_keys=len(pb_keys),
        touched_courses=len(
            {
                (scope_id, course_id, record_type)
                for scope_id, course_id, _steamid64, record_type in pb_keys
            }
        ),
        source_record_pb_after=source_record_pb_after,
        leaderboard_created=leaderboard_created,
        leaderboard_updated=leaderboard_updated,
        player_stats_deleted=player_stats_deleted,
        checksum=checksum,
        rating_rows_selected=rating_result.leaderboard.selected,
        rating_rows_created=rating_result.leaderboard.created,
        rating_rows_updated=rating_result.leaderboard.updated,
    )
