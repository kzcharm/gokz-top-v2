import uuid
from datetime import datetime
from typing import Any

from psycopg.errors import InvalidSchemaName, UndefinedTable
from sqlalchemy import Integer, case, cast, delete, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.crud.player import to_player_ref_public
from app.models import (
    Map,
    MapCourse,
    MapRefPublic,
    MapReview,
    MapReviewContentInput,
    MapReviewContentPublic,
    MapReviewPublic,
    MapReviewSource,
    MapReviewSummaryCache,
    MapReviewSummaryPublic,
    ModeScope,
    Player,
    RecordPb,
    get_datetime_utc,
)
from app.services.language_detection import detect_language_code


def _is_missing_map_review_summary_cache_error(exc: ProgrammingError) -> bool:
    original = exc.orig
    return isinstance(original, (UndefinedTable, InvalidSchemaName))


def _parse_existing_comment(content: dict[str, Any]) -> dict[str, Any] | None:
    comment = content.get("comment")
    if not isinstance(comment, dict):
        return None
    return comment


def _normalize_comment_timestamp(value: Any, *, fallback: str) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str) and value:
        return value
    return fallback


def normalize_map_review_content(
    *,
    content_in: MapReviewContentInput,
    existing_content: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = get_datetime_utc()
    now_iso = now.isoformat()
    normalized: dict[str, Any] = {
        "overall": content_in.overall,
        "gameplay": content_in.gameplay,
        "visuals": content_in.visuals,
    }

    comment_text = content_in.comment.text if content_in.comment is not None else None
    if comment_text is None:
        normalized["comment"] = None
        return normalized

    existing_comment = _parse_existing_comment(existing_content or {})
    existing_text = (
        existing_comment.get("text") if isinstance(existing_comment.get("text"), str) else None
    ) if existing_comment is not None else None

    if existing_comment is not None and existing_text == comment_text:
        created_at = _normalize_comment_timestamp(
            existing_comment.get("created_at"),
            fallback=now_iso,
        )
        updated_at = _normalize_comment_timestamp(
            existing_comment.get("updated_at"),
            fallback=now_iso,
        )
    else:
        created_at = now_iso
        updated_at = now_iso

    normalized["comment"] = {
        "text": comment_text,
        "language": detect_language_code(comment_text),
        "created_at": created_at,
        "updated_at": updated_at,
    }
    return normalized


def to_map_review_public(
    *,
    review: MapReview,
    player: Player,
    map_obj: Map,
) -> MapReviewPublic:
    return MapReviewPublic(
        steamid64=str(review.steamid64),
        map_id=review.map_id,
        server_group_id=review.server_group_id,
        content=MapReviewContentPublic.model_validate(review.content),
        created_at=review.created_at,
        updated_at=review.updated_at,
        player=to_player_ref_public(player=player),
        map=MapRefPublic(id=map_obj.id, name=map_obj.name),
    )


def _map_review_order_by(review_table: Any) -> tuple[Any, Any, Any]:
    return (
        review_table.c.updated_at.desc(),
        review_table.c.created_at.desc(),
        review_table.c.id.desc(),
    )


def _latest_map_review_ids_query(
    *,
    map_id: int | None = None,
    steamid64: int | None = None,
    website_only: bool = False,
):
    review_table = MapReview.__table__  # type: ignore[attr-defined]
    ranked_reviews = (
        select(
            review_table.c.id.label("review_id"),
            func.row_number()
            .over(
                partition_by=(review_table.c.steamid64, review_table.c.map_id),
                order_by=_map_review_order_by(review_table),
            )
            .label("rank"),
        )
        .select_from(review_table)
    )
    if map_id is not None:
        ranked_reviews = ranked_reviews.where(review_table.c.map_id == map_id)
    if steamid64 is not None:
        ranked_reviews = ranked_reviews.where(review_table.c.steamid64 == steamid64)
    if website_only:
        ranked_reviews = ranked_reviews.where(review_table.c.server_group_id.is_(None))

    ranked_subquery = ranked_reviews.subquery()
    return select(ranked_subquery.c.review_id).where(ranked_subquery.c.rank == 1)


async def get_map_review_by_context(
    *,
    session: AsyncSession,
    steamid64: int,
    map_id: int,
    server_group_id: uuid.UUID | None,
) -> MapReview | None:
    statement = select(MapReview).where(
        col(MapReview.steamid64) == steamid64,
        col(MapReview.map_id) == map_id,
        col(MapReview.server_group_id) == server_group_id,
    )
    return (await session.exec(statement)).first()


async def has_finished_map_for_review(
    *,
    session: AsyncSession,
    steamid64: int,
    map_id: int,
) -> bool:
    statement = (
        select(RecordPb.record_uuid)
        .join(MapCourse, col(MapCourse.id) == col(RecordPb.course_id))
        .where(
            col(RecordPb.steamid64) == steamid64,
            col(RecordPb.scope) == ModeScope.OVR,
            col(MapCourse.map_id) == map_id,
            col(MapCourse.stage) == 0,
        )
        .limit(1)
    )
    return (await session.exec(statement)).first() is not None


def _to_map_review_summary_public(
    cache_row: MapReviewSummaryCache,
) -> MapReviewSummaryPublic:
    return MapReviewSummaryPublic(
        overall_avg=cache_row.overall_avg,
        gameplay_avg=cache_row.gameplay_avg,
        visuals_avg=cache_row.visuals_avg,
        reviews_count=cache_row.reviews_count,
        gameplay_count=cache_row.gameplay_count,
        visuals_count=cache_row.visuals_count,
        comments_count=cache_row.comments_count,
        updated_at=cache_row.updated_at,
    )


async def load_map_review_summaries(
    *,
    session: AsyncSession,
    map_ids: list[int],
) -> dict[int, MapReviewSummaryPublic]:
    if not map_ids:
        return {}

    statement = select(MapReviewSummaryCache).where(col(MapReviewSummaryCache.map_id).in_(map_ids))
    try:
        rows = list((await session.exec(statement)).all())
    except ProgrammingError as exc:
        if _is_missing_map_review_summary_cache_error(exc):
            return {}
        raise
    return {row.map_id: _to_map_review_summary_public(row) for row in rows}


async def rebuild_map_review_summary(
    *,
    session: AsyncSession,
    map_id: int,
) -> MapReviewSummaryPublic | None:
    latest_ids = _latest_map_review_ids_query(map_id=map_id).subquery()
    review_table = MapReview.__table__  # type: ignore[attr-defined]

    overall_rating = cast(review_table.c.content["overall"].astext, Integer)
    gameplay_rating = cast(review_table.c.content["gameplay"].astext, Integer)
    visuals_rating = cast(review_table.c.content["visuals"].astext, Integer)
    comment_text = review_table.c.content["comment"]["text"].astext

    summary_statement = (
        select(
            func.count().label("reviews_count"),
            func.avg(overall_rating).label("overall_avg"),
            func.avg(gameplay_rating).label("gameplay_avg"),
            func.avg(visuals_rating).label("visuals_avg"),
            func.count(gameplay_rating).label("gameplay_count"),
            func.count(visuals_rating).label("visuals_count"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            comment_text.is_not(None) & (comment_text != ""),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("comments_count"),
        )
        .select_from(latest_ids)
        .join(review_table, review_table.c.id == latest_ids.c.review_id)
    )
    summary = (await session.exec(summary_statement)).one()
    reviews_count = int(summary.reviews_count or 0)

    if reviews_count == 0:
        try:
            await session.exec(
                delete(MapReviewSummaryCache).where(col(MapReviewSummaryCache.map_id) == map_id)
            )
            await session.commit()
        except ProgrammingError as exc:
            if _is_missing_map_review_summary_cache_error(exc):
                await session.rollback()
                return None
            raise
        return None

    now = get_datetime_utc()
    cache_table = MapReviewSummaryCache.__table__  # type: ignore[attr-defined]
    values = {
        "map_id": map_id,
        "overall_avg": float(summary.overall_avg),
        "gameplay_avg": (
            float(summary.gameplay_avg) if summary.gameplay_avg is not None else None
        ),
        "visuals_avg": (
            float(summary.visuals_avg) if summary.visuals_avg is not None else None
        ),
        "reviews_count": reviews_count,
        "gameplay_count": int(summary.gameplay_count or 0),
        "visuals_count": int(summary.visuals_count or 0),
        "comments_count": int(summary.comments_count or 0),
        "updated_at": now,
    }
    insert_statement = pg_insert(cache_table).values(values)
    upsert_statement = insert_statement.on_conflict_do_update(
        index_elements=[cache_table.c.map_id],
        set_={
            "overall_avg": insert_statement.excluded.overall_avg,
            "gameplay_avg": insert_statement.excluded.gameplay_avg,
            "visuals_avg": insert_statement.excluded.visuals_avg,
            "reviews_count": insert_statement.excluded.reviews_count,
            "gameplay_count": insert_statement.excluded.gameplay_count,
            "visuals_count": insert_statement.excluded.visuals_count,
            "comments_count": insert_statement.excluded.comments_count,
            "updated_at": insert_statement.excluded.updated_at,
        },
    )
    try:
        await session.exec(upsert_statement)
        await session.commit()
    except ProgrammingError as exc:
        if _is_missing_map_review_summary_cache_error(exc):
            await session.rollback()
            return None
        raise

    cache_row = await session.get(MapReviewSummaryCache, map_id)
    assert cache_row is not None
    return _to_map_review_summary_public(cache_row)


async def upsert_map_review(
    *,
    session: AsyncSession,
    steamid64: int,
    map_id: int,
    server_group_id: uuid.UUID | None,
    content_in: MapReviewContentInput,
) -> tuple[MapReview, Player, Map]:
    existing = await get_map_review_by_context(
        session=session,
        steamid64=steamid64,
        map_id=map_id,
        server_group_id=server_group_id,
    )
    now = get_datetime_utc()
    content = normalize_map_review_content(
        content_in=content_in,
        existing_content=existing.content if existing is not None else None,
    )

    review_table = MapReview.__table__  # type: ignore[attr-defined]
    values: dict[str, Any] = {
        "id": uuid.uuid7(),
        "steamid64": steamid64,
        "map_id": map_id,
        "server_group_id": server_group_id,
        "content": content,
        "created_at": now,
        "updated_at": now,
    }

    insert_statement = pg_insert(review_table).values(values)
    upsert_statement = insert_statement.on_conflict_do_update(
        constraint="uq_map_review_context",
        set_={
            "content": insert_statement.excluded.content,
            "updated_at": insert_statement.excluded.updated_at,
        },
    )
    await session.exec(upsert_statement)
    await session.commit()

    review = await get_map_review_by_context(
        session=session,
        steamid64=steamid64,
        map_id=map_id,
        server_group_id=server_group_id,
    )
    assert review is not None

    statement = (
        select(Player, Map)
        .select_from(Player)
        .join(Map, col(Map.id) == review.map_id)
        .where(col(Player.steamid64) == review.steamid64)
    )
    player, map_obj = (await session.exec(statement)).one()
    return review, player, map_obj


async def read_latest_map_reviews(
    *,
    session: AsyncSession,
    offset: int,
    limit: int,
    map_id: int | None = None,
    steamid64: int | None = None,
    with_comments_only: bool = False,
    language: str | None = None,
    source: MapReviewSource = "latest",
) -> tuple[list[tuple[MapReview, Player, Map]], int]:
    review_table = MapReview.__table__  # type: ignore[attr-defined]
    latest_ids = _latest_map_review_ids_query(
        map_id=map_id,
        steamid64=steamid64,
        website_only=source == "website",
    ).subquery()
    filters: list[ColumnElement[bool]] = []
    comment_text = review_table.c.content["comment"]["text"].astext
    comment_language = review_table.c.content["comment"]["language"].astext

    if with_comments_only or language is not None:
        filters.extend(
            [
                comment_text.is_not(None),
                comment_text != "",
            ],
        )
    if language is not None:
        filters.append(comment_language == language)

    count_statement = (
        select(func.count())
        .select_from(latest_ids)
        .join(review_table, latest_ids.c.review_id == review_table.c.id)
    )
    statement = (
        select(MapReview, Player, Map)
        .select_from(MapReview)
        .join(latest_ids, latest_ids.c.review_id == col(MapReview.id))
        .join(Player, col(Player.steamid64) == col(MapReview.steamid64))
        .join(Map, col(Map.id) == col(MapReview.map_id))
        .order_by(*_map_review_order_by(review_table))
        .offset(offset)
        .limit(limit)
    )

    for condition in filters:
        count_statement = count_statement.where(condition)
        statement = statement.where(condition)

    count = (await session.exec(count_statement)).one()
    rows = list((await session.exec(statement)).all())
    return rows, count


async def clear_map_review_comments(
    *,
    session: AsyncSession,
    steamid64: int,
    map_id: int,
) -> tuple[MapReview, Player, Map, list[str]] | None:
    statement = (
        select(MapReview)
        .where(
            col(MapReview.steamid64) == steamid64,
            col(MapReview.map_id) == map_id,
        )
        .order_by(
            col(MapReview.updated_at).desc(),
            col(MapReview.created_at).desc(),
            col(MapReview.id).desc(),
        )
    )
    reviews = list((await session.exec(statement)).all())
    if not reviews:
        return None

    now = get_datetime_utc()
    has_changes = False
    deleted_comment_texts: list[str] = []
    for review in reviews:
        content = dict(review.content)
        comment = content.get("comment")
        if not isinstance(comment, dict):
            continue
        comment_text = comment.get("text")
        if isinstance(comment_text, str) and comment_text.strip():
            deleted_comment_texts.append(comment_text)
        review.content = {
            **content,
            "comment": None,
        }
        review.updated_at = now
        session.add(review)
        has_changes = True

    if has_changes:
        await session.commit()

    latest_reviews, _ = await read_latest_map_reviews(
        session=session,
        offset=0,
        limit=1,
        map_id=map_id,
        steamid64=steamid64,
    )
    assert latest_reviews
    review, player, map_obj = latest_reviews[0]
    return review, player, map_obj, deleted_comment_texts
