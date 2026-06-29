import gzip
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest
from sqlmodel import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.importers.v1_map_reviews import (
    import_v1_map_reviews_from_sql_gz,
    iter_legacy_map_review_copy_rows,
    normalize_legacy_map_review_content,
    read_legacy_map_review_rows,
)
from app.models import Map, MapReview, MapReviewSummaryCache, Player, ServerGroup


def _bind_import_session(
    monkeypatch: pytest.MonkeyPatch,
    db: AsyncSession,
) -> None:
    @asynccontextmanager
    async def _session_maker():
        yield db

    monkeypatch.setattr("app.importers.v1_map_reviews.async_session_maker", _session_maker)


def _write_sql_gz(tmp_path, rows: list[str]) -> object:
    path = tmp_path / "v1.sql.gz"
    with gzip.open(path, mode="wt", encoding="utf-8") as stream:
        stream.write("-- unrelated dump content\n")
        stream.write(
            "COPY public.map_review (steamid64, map_id, content, created_at, updated_at) "
            "FROM stdin;\n"
        )
        for row in rows:
            stream.write(f"{row}\n")
        stream.write("\\.\n")
        stream.write("-- ignored after copy\n")
    return path


async def _create_map(db: AsyncSession, *, id: int, name: str) -> None:
    await db.exec(delete(MapReview).where(MapReview.map_id == id))
    await db.exec(delete(MapReviewSummaryCache).where(MapReviewSummaryCache.map_id == id))
    await db.exec(delete(Map).where(Map.id == id))
    await db.commit()
    db.add(
        Map(
            id=id,
            name=name,
            filesize=1,
            validated=True,
            difficulty=4,
            approved_by_steamid64=76561198003275951,
        )
    )
    await db.commit()


async def _create_player(db: AsyncSession, *, steamid64: int, name: str) -> None:
    await db.exec(delete(Player).where(Player.steamid64 == steamid64))
    await db.commit()
    db.add(Player(steamid64=steamid64, name=name))
    await db.commit()


def test_iter_legacy_map_review_copy_rows_extracts_only_review_copy(tmp_path) -> None:
    path = _write_sql_gz(
        tmp_path,
        [
            '76561198000000100\t990701\t{"lang":"en","comment":"line\\\\ntext","overall":5,"visuals":4,"gameplay":3}\t2026-05-01 10:00:00\t2026-05-01 11:00:00'
        ],
    )

    rows = list(iter_legacy_map_review_copy_rows(path))

    assert rows == [
        [
            "76561198000000100",
            "990701",
            '{"lang":"en","comment":"line\\ntext","overall":5,"visuals":4,"gameplay":3}',
            "2026-05-01 10:00:00",
            "2026-05-01 11:00:00",
        ]
    ]


def test_read_legacy_map_review_rows_normalizes_content(tmp_path) -> None:
    path = _write_sql_gz(
        tmp_path,
        [
            '76561198000000101\t990702\t{"lang":"en","comment":"  great map  ","overall":5,"visuals":4,"gameplay":3}\t2026-05-01 10:00:00\t2026-05-01 11:00:00'
        ],
    )

    row = read_legacy_map_review_rows(path)[0]

    assert row.steamid64 == 76561198000000101
    assert row.map_id == 990702
    assert row.created_at == datetime(2026, 5, 1, 10, 0, tzinfo=UTC)
    assert row.updated_at == datetime(2026, 5, 1, 11, 0, tzinfo=UTC)
    assert row.content == {
        "overall": 5,
        "gameplay": 3,
        "visuals": 4,
        "comment": {
            "text": "great map",
            "language": "en",
            "created_at": "2026-05-01T10:00:00+00:00",
            "updated_at": "2026-05-01T11:00:00+00:00",
        },
    }


