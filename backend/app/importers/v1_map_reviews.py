import argparse
import asyncio
import gzip
import hashlib
import json
import logging
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import col, select

from app.core.db import async_session_maker
from app.crud.map_review import rebuild_map_review_summary
from app.models import (
    Map,
    MapReview,
    MapReviewCommentInput,
    MapReviewContentInput,
    MapReviewSummaryCache,
    Player,
    generate_uuid7,
)
from app.services.language_detection import detect_language_code

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

COPY_HEADER = (
    "COPY public.map_review (steamid64, map_id, content, created_at, updated_at) "
    "FROM stdin;"
)
DEFAULT_BATCH_SIZE = 500


@dataclass(frozen=True, slots=True)
class LegacyMapReviewRow:
    steamid64: int
    map_id: int
    content: dict[str, Any]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class MapReviewImportResult:
    source_rows: int
    distinct_players: int
    distinct_maps: int
    missing_players: int
    missing_maps: int
    existing_website_reviews: int
    imported_rows: int
    summaries_rebuilt: int
    digest: str


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Import gokz-top v1 map reviews from a plain SQL gzip backup.",
    )
    parser.add_argument(
        "--source-sql-gz",
        type=Path,
        required=True,
        help="Path to the v1 .sql.gz backup.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Inspect source and database dependencies without writing rows.",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify target map_review rows match the normalized source rows.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help="Maximum review rows to upsert per statement.",
    )
    return parser


