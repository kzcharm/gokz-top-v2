import gzip
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.importers.v1_player_likes_sessions import (
    _stable_uuid7_from_source,
    import_v1_player_likes_sessions,
    iter_copy_dict_rows,
)
from app.models import Player, PlayerLike, PlayerSession, ServerGroup


def _write_sql_gz(
    tmp_path: Path,
    *,
    player_rows: list[str],
    group_rows: list[str],
    like_rows: list[str],
    session_rows: list[str],
) -> Path:
    path = tmp_path / "v1.sql.gz"
    with gzip.open(path, mode="wt", encoding="utf-8") as stream:
        stream.write("-- ignored header\n")
        stream.write(
            "COPY public.player (steamid64, name, custom_id, avatar_hash, country, "
            "created_at, last_seen, alias, updated_at, profile_updated_at, primary_mode, "
            "is_country_locked, alias_updated_at) FROM stdin;\n"
        )
        if player_rows:
            stream.write("\n".join(player_rows))
            stream.write("\n")
        stream.write("\\.\n")
        stream.write(
            "COPY public.server_groups (id, name, description, owner_id, website, "
            "discord, steam_group, created_at, updated_at, custom_id) FROM stdin;\n"
        )
        if group_rows:
            stream.write("\n".join(group_rows))
            stream.write("\n")
        stream.write("\\.\n")
        stream.write(
            "COPY public.player_likes (liker_steamid64, liked_steamid64, like_date, "
            "count, created_at, updated_at) FROM stdin;\n"
        )
        if like_rows:
            stream.write("\n".join(like_rows))
            stream.write("\n")
        stream.write("\\.\n")
        stream.write(
            "COPY public.player_sessions (id, player_steamid64, server_group_id, "
            "connected_time, disconnect_time, ip_address, map_name) FROM stdin;\n"
        )
        if session_rows:
            stream.write("\n".join(session_rows))
            stream.write("\n")
        stream.write("\\.\n")
    return path


def _player_row(steamid64: int, name: str = "Player") -> str:
    return "\t".join(
        [
            str(steamid64),
            name,
            r"\N",
            r"\N",
            r"\N",
            "2026-01-01 00:00:00+00",
            r"\N",
            r"\N",
            "2026-01-02 00:00:00+00",
            r"\N",
            "KZT",
            "f",
            r"\N",
        ]
    )


def _group_row(
    *,
    group_id: uuid.UUID,
    name: str,
    custom_id: str,
    owner: int = 76561198000000099,
) -> str:
    return "\t".join(
        [
            str(group_id),
            name,
            r"\N",
            str(owner),
            "https://example.test",
            r"\N",
            r"\N",
            "2026-01-01 00:00:00+00",
            "2026-01-02 00:00:00+00",
            custom_id,
        ]
    )


def _like_row(
    *,
    viewer: int,
    target: int,
    like_date: str = "2026-01-03",
    count: int = 10,
    created_at: str = "2026-01-03 01:02:03+00",
) -> str:
    return "\t".join(
        [
            str(viewer),
            str(target),
            like_date,
            str(count),
            created_at,
            "2026-01-03 01:02:04+00",
        ]
    )


def _session_row(
    *,
    session_id: uuid.UUID,
    player: int,
    group_id: uuid.UUID,
    connected_at: str,
    disconnect_at: str,
    ip_address: str = "203.0.113.10",
    map_name: str = "kz_example",
) -> str:
    return "\t".join(
        [
            str(session_id),
            str(player),
            str(group_id),
            connected_at,
            disconnect_at,
            ip_address,
            map_name,
        ]
    )


def test_iter_copy_dict_rows_parses_escaped_values(tmp_path: Path) -> None:
    group_id = uuid.uuid4()
    path = _write_sql_gz(
        tmp_path,
        player_rows=[_player_row(76561198000000001, name=r"Name\tWith\\Slash")],
        group_rows=[_group_row(group_id=group_id, name="Group", custom_id="group")],
        like_rows=[],
        session_rows=[],
    )

    rows = list(iter_copy_dict_rows(path, table="player"))

    assert rows[0]["name"] == "Name\tWith\\Slash"
    assert rows[0]["custom_id"] is None


