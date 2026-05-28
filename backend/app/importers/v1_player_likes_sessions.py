import argparse
import asyncio
import gzip
import hashlib
import logging
import uuid
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, TextIO

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import async_session_maker
from app.models import Player, PlayerLike, PlayerSession, ServerGroup, ServerGroupStatus
from app.models.player import validate_player_custom_id

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 5_000


@dataclass(frozen=True, slots=True)
class V1PlayerRow:
    steamid64: int
    name: str
    created_at: datetime | None
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class V1ServerGroupRow:
    id: uuid.UUID
    name: str
    owner_steamid64: int | None
    website: str | None
    discord: str | None
    steam_group: str | None
    custom_id: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class V1PlayerLikeRow:
    viewer_steamid64: int
    target_steamid64: int
    like_date: date
    created_at: datetime


@dataclass(frozen=True, slots=True)
class V1PlayerSessionRow:
    source_id: uuid.UUID
    player_steamid64: int
    source_server_group_id: uuid.UUID
    connected_at: datetime
    disconnect_at: datetime | None
    ip_address: str
    map_name: str


@dataclass(frozen=True, slots=True)
class ServerGroupResolution:
    group_id_map: dict[uuid.UUID, uuid.UUID]
    groups_to_create: list[V1ServerGroupRow]


@dataclass(frozen=True, slots=True)
class V1PlayerLikesSessionsImportSummary:
    source_players: int
    source_server_groups: int
    source_likes: int
    source_sessions: int
    skipped_self_likes: int
    distinct_session_groups: int
    groups_mapped_by_existing_id: int
    groups_mapped_by_name_or_custom_id: int
    groups_created: int
    placeholder_players: int
    imported_likes: int
    imported_sessions: int
    clamped_sessions: int
    dry_run: bool
    verified: bool
    digest: str


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Import gokz-top v1 player likes and sessions from a SQL dump.",
    )
    parser.add_argument(
        "--dump",
        type=Path,
        required=True,
        help="Path to the gokz-top v1 PostgreSQL .sql or .sql.gz dump.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help="Rows to insert/upsert per batch.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and preflight the import without writing rows.",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify imported target row counts after writing.",
    )
    return parser


def _chunked[T](items: Sequence[T], *, size: int) -> Iterator[Sequence[T]]:
    if size < 1:
        raise ValueError("chunk size must be at least 1")
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _open_dump(path: Path) -> TextIO:
    if path.suffix == ".gz":
        return gzip.open(path, mode="rt", encoding="utf-8", newline="")
    return path.open(mode="r", encoding="utf-8", newline="")


def _parse_copy_columns(header: str, *, table: str) -> list[str]:
    prefix = f"COPY public.{table} ("
    if not header.startswith(prefix):
        raise ValueError(f"{table} COPY header has an unexpected format")
    column_end = header.find(") FROM stdin;")
    if column_end == -1:
        raise ValueError(f"{table} COPY header is missing FROM stdin terminator")
    return [column.strip().strip('"') for column in header[len(prefix) : column_end].split(",")]


def _unescape_copy_text(value: str) -> str:
    result: list[str] = []
    index = 0
    while index < len(value):
        char = value[index]
        if char != "\\":
            result.append(char)
            index += 1
            continue

        index += 1
        if index >= len(value):
            result.append("\\")
            break

        escaped = value[index]
        index += 1
        mapped = {
            "b": "\b",
            "f": "\f",
            "n": "\n",
            "r": "\r",
            "t": "\t",
            "v": "\v",
            "\\": "\\",
        }.get(escaped)
        result.append(mapped if mapped is not None else escaped)
    return "".join(result)


def _split_copy_line(line: str) -> list[str | None]:
    return [
        None if value == r"\N" else _unescape_copy_text(value)
        for value in line.rstrip("\n").split("\t")
    ]