@pytest.mark.asyncio
async def test_import_v1_map_reviews_overwrites_website_reviews_and_rebuilds_summaries(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    _bind_import_session(monkeypatch, db)
    existing_player = 76561198000000110
    placeholder_player = 76561198000000111
    map_one = 990710
    map_two = 990711
    await _create_map(db, id=map_one, name="kz_v1_review_one")
    await _create_map(db, id=map_two, name="kz_v1_review_two")
    await _create_player(db, steamid64=existing_player, name="Existing")

    server_group = ServerGroup(
        name="Review Import Group",
        custom_id="review-import-group",
        api_key="review-import-key",
    )
    db.add(server_group)
    await db.commit()
    await db.refresh(server_group)

    db.add(
        MapReview(
            steamid64=existing_player,
            map_id=map_one,
            server_group_id=None,
            content={"overall": 1, "gameplay": None, "visuals": None, "comment": None},
            created_at=datetime(2026, 4, 1, tzinfo=UTC),
            updated_at=datetime(2026, 4, 1, tzinfo=UTC),
        )
    )
    db.add(
        MapReview(
            steamid64=existing_player,
            map_id=map_one,
            server_group_id=server_group.id,
            content={"overall": 2, "gameplay": None, "visuals": None, "comment": None},
            created_at=datetime(2026, 4, 2, tzinfo=UTC),
            updated_at=datetime(2026, 4, 2, tzinfo=UTC),
        )
    )
    await db.commit()

    path = _write_sql_gz(
        tmp_path,
        [
            f'{existing_player}\t{map_one}\t{{"lang":"en","comment":"imported","overall":5,"visuals":4,"gameplay":3}}\t2026-05-01 10:00:00\t2026-05-01 11:00:00',
            f'{placeholder_player}\t{map_two}\t{{"lang":null,"comment":null,"overall":4,"visuals":null,"gameplay":null}}\t2026-05-02 10:00:00\t2026-05-02 11:00:00',
        ],
    )

    dry_run_result = await import_v1_map_reviews_from_sql_gz(source_sql_gz=path, dry_run=True)
    result = await import_v1_map_reviews_from_sql_gz(source_sql_gz=path, verify=True)

    assert dry_run_result.source_rows == 2
    assert dry_run_result.missing_players == 1
    assert dry_run_result.existing_website_reviews == 1
    assert dry_run_result.imported_rows == 0
    assert result.imported_rows == 2
    assert result.summaries_rebuilt == 2

    placeholder = await db.get(Player, placeholder_player)
    assert placeholder is not None
    assert placeholder.name == str(placeholder_player)

    website_review = (
        await db.exec(
            select(MapReview).where(
                MapReview.steamid64 == existing_player,
                MapReview.map_id == map_one,
                MapReview.server_group_id.is_(None),
            )
        )
    ).one()
    assert website_review.content == normalize_legacy_map_review_content(
        raw_content='{"lang":"en","comment":"imported","overall":5,"visuals":4,"gameplay":3}',
        created_at=datetime(2026, 5, 1, 10, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 1, 11, 0, tzinfo=UTC),
    )

    server_group_review = (
        await db.exec(
            select(MapReview).where(
                MapReview.steamid64 == existing_player,
                MapReview.map_id == map_one,
                MapReview.server_group_id == server_group.id,
            )
        )
    ).one()
    assert server_group_review.content["overall"] == 2

    assert await db.get(MapReviewSummaryCache, map_one) is not None
    assert await db.get(MapReviewSummaryCache, map_two) is not None


@pytest.mark.asyncio
async def test_import_v1_map_reviews_fails_before_writes_for_missing_maps(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    _bind_import_session(monkeypatch, db)
    missing_player = 76561198000000120
    missing_map = 990720
    await db.exec(delete(Player).where(Player.steamid64 == missing_player))
    await db.exec(delete(Map).where(Map.id == missing_map))
    await db.commit()
    path = _write_sql_gz(
        tmp_path,
        [
            f'{missing_player}\t{missing_map}\t{{"lang":null,"comment":null,"overall":4,"visuals":null,"gameplay":null}}\t2026-05-02 10:00:00\t2026-05-02 11:00:00'
        ],
    )

    with pytest.raises(ValueError, match="missing map ids"):
        await import_v1_map_reviews_from_sql_gz(source_sql_gz=path)

    assert await db.get(Player, missing_player) is None
    reviews = (
        await db.exec(
            select(MapReview).where(
                MapReview.steamid64 == missing_player,
                MapReview.map_id == missing_map,
            )
        )
    ).all()
    assert reviews == []