def test_stable_uuid7_from_source_is_deterministic_and_time_based() -> None:
    source_id = uuid.UUID("aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa")
    connected_at = datetime(2026, 1, 2, 3, 4, 5, 678000, tzinfo=UTC)

    first = _stable_uuid7_from_source(source_id=source_id, timestamp=connected_at)
    second = _stable_uuid7_from_source(source_id=source_id, timestamp=connected_at)

    assert first == second
    assert first.version == 7
    assert first.int >> 80 == int(connected_at.timestamp() * 1000)


@pytest.mark.asyncio
async def test_import_likes_sessions_and_resolves_groups(
    db: AsyncSession,
    tmp_path: Path,
) -> None:
    existing_group_id = uuid.UUID("11111111-1111-4111-8111-111111111111")
    fallback_source_group_id = uuid.UUID("22222222-2222-4222-8222-222222222222")
    fallback_existing_group_id = uuid.UUID("33333333-3333-4333-8333-333333333333")
    created_group_id = uuid.UUID("44444444-4444-4444-8444-444444444444")
    session_one_id = uuid.UUID("55555555-5555-4555-8555-555555555555")
    session_two_id = uuid.UUID("66666666-6666-4666-8666-666666666666")
    session_three_id = uuid.UUID("77777777-7777-4777-8777-777777777777")
    viewer = 76561198000001001
    target = 76561198000001002
    session_player = 76561198000001003

    db.add(
        ServerGroup(
            id=existing_group_id,
            name="AXE GOKZ",
            custom_id="axekz",
            api_key="existing-axe",
        )
    )
    db.add(
        ServerGroup(
            id=fallback_existing_group_id,
            name="ThRei",
            custom_id="threi",
            api_key="existing-threi",
        )
    )
    await db.commit()

    path = _write_sql_gz(
        tmp_path,
        player_rows=[
            _player_row(viewer, name="Viewer"),
            _player_row(target, name="Target"),
            _player_row(session_player, name="Session Player"),
        ],
        group_rows=[
            _group_row(group_id=existing_group_id, name="AXE GOKZ", custom_id="axekz"),
            _group_row(
                group_id=fallback_source_group_id,
                name="ThRei",
                custom_id="threi",
            ),
            _group_row(
                group_id=created_group_id,
                name="CNGOKZ",
                custom_id="cngokz",
            ),
        ],
        like_rows=[
            _like_row(viewer=viewer, target=target, count=10),
            _like_row(
                viewer=viewer,
                target=target,
                count=1,
                created_at="2026-01-03 02:02:03+00",
            ),
            _like_row(viewer=target, target=target),
        ],
        session_rows=[
            _session_row(
                session_id=session_one_id,
                player=session_player,
                group_id=existing_group_id,
                connected_at="2026-01-04 01:00:00+00",
                disconnect_at="2026-01-04 01:30:00+00",
            ),
            _session_row(
                session_id=session_two_id,
                player=session_player,
                group_id=fallback_source_group_id,
                connected_at="2026-01-05 01:00:00+00",
                disconnect_at="2026-01-05 00:59:00+00",
                ip_address="203.0.113.11",
            ),
            _session_row(
                session_id=session_three_id,
                player=session_player,
                group_id=created_group_id,
                connected_at="2026-01-06 01:00:00+00",
                disconnect_at=r"\N",
                ip_address="203.0.113.12",
            ),
        ],
    )

    dry_run = await import_v1_player_likes_sessions(
        session=db,
        dump_path=path,
        dry_run=True,
        batch_size=2,
    )
    summary = await import_v1_player_likes_sessions(
        session=db,
        dump_path=path,
        dry_run=False,
        verify=True,
        batch_size=2,
    )
    rerun = await import_v1_player_likes_sessions(
        session=db,
        dump_path=path,
        dry_run=False,
        verify=True,
        batch_size=2,
    )

    assert dry_run.groups_created == 1
    assert dry_run.imported_likes == 0
    assert summary.placeholder_players == 4
    assert summary.groups_mapped_by_existing_id == 1
    assert summary.groups_mapped_by_name_or_custom_id == 1
    assert summary.groups_created == 1
    assert summary.imported_likes == 1
    assert summary.imported_sessions == 3
    assert summary.skipped_self_likes == 1
    assert summary.clamped_sessions == 1
    assert rerun.imported_sessions == 3

    like_rows = (
        await db.exec(
            select(PlayerLike).where(
                PlayerLike.viewer_steamid64 == viewer,
                PlayerLike.target_steamid64 == target,
            )
        )
    ).all()
    assert [(row.like_date, row.created_at) for row in like_rows] == [
        (date(2026, 1, 3), datetime(2026, 1, 3, 1, 2, 3, tzinfo=UTC))
    ]

    first_v2_id = _stable_uuid7_from_source(
        source_id=session_one_id,
        timestamp=datetime(2026, 1, 4, 1, 0, tzinfo=UTC),
    )
    second_v2_id = _stable_uuid7_from_source(
        source_id=session_two_id,
        timestamp=datetime(2026, 1, 5, 1, 0, tzinfo=UTC),
    )
    third_v2_id = _stable_uuid7_from_source(
        source_id=session_three_id,
        timestamp=datetime(2026, 1, 6, 1, 0, tzinfo=UTC),
    )

    first_session = await db.get(PlayerSession, first_v2_id)
    second_session = await db.get(PlayerSession, second_v2_id)
    third_session = await db.get(PlayerSession, third_v2_id)
    assert first_session is not None
    assert second_session is not None
    assert third_session is not None
    assert first_session.server_group_id == existing_group_id
    assert second_session.server_group_id == fallback_existing_group_id
    assert second_session.disconnect_at == datetime(2026, 1, 5, 1, 0, tzinfo=UTC)
    assert second_session.last_heartbeat_at == datetime(2026, 1, 5, 1, 0, tzinfo=UTC)
    assert third_session.server_group_id == created_group_id
    assert third_session.disconnect_at is None
    assert third_session.last_heartbeat_at == datetime(2026, 1, 6, 1, 0, tzinfo=UTC)

    created_group = await db.get(ServerGroup, created_group_id)
    assert created_group is not None
    assert created_group.name == "CNGOKZ"
    assert created_group.api_key == str(created_group_id)
    assert (await db.get(Player, viewer)) is not None