def iter_copy_dict_rows(path: Path, *, table: str) -> Iterator[dict[str, str | None]]:
    with _open_dump(path) as stream:
        in_copy = False
        columns: list[str] = []
        for line in stream:
            if not in_copy:
                if line.startswith(f"COPY public.{table} ("):
                    columns = _parse_copy_columns(line.strip(), table=table)
                    in_copy = True
                continue

            if line == "\\.\n" or line.strip() == r"\.":
                return

            values = _split_copy_line(line)
            if len(values) != len(columns):
                raise ValueError(
                    f"{table} COPY row expected {len(columns)} fields, got {len(values)}"
                )
            yield dict(zip(columns, values, strict=True))


def _normalize_datetime(raw_value: str | None, *, field_name: str) -> datetime:
    if raw_value is None or not raw_value.strip():
        raise ValueError(f"{field_name} must not be blank")
    parsed = datetime.fromisoformat(raw_value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _normalize_optional_datetime(raw_value: str | None) -> datetime | None:
    if raw_value is None or not raw_value.strip():
        return None
    return _normalize_datetime(raw_value, field_name="datetime")


def _normalize_int(raw_value: str | None, *, field_name: str) -> int:
    if raw_value is None or not raw_value.strip():
        raise ValueError(f"{field_name} must not be blank")
    return int(raw_value.strip())


def _normalize_optional_int(raw_value: str | None, *, field_name: str) -> int | None:
    if raw_value is None or not raw_value.strip():
        return None
    return _normalize_int(raw_value, field_name=field_name)


def _normalize_text(raw_value: str | None, *, field_name: str) -> str:
    if raw_value is None or not raw_value.strip():
        raise ValueError(f"{field_name} must not be blank")
    return raw_value.strip()


def _normalize_optional_text(raw_value: str | None, *, max_length: int) -> str | None:
    if raw_value is None:
        return None
    normalized = raw_value.strip()
    if not normalized:
        return None
    return normalized[:max_length]


def _sanitize_custom_id(raw_value: str | None) -> str | None:
    if raw_value is None:
        return None
    try:
        return validate_player_custom_id(raw_value)
    except ValueError:
        return None


def _stable_uuid7_from_source(
    *,
    source_id: uuid.UUID,
    timestamp: datetime,
) -> uuid.UUID:
    normalized = timestamp.astimezone(UTC) if timestamp.tzinfo else timestamp.replace(
        tzinfo=UTC
    )
    unix_ts_ms = int(normalized.timestamp() * 1000)
    if unix_ts_ms < 0 or unix_ts_ms >= 1 << 48:
        raise ValueError("UUIDv7 timestamp must fit in 48 bits")

    digest = hashlib.sha256(b"gokz-top-v1-player-session:" + source_id.bytes).digest()
    random_bits = int.from_bytes(digest[:10], "big") & ((1 << 74) - 1)
    rand_a = random_bits >> 62
    rand_b = random_bits & ((1 << 62) - 1)
    value = (
        (unix_ts_ms << 80)
        | (0x7 << 76)
        | (rand_a << 64)
        | (0b10 << 62)
        | rand_b
    )
    return uuid.UUID(int=value)


def _normalize_session_timestamps(
    *,
    connected_at: datetime,
    disconnect_at: datetime | None,
) -> tuple[datetime | None, datetime, bool]:
    if disconnect_at is None:
        return None, connected_at, False
    if disconnect_at < connected_at:
        return connected_at, connected_at, True
    return disconnect_at, disconnect_at, False


def read_v1_player_rows(path: Path) -> dict[int, V1PlayerRow]:
    rows: dict[int, V1PlayerRow] = {}
    for row in iter_copy_dict_rows(path, table="player"):
        steamid64 = _normalize_int(row.get("steamid64"), field_name="steamid64")
        raw_name = row.get("name")
        name = raw_name.strip()[:255] if raw_name is not None and raw_name.strip() else str(
            steamid64
        )
        rows[steamid64] = V1PlayerRow(
            steamid64=steamid64,
            name=name,
            created_at=_normalize_optional_datetime(row.get("created_at")),
            updated_at=_normalize_optional_datetime(row.get("updated_at")),
        )
    return rows


def read_v1_server_group_rows(path: Path) -> dict[uuid.UUID, V1ServerGroupRow]:
    rows: dict[uuid.UUID, V1ServerGroupRow] = {}
    for row in iter_copy_dict_rows(path, table="server_groups"):
        group_id = uuid.UUID(_normalize_text(row.get("id"), field_name="id"))
        rows[group_id] = V1ServerGroupRow(
            id=group_id,
            name=_normalize_text(row.get("name"), field_name="name")[:255],
            owner_steamid64=_normalize_optional_int(
                row.get("owner_id"),
                field_name="owner_id",
            ),
            website=_normalize_optional_text(row.get("website"), max_length=255),
            discord=_normalize_optional_text(row.get("discord"), max_length=255),
            steam_group=_normalize_optional_text(row.get("steam_group"), max_length=255),
            custom_id=_sanitize_custom_id(row.get("custom_id")),
            created_at=_normalize_datetime(row.get("created_at"), field_name="created_at"),
            updated_at=_normalize_datetime(row.get("updated_at"), field_name="updated_at"),
        )
    return rows


def read_v1_player_like_rows(path: Path) -> list[V1PlayerLikeRow]:
    rows: list[V1PlayerLikeRow] = []
    for row in iter_copy_dict_rows(path, table="player_likes"):
        rows.append(
            V1PlayerLikeRow(
                viewer_steamid64=_normalize_int(
                    row.get("liker_steamid64"),
                    field_name="liker_steamid64",
                ),
                target_steamid64=_normalize_int(
                    row.get("liked_steamid64"),
                    field_name="liked_steamid64",
                ),
                like_date=date.fromisoformat(
                    _normalize_text(row.get("like_date"), field_name="like_date")
                ),
                created_at=_normalize_datetime(
                    row.get("created_at"),
                    field_name="created_at",
                ),
            )
        )
    return rows


def read_v1_player_session_rows(path: Path) -> list[V1PlayerSessionRow]:
    rows: list[V1PlayerSessionRow] = []
    for row in iter_copy_dict_rows(path, table="player_sessions"):
        rows.append(
            V1PlayerSessionRow(
                source_id=uuid.UUID(_normalize_text(row.get("id"), field_name="id")),
                player_steamid64=_normalize_int(
                    row.get("player_steamid64"),
                    field_name="player_steamid64",
                ),
                source_server_group_id=uuid.UUID(
                    _normalize_text(row.get("server_group_id"), field_name="server_group_id")
                ),
                connected_at=_normalize_datetime(
                    row.get("connected_time"),
                    field_name="connected_time",
                ),
                disconnect_at=_normalize_optional_datetime(row.get("disconnect_time")),
                ip_address=_normalize_text(row.get("ip_address"), field_name="ip_address"),
                map_name=_normalize_text(row.get("map_name"), field_name="map_name")[:255],
            )
        )
    return rows


def _digest_source_rows(
    *,
    likes: Sequence[V1PlayerLikeRow],
    sessions: Sequence[V1PlayerSessionRow],
) -> str:
    digest = hashlib.sha256()
    for like in likes:
        digest.update(
            "\t".join(
                [
                    str(like.viewer_steamid64),
                    str(like.target_steamid64),
                    like.like_date.isoformat(),
                    like.created_at.isoformat(),
                ]
            ).encode()
        )
        digest.update(b"\n")
    for player_session in sessions:
        digest.update(
            "\t".join(
                [
                    str(player_session.source_id),
                    str(player_session.player_steamid64),
                    str(player_session.source_server_group_id),
                    player_session.connected_at.isoformat(),
                    player_session.disconnect_at.isoformat()
                    if player_session.disconnect_at
                    else "",
                    player_session.ip_address,
                    player_session.map_name,
                ]
            ).encode()
        )
        digest.update(b"\n")
    return digest.hexdigest()


async def _insert_placeholder_players(
    *,
    session: AsyncSession,
    player_ids: set[int],
    source_players: dict[int, V1PlayerRow],
    batch_size: int,
) -> int:
    if not player_ids:
        return 0

    existing_player_ids = set(
        (
            await session.exec(
                select(Player.steamid64).where(col(Player.steamid64).in_(player_ids))
            )
        ).all()
    )
    missing_player_ids = player_ids - existing_player_ids
    if not missing_player_ids:
        return 0

    now = datetime.now(UTC)
    rows: list[dict[str, Any]] = []
    for steamid64 in sorted(missing_player_ids):
        source_player = source_players.get(steamid64)
        rows.append(
            {
                "steamid64": steamid64,
                "name": source_player.name if source_player is not None else str(steamid64),
                "created_at": (
                    source_player.created_at
                    if source_player is not None and source_player.created_at is not None
                    else now
                ),
                "updated_at": (
                    source_player.updated_at
                    if source_player is not None and source_player.updated_at is not None
                    else now
                ),
            }
        )

    for chunk in _chunked(rows, size=batch_size):
        statement = (
            pg_insert(Player.__table__)
            .values(list(chunk))
            .on_conflict_do_nothing(index_elements=[Player.__table__.c.steamid64])
        )
        await session.exec(statement)
    return len(rows)


async def _resolve_server_groups(
    *,
    session: AsyncSession,
    session_group_ids: set[uuid.UUID],
    source_groups: dict[uuid.UUID, V1ServerGroupRow],
) -> ServerGroupResolution:
    if not session_group_ids:
        return ServerGroupResolution(group_id_map={}, groups_to_create=[])

    missing_source_group_ids = session_group_ids - set(source_groups)
    if missing_source_group_ids:
        missing = ", ".join(str(group_id) for group_id in sorted(missing_source_group_ids))
        raise ValueError(f"player_sessions references missing v1 server_groups: {missing}")

    existing_groups = list((await session.exec(select(ServerGroup))).all())
    existing_by_id = {group.id: group for group in existing_groups}
    existing_by_custom_id: dict[str, list[ServerGroup]] = {}
    existing_by_lower_name: dict[str, list[ServerGroup]] = {}
    existing_api_keys = {group.api_key: group for group in existing_groups}
    for group in existing_groups:
        if group.custom_id is not None:
            existing_by_custom_id.setdefault(group.custom_id, []).append(group)
        existing_by_lower_name.setdefault(group.name.lower(), []).append(group)

    group_id_map: dict[uuid.UUID, uuid.UUID] = {}
    groups_to_create: list[V1ServerGroupRow] = []
    planned_names: set[str] = {group.name.lower() for group in existing_groups}
    planned_custom_ids: set[str] = {
        group.custom_id for group in existing_groups if group.custom_id is not None
    }
    planned_api_keys: set[str] = {group.api_key for group in existing_groups}

    for source_group_id in sorted(session_group_ids, key=str):
        source_group = source_groups[source_group_id]
        if source_group_id in existing_by_id:
            group_id_map[source_group_id] = source_group_id
            continue

        matches: dict[uuid.UUID, ServerGroup] = {}
        if source_group.custom_id is not None:
            for group in existing_by_custom_id.get(source_group.custom_id, []):
                matches[group.id] = group
        for group in existing_by_lower_name.get(source_group.name.lower(), []):
            matches[group.id] = group

        if len(matches) > 1:
            labels = ", ".join(f"{group.name} ({group.id})" for group in matches.values())
            raise ValueError(
                f"v1 server group {source_group.name} ({source_group.id}) "
                f"matches multiple v2 groups: {labels}"
            )
        if len(matches) == 1:
            matched_group = next(iter(matches.values()))
            group_id_map[source_group_id] = matched_group.id
            continue

        api_key = str(source_group.id)
        if source_group.name.lower() in planned_names:
            raise ValueError(
                f"v1 server group {source_group.name} ({source_group.id}) "
                "would conflict with an existing v2 server_group name"
            )
        if source_group.custom_id is not None and source_group.custom_id in planned_custom_ids:
            raise ValueError(
                f"v1 server group {source_group.name} ({source_group.id}) "
                "would conflict with an existing v2 server_group custom_id"
            )
        if api_key in planned_api_keys and existing_api_keys.get(api_key, None) is not None:
            raise ValueError(
                f"v1 server group {source_group.name} ({source_group.id}) "
                "would conflict with an existing v2 server_group api_key"
            )

        planned_names.add(source_group.name.lower())
        planned_api_keys.add(api_key)
        if source_group.custom_id is not None:
            planned_custom_ids.add(source_group.custom_id)
        groups_to_create.append(source_group)
        group_id_map[source_group_id] = source_group_id

    return ServerGroupResolution(
        group_id_map=group_id_map,
        groups_to_create=groups_to_create,
    )


async def _insert_server_groups(
    *,
    session: AsyncSession,
    groups: Sequence[V1ServerGroupRow],
) -> int:
    if not groups:
        return 0

    rows: list[dict[str, Any]] = []
    for group in groups:
        rows.append(
            {
                "id": group.id,
                "name": group.name,
                "custom_id": group.custom_id,
                "website": group.website,
                "discord": group.discord,
                "steam_group": group.steam_group,
                "api_key": str(group.id),
                "owner_steamid64": group.owner_steamid64,
                "status": ServerGroupStatus.PENDING,
                "created_at": group.created_at,
                "updated_at": group.updated_at,
            }
        )

    statement = (
        pg_insert(ServerGroup.__table__)
        .values(rows)
        .on_conflict_do_nothing(index_elements=[ServerGroup.__table__.c.id])
    )
    await session.exec(statement)
    return len(rows)


async def _import_player_likes(
    *,
    session: AsyncSession,
    likes: Sequence[V1PlayerLikeRow],
    batch_size: int,
) -> tuple[int, int]:
    rows: dict[tuple[int, int, date], dict[str, Any]] = {}
    skipped_self_likes = 0
    for like in likes:
        if like.viewer_steamid64 == like.target_steamid64:
            skipped_self_likes += 1
            continue
        key = (like.viewer_steamid64, like.target_steamid64, like.like_date)
        existing = rows.get(key)
        if existing is None or like.created_at < existing["created_at"]:
            rows[key] = {
                "viewer_steamid64": like.viewer_steamid64,
                "target_steamid64": like.target_steamid64,
                "like_date": like.like_date,
                "created_at": like.created_at,
            }

    for chunk in _chunked(list(rows.values()), size=batch_size):
        statement = (
            pg_insert(PlayerLike.__table__)
            .values(list(chunk))
            .on_conflict_do_nothing(
                index_elements=[
                    PlayerLike.__table__.c.viewer_steamid64,
                    PlayerLike.__table__.c.target_steamid64,
                    PlayerLike.__table__.c.like_date,
                ]
            )
        )
        await session.exec(statement)
    return len(rows), skipped_self_likes


def _build_player_session_rows(
    *,
    sessions: Sequence[V1PlayerSessionRow],
    group_id_map: dict[uuid.UUID, uuid.UUID],
) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    clamped_sessions = 0
    for player_session in sessions:
        disconnect_at, last_heartbeat_at, was_clamped = _normalize_session_timestamps(
            connected_at=player_session.connected_at,
            disconnect_at=player_session.disconnect_at,
        )
        if was_clamped:
            clamped_sessions += 1
        rows.append(
            {
                "id": _stable_uuid7_from_source(
                    source_id=player_session.source_id,
                    timestamp=player_session.connected_at,
                ),
                "player_steamid64": player_session.player_steamid64,
                "server_group_id": group_id_map[player_session.source_server_group_id],
                "connected_at": player_session.connected_at,
                "disconnect_at": disconnect_at,
                "last_heartbeat_at": last_heartbeat_at,
                "ip_address": player_session.ip_address,
                "map_name": player_session.map_name,
            }
        )
    return rows, clamped_sessions


async def _import_player_sessions(
    *,
    session: AsyncSession,
    sessions: Sequence[V1PlayerSessionRow],
    group_id_map: dict[uuid.UUID, uuid.UUID],
    batch_size: int,
) -> tuple[int, int]:
    rows, clamped_sessions = _build_player_session_rows(
        sessions=sessions,
        group_id_map=group_id_map,
    )
    for chunk in _chunked(rows, size=batch_size):
        statement = pg_insert(PlayerSession.__table__).values(list(chunk))
        statement = statement.on_conflict_do_update(
            index_elements=[PlayerSession.__table__.c.id],
            set_={
                "player_steamid64": statement.excluded.player_steamid64,
                "server_group_id": statement.excluded.server_group_id,
                "connected_at": statement.excluded.connected_at,
                "disconnect_at": statement.excluded.disconnect_at,
                "last_heartbeat_at": statement.excluded.last_heartbeat_at,
                "ip_address": statement.excluded.ip_address,
                "map_name": statement.excluded.map_name,
            },
        )
        await session.exec(statement)
    return len(rows), clamped_sessions


async def _verify_import(
    *,
    session: AsyncSession,
    likes: Sequence[V1PlayerLikeRow],
    sessions: Sequence[V1PlayerSessionRow],
    group_id_map: dict[uuid.UUID, uuid.UUID],
) -> None:
    expected_like_keys = {
        (like.viewer_steamid64, like.target_steamid64, like.like_date)
        for like in likes
        if like.viewer_steamid64 != like.target_steamid64
    }
    if expected_like_keys:
        actual_like_count = int(
            (
                await session.exec(
                    select(func.count())
                    .select_from(PlayerLike)
                    .where(
                        col(PlayerLike.viewer_steamid64).in_(
                            {key[0] for key in expected_like_keys}
                        ),
                        col(PlayerLike.target_steamid64).in_(
                            {key[1] for key in expected_like_keys}
                        ),
                        col(PlayerLike.like_date).in_(
                            {key[2] for key in expected_like_keys}
                        ),
                    )
                )
            ).one()
        )
        if actual_like_count < len(expected_like_keys):
            raise ValueError(
                f"player_like verification failed: expected at least "
                f"{len(expected_like_keys)} rows, found {actual_like_count}"
            )

    expected_session_rows, _ = _build_player_session_rows(
        sessions=sessions,
        group_id_map=group_id_map,
    )
    if expected_session_rows:
        expected_ids = {row["id"] for row in expected_session_rows}
        actual_session_count = 0
        for chunk in _chunked(list(expected_ids), size=50_000):
            actual_session_count += int(
                (
                    await session.exec(
                        select(func.count())
                        .select_from(PlayerSession)
                        .where(col(PlayerSession.id).in_(chunk))
                    )
                ).one()
            )
        if actual_session_count != len(expected_ids):
            raise ValueError(
                f"player_session verification failed: expected {len(expected_ids)} "
                f"rows, found {actual_session_count}"
            )


async def import_v1_player_likes_sessions(
    *,
    session: AsyncSession,
    dump_path: Path,
    dry_run: bool,
    verify: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> V1PlayerLikesSessionsImportSummary:
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")
    if not dump_path.is_file():
        raise FileNotFoundError(dump_path)

    source_players = read_v1_player_rows(dump_path)
    source_groups = read_v1_server_group_rows(dump_path)
    source_likes = read_v1_player_like_rows(dump_path)
    source_sessions = read_v1_player_session_rows(dump_path)
    session_group_ids = {row.source_server_group_id for row in source_sessions}
    group_resolution = await _resolve_server_groups(
        session=session,
        session_group_ids=session_group_ids,
        source_groups=source_groups,
    )
    mapped_by_existing_id = sum(
        1
        for group_id in session_group_ids
        if group_resolution.group_id_map[group_id] == group_id
        and group_id not in {group.id for group in group_resolution.groups_to_create}
    )
    mapped_by_name_or_custom_id = len(session_group_ids) - mapped_by_existing_id - len(
        group_resolution.groups_to_create
    )

    unique_like_rows = {
        (row.viewer_steamid64, row.target_steamid64, row.like_date)
        for row in source_likes
        if row.viewer_steamid64 != row.target_steamid64
    }
    skipped_self_likes = sum(
        1 for row in source_likes if row.viewer_steamid64 == row.target_steamid64
    )
    _, clamped_sessions = _build_player_session_rows(
        sessions=source_sessions,
        group_id_map=group_resolution.group_id_map,
    )

    all_player_ids = {
        row.player_steamid64 for row in source_sessions
    } | {
        row.viewer_steamid64 for row in source_likes
    } | {
        row.target_steamid64 for row in source_likes
    } | {
        group.owner_steamid64
        for group in group_resolution.groups_to_create
        if group.owner_steamid64 is not None
    }

    if dry_run:
        return V1PlayerLikesSessionsImportSummary(
            source_players=len(source_players),
            source_server_groups=len(source_groups),
            source_likes=len(source_likes),
            source_sessions=len(source_sessions),
            skipped_self_likes=skipped_self_likes,
            distinct_session_groups=len(session_group_ids),
            groups_mapped_by_existing_id=mapped_by_existing_id,
            groups_mapped_by_name_or_custom_id=mapped_by_name_or_custom_id,
            groups_created=len(group_resolution.groups_to_create),
            placeholder_players=0,
            imported_likes=0,
            imported_sessions=0,
            clamped_sessions=clamped_sessions,
            dry_run=True,
            verified=False,
            digest=_digest_source_rows(likes=source_likes, sessions=source_sessions),
        )

    placeholder_players = await _insert_placeholder_players(
        session=session,
        player_ids={player_id for player_id in all_player_ids if player_id is not None},
        source_players=source_players,
        batch_size=batch_size,
    )
    groups_created = await _insert_server_groups(
        session=session,
        groups=group_resolution.groups_to_create,
    )
    imported_likes, skipped_self_likes = await _import_player_likes(
        session=session,
        likes=source_likes,
        batch_size=batch_size,
    )
    imported_sessions, clamped_sessions = await _import_player_sessions(
        session=session,
        sessions=source_sessions,
        group_id_map=group_resolution.group_id_map,
        batch_size=batch_size,
    )
    if verify:
        await _verify_import(
            session=session,
            likes=source_likes,
            sessions=source_sessions,
            group_id_map=group_resolution.group_id_map,
        )
    await session.commit()

    return V1PlayerLikesSessionsImportSummary(
        source_players=len(source_players),
        source_server_groups=len(source_groups),
        source_likes=len(source_likes),
        source_sessions=len(source_sessions),
        skipped_self_likes=skipped_self_likes,
        distinct_session_groups=len(session_group_ids),
        groups_mapped_by_existing_id=mapped_by_existing_id,
        groups_mapped_by_name_or_custom_id=mapped_by_name_or_custom_id,
        groups_created=groups_created,
        placeholder_players=placeholder_players,
        imported_likes=len(unique_like_rows),
        imported_sessions=imported_sessions,
        clamped_sessions=clamped_sessions,
        dry_run=False,
        verified=verify,
        digest=_digest_source_rows(likes=source_likes, sessions=source_sessions),
    )


def _log_summary(summary: V1PlayerLikesSessionsImportSummary) -> None:
    logger.info("v1 likes/sessions import dry_run=%s", summary.dry_run)
    logger.info("Source players: %s", summary.source_players)
    logger.info("Source server groups: %s", summary.source_server_groups)
    logger.info("Source likes: %s", summary.source_likes)
    logger.info("Source sessions: %s", summary.source_sessions)
    logger.info("Skipped self-likes: %s", summary.skipped_self_likes)
    logger.info("Distinct session groups: %s", summary.distinct_session_groups)
    logger.info("Groups mapped by existing id: %s", summary.groups_mapped_by_existing_id)
    logger.info(
        "Groups mapped by name/custom_id: %s",
        summary.groups_mapped_by_name_or_custom_id,
    )
    logger.info("Groups created: %s", summary.groups_created)
    logger.info("Placeholder players inserted: %s", summary.placeholder_players)
    logger.info("Imported likes: %s", summary.imported_likes)
    logger.info("Imported sessions: %s", summary.imported_sessions)
    logger.info("Clamped invalid session disconnects: %s", summary.clamped_sessions)
    logger.info("Verified: %s", summary.verified)
    logger.info("Source digest: %s", summary.digest)


async def _main_async(argv: list[str] | None = None) -> None:
    args = _build_parser().parse_args(argv)
    async with async_session_maker() as session:
        summary = await import_v1_player_likes_sessions(
            session=session,
            dump_path=args.dump.resolve(),
            dry_run=args.dry_run,
            verify=args.verify,
            batch_size=args.batch_size,
        )
    _log_summary(summary)


def main(argv: list[str] | None = None) -> None:
    asyncio.run(_main_async(argv))


if __name__ == "__main__":
    main()