def _chunked[T](items: Sequence[T], *, size: int) -> Iterator[Sequence[T]]:
    if size < 1:
        raise ValueError("chunk size must be at least 1")
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _normalize_datetime(raw_value: str, *, field_name: str) -> datetime:
    normalized = raw_value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _normalize_int(raw_value: Any, *, field_name: str) -> int:
    try:
        return int(str(raw_value).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer") from exc


def _normalize_optional_int(raw_value: Any, *, field_name: str) -> int | None:
    if raw_value is None:
        return None
    normalized = str(raw_value).strip()
    if not normalized:
        return None
    return _normalize_int(normalized, field_name=field_name)


def _normalize_copy_escape(line: str) -> str:
    result: list[str] = []
    index = 0
    while index < len(line):
        char = line[index]
        if char != "\\":
            result.append(char)
            index += 1
            continue

        index += 1
        if index >= len(line):
            result.append("\\")
            break

        escaped = line[index]
        index += 1
        if escaped == "b":
            result.append("\b")
        elif escaped == "f":
            result.append("\f")
        elif escaped == "n":
            result.append("\n")
        elif escaped == "r":
            result.append("\r")
        elif escaped == "t":
            result.append("\t")
        elif escaped == "v":
            result.append("\v")
        elif escaped in "01234567":
            octal_digits = [escaped]
            while index < len(line) and len(octal_digits) < 3 and line[index] in "01234567":
                octal_digits.append(line[index])
                index += 1
            result.append(chr(int("".join(octal_digits), 8)))
        else:
            result.append(escaped)
    return "".join(result)


def _parse_copy_text_row(line: str, *, expected_fields: int = 5) -> list[str | None]:
    fields = line.rstrip("\n").split("\t")
    if len(fields) != expected_fields:
        raise ValueError(f"Expected {expected_fields} COPY fields, got {len(fields)}")
    return [None if field == r"\N" else _normalize_copy_escape(field) for field in fields]


def iter_legacy_map_review_copy_rows(source_sql_gz: Path) -> Iterator[list[str | None]]:
    in_copy = False
    with gzip.open(source_sql_gz, mode="rt", encoding="utf-8") as stream:
        for line in stream:
            stripped = line.rstrip("\n")
            if not in_copy:
                if stripped == COPY_HEADER:
                    in_copy = True
                continue
            if stripped == r"\.":
                return
            yield _parse_copy_text_row(line)

    if not in_copy:
        raise ValueError("Backup does not contain the public.map_review COPY block")
    raise ValueError("Backup ended before the public.map_review COPY block terminator")


def _normalize_comment_text(raw_comment: Any) -> str | None:
    if isinstance(raw_comment, dict):
        candidate = raw_comment.get("text")
    else:
        candidate = raw_comment
    if candidate is None:
        return None
    candidate_text = str(candidate)
    if len(candidate_text) > 1000:
        candidate_text = candidate_text[:1000]
    return MapReviewCommentInput(text=candidate_text).text


def normalize_legacy_map_review_content(
    *,
    raw_content: str,
    created_at: datetime,
    updated_at: datetime,
) -> dict[str, Any]:
    payload = json.loads(raw_content)
    if not isinstance(payload, dict):
        raise ValueError("map review content must be a JSON object")

    comment_text = _normalize_comment_text(payload.get("comment"))
    content_input = MapReviewContentInput(
        overall=_normalize_int(payload.get("overall"), field_name="overall"),
        gameplay=_normalize_optional_int(payload.get("gameplay"), field_name="gameplay"),
        visuals=_normalize_optional_int(payload.get("visuals"), field_name="visuals"),
        comment=MapReviewCommentInput(text=comment_text),
    )

    normalized: dict[str, Any] = {
        "overall": content_input.overall,
        "gameplay": content_input.gameplay,
        "visuals": content_input.visuals,
    }
    if content_input.comment is None or content_input.comment.text is None:
        normalized["comment"] = None
        return normalized

    language = payload.get("lang")
    if not isinstance(language, str) or not language.strip():
        language = detect_language_code(content_input.comment.text)
    normalized["comment"] = {
        "text": content_input.comment.text,
        "language": language,
        "created_at": created_at.isoformat(),
        "updated_at": updated_at.isoformat(),
    }
    return normalized


def read_legacy_map_review_rows(source_sql_gz: Path) -> list[LegacyMapReviewRow]:
    rows: list[LegacyMapReviewRow] = []
    for row in iter_legacy_map_review_copy_rows(source_sql_gz):
        steamid64_raw, map_id_raw, content_raw, created_at_raw, updated_at_raw = row
        if None in row:
            raise ValueError("public.map_review COPY rows must not contain NULL fields")
        assert steamid64_raw is not None
        assert map_id_raw is not None
        assert content_raw is not None
        assert created_at_raw is not None
        assert updated_at_raw is not None

        created_at = _normalize_datetime(created_at_raw, field_name="created_at")
        updated_at = _normalize_datetime(updated_at_raw, field_name="updated_at")
        rows.append(
            LegacyMapReviewRow(
                steamid64=_normalize_int(steamid64_raw, field_name="steamid64"),
                map_id=_normalize_int(map_id_raw, field_name="map_id"),
                content=normalize_legacy_map_review_content(
                    raw_content=content_raw,
                    created_at=created_at,
                    updated_at=updated_at,
                ),
                created_at=created_at,
                updated_at=updated_at,
            )
        )
    return rows


def _build_placeholder_player_rows(player_ids: set[int]) -> list[dict[str, Any]]:
    now = datetime.now(UTC)
    return [
        {
            "steamid64": steamid64,
            "name": str(steamid64),
            "created_at": now,
            "updated_at": now,
        }
        for steamid64 in sorted(player_ids)
    ]


def _build_review_insert_rows(rows: Sequence[LegacyMapReviewRow]) -> list[dict[str, Any]]:
    return [
        {
            "id": generate_uuid7(timestamp=row.updated_at),
            "steamid64": row.steamid64,
            "map_id": row.map_id,
            "server_group_id": None,
            "content": row.content,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
        for row in rows
    ]


def _canonical_review_payload(row: LegacyMapReviewRow) -> str:
    payload = {
        "steamid64": row.steamid64,
        "map_id": row.map_id,
        "content": row.content,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def compute_source_digest(rows: Sequence[LegacyMapReviewRow]) -> str:
    digest = hashlib.sha256()
    for row in sorted(rows, key=lambda item: (item.steamid64, item.map_id)):
        digest.update(_canonical_review_payload(row).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


async def _inspect_dependencies(
    *,
    rows: Sequence[LegacyMapReviewRow],
) -> tuple[set[int], set[int], int]:
    player_ids = {row.steamid64 for row in rows}
    map_ids = {row.map_id for row in rows}
    if not rows:
        return set(), set(), 0

    async with async_session_maker() as session:
        existing_player_ids = set(
            (await session.exec(select(Player.steamid64).where(col(Player.steamid64).in_(player_ids)))).all()
        )
        existing_map_ids = set(
            (await session.exec(select(Map.id).where(col(Map.id).in_(map_ids)))).all()
        )
        existing_reviews = (
            await session.exec(
                select(MapReview).where(
                    col(MapReview.server_group_id).is_(None),
                    col(MapReview.steamid64).in_(player_ids),
                    col(MapReview.map_id).in_(map_ids),
                )
            )
        ).all()

    source_contexts = {(row.steamid64, row.map_id) for row in rows}
    existing_website_reviews = sum(
        1
        for review in existing_reviews
        if (review.steamid64, review.map_id) in source_contexts
    )
    return player_ids - existing_player_ids, map_ids - existing_map_ids, existing_website_reviews


async def _insert_placeholder_players(*, player_ids: set[int]) -> int:
    if not player_ids:
        return 0

    rows = _build_placeholder_player_rows(player_ids)
    async with async_session_maker() as session:
        for chunk in _chunked(rows, size=1_000):
            statement = pg_insert(Player.__table__).values(list(chunk)).on_conflict_do_nothing(
                index_elements=[Player.__table__.c.steamid64]
            )
            await session.exec(statement)
        await session.commit()
    return len(rows)


async def _upsert_map_reviews(
    *,
    rows: Sequence[LegacyMapReviewRow],
    batch_size: int,
) -> tuple[int, int]:
    if not rows:
        return 0, 0

    insert_rows = _build_review_insert_rows(rows)
    touched_map_ids = {row.map_id for row in rows}
    review_table = MapReview.__table__  # type: ignore[attr-defined]

    async with async_session_maker() as session:
        for chunk in _chunked(insert_rows, size=batch_size):
            insert_statement = pg_insert(review_table).values(list(chunk))
            upsert_statement = insert_statement.on_conflict_do_update(
                constraint="uq_map_review_context",
                set_={
                    "content": insert_statement.excluded.content,
                    "created_at": insert_statement.excluded.created_at,
                    "updated_at": insert_statement.excluded.updated_at,
                },
            )
            await session.exec(upsert_statement)

        summaries_rebuilt = 0
        for map_id in sorted(touched_map_ids):
            await rebuild_map_review_summary(session=session, map_id=map_id)
            summaries_rebuilt += 1

        await session.commit()
    return len(insert_rows), summaries_rebuilt


async def verify_imported_map_reviews(
    *,
    rows: Sequence[LegacyMapReviewRow],
) -> None:
    if not rows:
        return

    source_by_context = {(row.steamid64, row.map_id): row for row in rows}
    player_ids = {row.steamid64 for row in rows}
    map_ids = {row.map_id for row in rows}

    async with async_session_maker() as session:
        target_rows = (
            await session.exec(
                select(MapReview).where(
                    col(MapReview.server_group_id).is_(None),
                    col(MapReview.steamid64).in_(player_ids),
                    col(MapReview.map_id).in_(map_ids),
                )
            )
        ).all()
        summary_count = (
            await session.exec(
                select(MapReviewSummaryCache).where(
                    col(MapReviewSummaryCache.map_id).in_({row.map_id for row in rows})
                )
            )
        ).all()

    target_by_context = {
        (row.steamid64, row.map_id): row
        for row in target_rows
        if (row.steamid64, row.map_id) in source_by_context
    }
    missing_contexts = sorted(set(source_by_context) - set(target_by_context))
    if missing_contexts:
        raise ValueError(f"Target is missing {len(missing_contexts)} imported review rows")

    mismatches: list[tuple[int, int]] = []
    for context, source in source_by_context.items():
        target = target_by_context[context]
        if (
            target.content != source.content
            or target.created_at != source.created_at
            or target.updated_at != source.updated_at
        ):
            mismatches.append(context)

    if mismatches:
        raise ValueError(f"Target has {len(mismatches)} mismatched imported review rows")
    if not summary_count:
        raise ValueError("Target has no map review summaries after import")


async def import_v1_map_reviews_from_sql_gz(
    *,
    source_sql_gz: Path,
    dry_run: bool = False,
    verify: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> MapReviewImportResult:
    if batch_size < 1:
        raise ValueError("batch size must be at least 1")
    if not source_sql_gz.is_file():
        raise FileNotFoundError(source_sql_gz)

    rows = read_legacy_map_review_rows(source_sql_gz)
    missing_players, missing_maps, existing_reviews = await _inspect_dependencies(rows=rows)
    digest = compute_source_digest(rows)

    result = MapReviewImportResult(
        source_rows=len(rows),
        distinct_players=len({row.steamid64 for row in rows}),
        distinct_maps=len({row.map_id for row in rows}),
        missing_players=len(missing_players),
        missing_maps=len(missing_maps),
        existing_website_reviews=existing_reviews,
        imported_rows=0,
        summaries_rebuilt=0,
        digest=digest,
    )
    if dry_run:
        return result
    if missing_maps:
        missing_ids = ", ".join(str(map_id) for map_id in sorted(missing_maps))
        raise ValueError(f"v1 map reviews reference missing map ids: {missing_ids}")

    await _insert_placeholder_players(player_ids=missing_players)
    imported_rows, summaries_rebuilt = await _upsert_map_reviews(
        rows=rows,
        batch_size=batch_size,
    )
    if verify:
        await verify_imported_map_reviews(rows=rows)

    return MapReviewImportResult(
        source_rows=result.source_rows,
        distinct_players=result.distinct_players,
        distinct_maps=result.distinct_maps,
        missing_players=result.missing_players,
        missing_maps=result.missing_maps,
        existing_website_reviews=result.existing_website_reviews,
        imported_rows=imported_rows,
        summaries_rebuilt=summaries_rebuilt,
        digest=digest,
    )


def _log_result(result: MapReviewImportResult) -> None:
    logger.info("Source rows: %s", result.source_rows)
    logger.info("Distinct players: %s", result.distinct_players)
    logger.info("Distinct maps: %s", result.distinct_maps)
    logger.info("Missing placeholder players needed: %s", result.missing_players)
    logger.info("Missing map ids: %s", result.missing_maps)
    logger.info("Existing website reviews to overwrite: %s", result.existing_website_reviews)
    logger.info("Imported rows: %s", result.imported_rows)
    logger.info("Summaries rebuilt: %s", result.summaries_rebuilt)
    logger.info("Source digest: %s", result.digest)


async def _main_async(argv: list[str] | None = None) -> None:
    args = _build_parser().parse_args(argv)
    result = await import_v1_map_reviews_from_sql_gz(
        source_sql_gz=args.source_sql_gz.resolve(),
        dry_run=args.dry_run,
        verify=args.verify,
        batch_size=args.batch_size,
    )
    _log_result(result)


def main(argv: list[str] | None = None) -> None:
    asyncio.run(_main_async(argv))


if __name__ == "__main__":
    main()