@pytest.mark.asyncio
async def test_import_group_ambiguous_match_fails_before_writes(
    db: AsyncSession,
    tmp_path: Path,
) -> None:
    source_group_id = uuid.UUID("88888888-8888-4888-8888-888888888888")
    session_id = uuid.UUID("99999999-9999-4999-8999-999999999999")
    player = 76561198000002001

    db.add(
        ServerGroup(
            id=uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
            name="Collision",
            custom_id="collision_one",
            api_key="collision-one",
        )
    )
    db.add(
        ServerGroup(
            id=uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
            name="Other",
            custom_id="collision",
            api_key="collision-two",
        )
    )
    await db.commit()

    path = _write_sql_gz(
        tmp_path,
        player_rows=[_player_row(player)],
        group_rows=[
            _group_row(
                group_id=source_group_id,
                name="Collision",
                custom_id="collision",
            )
        ],
        like_rows=[],
        session_rows=[
            _session_row(
                session_id=session_id,
                player=player,
                group_id=source_group_id,
                connected_at="2026-01-04 01:00:00+00",
                disconnect_at=r"\N",
            )
        ],
    )

    with pytest.raises(ValueError, match="matches multiple v2 groups"):
        await import_v1_player_likes_sessions(
            session=db,
            dump_path=path,
            dry_run=False,
        )

    generated_id = _stable_uuid7_from_source(
        source_id=session_id,
        timestamp=datetime(2026, 1, 4, 1, 0, tzinfo=UTC),
    )
    assert await db.get(PlayerSession, generated_id) is None
