import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.crud.player import to_player_ref_public
from app.models import (
    Map,
    MapRefPublic,
    MapReview,
    MapReviewContentInput,
    MapReviewContentPublic,
    MapReviewPublic,
    Player,
    get_datetime_utc,
)
from app.services.language_detection import detect_language_code


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
        "steamid64": steamid64,
        "map_id": map_id,
        "server_group_id": server_group_id,
        "content": content,
        "updated_at": now,
    }
    if existing is None:
        values["id"] = uuid.uuid7()
        values["created_at"] = now

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
) -> tuple[list[tuple[MapReview, Player, Map]], int]:
    review_table = MapReview.__table__  # type: ignore[attr-defined]
    ranked_reviews = (
        select(
            review_table.c.id.label("review_id"),
            func.row_number()
            .over(
                partition_by=(review_table.c.steamid64, review_table.c.map_id),
                order_by=(
                    review_table.c.updated_at.desc(),
                    review_table.c.created_at.desc(),
                    review_table.c.id.desc(),
                ),
            )
            .label("rank"),
        )
        .select_from(review_table)
    )
    if map_id is not None:
        ranked_reviews = ranked_reviews.where(review_table.c.map_id == map_id)
    if steamid64 is not None:
        ranked_reviews = ranked_reviews.where(review_table.c.steamid64 == steamid64)

    ranked_subquery = ranked_reviews.subquery()
    latest_ids = (
        select(ranked_subquery.c.review_id)
        .where(ranked_subquery.c.rank == 1)
        .subquery()
    )

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
        .order_by(
            col(MapReview.updated_at).desc(),
            col(MapReview.created_at).desc(),
            col(MapReview.id).desc(),
        )
        .offset(offset)
        .limit(limit)
    )

    for condition in filters:
        count_statement = count_statement.where(condition)
        statement = statement.where(condition)

    count = (await session.exec(count_statement)).one()
    rows = list((await session.exec(statement)).all())
    return rows, count
