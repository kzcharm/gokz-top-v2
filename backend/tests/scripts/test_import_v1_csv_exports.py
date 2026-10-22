"""Exercise CSV imports at the legacy-input and database boundaries."""

import csv
import json
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.importers import v1_csv_exports as importer
from app.models import Map, MapReview, Player, PlayerSession, ServerGroup
from tests.utils.utils import random_steamid64


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


@pytest.mark.parametrize(
    ("function", "value", "expected"),
    [
        (importer._normalize_optional_int, None, None),
        (importer._normalize_optional_int, " ", None),
        (importer._normalize_optional_int, " 12 ", 12),
        (importer._normalize_int, " 7 ", 7),
        (importer._normalize_text, " kz_test ", "kz_test"),
    ],
)
def test_scalar_normalization(function, value, expected) -> None:
    assert function(value, field_name="legacy") == expected


@pytest.mark.parametrize(
    "function",
    [
        importer._normalize_int,
        importer._normalize_text,
        importer._normalize_uuid,
        importer._normalize_datetime,
    ],
)
def test_required_csv_fields_cannot_be_blank(function) -> None:
    with pytest.raises(ValueError, match="legacy must not be blank"):
        function("  ", field_name="legacy")


def test_dates_and_sessions_preserve_utc_and_clamp_invalid_legacy_ends() -> None:
    connected = datetime(2025, 1, 1, tzinfo=UTC)
    assert (
        importer._normalize_datetime("2025-01-01T02:00:00+02:00", field_name="date")
        == connected
    )
    assert importer._normalize_datetime("2025-01-01", field_name="date") == connected
    assert importer._normalize_optional_datetime(" ") is None
    assert importer._normalize_optional_datetime("2025-01-01Z") == connected
    assert importer._normalize_session_timestamps(
        connected_at=connected, disconnect_at=None
    ) == (None, connected, False)
    assert importer._normalize_session_timestamps(
        connected_at=connected, disconnect_at=connected - timedelta(seconds=1)
    ) == (connected, connected, True)
    assert list(importer._chunked([1, 2, 3], size=2)) == [[1, 2], [3]]
    with pytest.raises(ValueError, match="chunk size"):
        list(importer._chunked([1], size=0))


def test_review_content_validation_and_comment_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    when = datetime(2025, 1, 1, tzinfo=UTC)
    monkeypatch.setattr(importer, "detect_language_code", lambda _text: "en")
    assert importer._normalize_review_comment_text(None) is None
    assert len(importer._normalize_review_comment_text("x" * 1200)) == 1000
    for comment, language in [
        (None, None),
        ({"text": " useful "}, "ru"),
        (" useful ", None),
    ]:
        payload = {"overall": 4, "gameplay": "3", "visuals": "", "comment": comment}
        if language:
            payload["lang"] = language
        content = importer._normalize_review_content(
            raw_content=json.dumps(payload), created_at=when, updated_at=when
        )
        assert content["overall"] == 4
        assert content["visuals"] is None
        if comment is None:
            assert content["comment"] is None
        else:
            assert content["comment"] == {
                "text": "useful",
                "language": language or "en",
                "created_at": when.isoformat(),
                "updated_at": when.isoformat(),
            }
    with pytest.raises(ValueError, match="JSON object"):
        importer._normalize_review_content(
            raw_content="[]", created_at=when, updated_at=when
        )


@pytest.mark.asyncio
async def test_csv_import_dry_run_upsert_and_missing_dependencies(
    db: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @asynccontextmanager
    async def session_factory():
        yield db

    monkeypatch.setattr(importer, "async_session_maker", session_factory)
    monkeypatch.setattr(importer, "detect_language_code", lambda _text: "en")
    steamid = random_steamid64()
    group_id, session_id = uuid.uuid7(), uuid.uuid7()
    session_path, review_path = tmp_path / "sessions.csv", tmp_path / "reviews.csv"
    connected = datetime(2025, 1, 1, tzinfo=UTC)
    session_rows = [
        {
            "id": str(session_id),
            "player_steamid64": str(steamid),
            "server_group_id": str(group_id),
            "connected_time": connected.isoformat(),
            "disconnect_time": "2024-12-31T23:59:00Z",
            "ip_address": "127.0.0.1",
            "map_name": "kz_csv_coverage",
        }
    ]
    review_rows = [
        {
            "steamid64": str(steamid),
            "map_id": "972341",
            "created_at": connected.isoformat(),
            "updated_at": connected.isoformat(),
            "content": json.dumps({"overall": 4, "comment": "A useful review"}),
        }
    ]
    write_csv(session_path, session_rows)
    write_csv(review_path, review_rows)
    args = [
        "--player-sessions-csv",
        str(session_path),
        "--map-review-csv",
        str(review_path),
        "--batch-size",
        "1",
    ]
    await importer._main_async([*args, "--dry-run"])
    assert await db.get(Player, steamid) is None
    with pytest.raises(ValueError, match="missing map ids: 972341"):
        await importer._assert_review_maps_exist(map_ids={972341})
    db.add(Map(id=972341, name="kz_csv_coverage"))
    await db.flush()
    await importer._main_async(args)
    group = await db.get(ServerGroup, group_id)
    assert group is not None and group.custom_id
    session = await db.get(PlayerSession, session_id)
    assert session is not None
    assert session.disconnect_at == connected
    assert session.last_heartbeat_at == connected
    review = (await db.exec(select(MapReview).where(MapReview.map_id == 972341))).one()
    assert review.content["comment"]["text"] == "A useful review"
    session_rows[0]["disconnect_time"] = "2025-01-01T00:10:00Z"
    write_csv(session_path, session_rows)
    await importer._main_async(args)
    await db.refresh(session)
    assert session.disconnect_at == connected + timedelta(minutes=10)
    assert (
        len((await db.exec(select(MapReview).where(MapReview.map_id == 972341))).all())
        == 1
    )
    assert await importer._insert_placeholder_players(player_ids=set()) == 0
    assert await importer._insert_placeholder_server_groups(group_ids=set()) == 0
    assert await importer._import_map_reviews(rows=[]) == 0
    await importer._assert_review_maps_exist(map_ids=set())
    session_rows[0]["id"] = str(uuid.uuid7())
    write_csv(session_path, session_rows * 2)
    batches = list(importer._iter_player_session_batches(session_path, batch_size=3))
    assert len(batches) == 1 and len(batches[0][0]) == 2
    with pytest.raises(ValueError, match="batch-size"):
        await importer._main_async([*args, "--batch-size", "0"])
    with pytest.raises(FileNotFoundError):
        await importer._main_async(
            [
                "--player-sessions-csv",
                str(tmp_path / "missing"),
                "--map-review-csv",
                str(review_path),
            ]
        )
    with pytest.raises(FileNotFoundError):
        await importer._main_async(
            [
                "--player-sessions-csv",
                str(session_path),
                "--map-review-csv",
                str(tmp_path / "missing"),
            ]
        )
