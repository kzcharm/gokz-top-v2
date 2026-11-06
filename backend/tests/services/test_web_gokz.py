import json
import uuid
from pathlib import Path

import pytest

from app.models.web_gokz import WebIdentity
from app.services.web_gokz import Member, Room, playable_maps


def member(key: str = "1", admin: bool = False) -> Member:
    return Member(WebIdentity(steamid64=key, name=f"Player {key}"), admin=admin)


def room_with_players() -> tuple[Room, Member, Member]:
    room = Room(1, {"kz_one": "v1", "kz_two": "v2"}, "kz_one", opened_at=0)
    first, second = member(), member("2")
    room.join(first)
    room.join(second)
    return room, first, second


def test_rtv_protects_running_timers_then_changes_generation() -> None:
    room, first, second = room_with_players()
    generation = str(room.generation)
    room.receive(first, {"type": "timer_start", "generation": generation}, 31)
    assert first.running
    room.receive(first, {"type": "rtv"}, 32)
    assert not room.block_starts
    room.receive(second, {"type": "rtv"}, 33)
    assert room.block_starts
    room.receive(second, {"type": "timer_start", "generation": generation}, 34)
    assert not second.running
    room.receive(first, {"type": "vote", "map_name": "kz_two"}, 35)
    room.tick(54)
    assert room.pending_map == "kz_two"
    room.tick(60)
    assert room.map_name == "kz_one"
    first.running = False
    room.tick(61)
    room.tick(65)
    assert room.map_name == "kz_two"
    assert str(room.generation) != generation
    assert not room.block_starts
    assert not room.rtv


def test_solo_map_change_rechecks_membership_and_admin_can_change() -> None:
    room = Room(1, {"kz_one": "1", "kz_two": "2"}, "kz_one")
    first = member()
    room.join(first)
    room.receive(first, {"type": "map", "map_name": "kz_two"}, 1)
    room.join(member("2"))
    room.tick(5)
    assert room.map_name == "kz_one" and room.pending_map is None
    with pytest.raises(ValueError, match="RTV"):
        room.receive(first, {"type": "map", "map_name": "kz_two"}, 6)
    first.admin = True
    room.receive(first, {"type": "map", "map_name": "kz_two"}, 7)
    room.tick(11)
    assert room.map_name == "kz_two"


def test_stale_poses_timer_spoofing_invalid_commands_and_chat_limits() -> None:
    room, first, _ = room_with_players()
    pose = {
        "type": "state",
        "generation": str(uuid.uuid7()),
        "position": [0, 0, 0],
        "angles": [0, 0],
        "crouched": False,
        "mode": "KZT",
        "timer_running": True,
    }
    room.receive(first, pose, 31)
    assert first.state is None
    pose["generation"] = str(room.generation)
    room.receive(first, pose, 32)
    assert first.state and first.state["timer_running"] is False
    for data in (
        {**pose, "position": [float("nan"), 0, 0]},
        {**pose, "position": [1e7, 0, 0]},
        {**pose, "progress": 101},
        {**pose, "progress": float("nan")},
        {**pose, "time_ms": -1},
        {**pose, "teleports": 1.5},
        {"type": "nominate", "map_name": "missing"},
        {"type": "vote", "map_name": "kz_two"},
    ):
        with pytest.raises(ValueError):
            room.receive(first, data, 40 + first.last_command)
    room.receive(first, {"type": "chat", "text": "Hello!"}, 200)
    with pytest.raises(ValueError, match="wait"):
        room.receive(first, {"type": "chat", "text": "spam"}, 200.1)
    room.receive(first, {"type": "chat", "text": "!nominate kz_two"}, 201)
    assert room.nominations == {"1": "kz_two"}
    with pytest.raises(ValueError, match="already connected"):
        room.join(member())


def test_paused_progress_reaches_peers_and_normal_server_cards() -> None:
    room, first, second = room_with_players()
    generation = str(room.generation)
    room.receive(first, {"type": "timer_start", "generation": generation}, 31)
    room.receive(
        first,
        {
            "type": "state",
            "generation": generation,
            "position": [0, 0, 0],
            "angles": [0, 0],
            "crouched": False,
            "mode": "NKZ",
            "timer_running": True,
            "timer_paused": True,
            "progress": 42.5,
            "time_ms": 12345,
            "teleports": 2,
        },
        32,
    )
    assert first.running
    messages = []
    while not second.queue.empty():
        messages.append(second.queue.get_nowait())
    assert messages[-1]["progress"] == 42.5
    assert messages[-1]["timer_paused"] is True
    status = room.server_public().live_status
    assert status is not None
    player = status.players[0]
    assert player.score == 425 and player.timer_time == 12.345
    assert player.status == "in_progress" and player.is_paused


def test_disconnect_removes_votes_and_clears_empty_room() -> None:
    room, first, second = room_with_players()
    room.receive(first, {"type": "rtv"}, 31)
    room.leave(second)
    assert room.vote_ends
    room.leave(first)
    assert not room.block_starts and not room.rtv and not room.members


def test_spectator_poses_keep_membership_and_reach_peers_and_snapshots() -> None:
    room, first, second = room_with_players()
    pose = {
        "type": "state",
        "generation": str(room.generation),
        "position": [0, 0, 0],
        "angles": [0, 0],
        "crouched": False,
        "mode": "NKZ",
        "timer_running": False,
    }
    room.receive(first, pose, 1)
    assert first.state and first.state["spectating"] is False
    while not second.queue.empty():
        second.queue.get_nowait()
    room.receive(first, {**pose, "spectating": True}, 2)
    assert second.queue.get_nowait()["spectating"] is True
    room.snapshot()
    snapshot = second.queue.get_nowait()
    assert len(snapshot["room"]["players"]) == 2
    assert snapshot["states"][0]["spectating"] is True
    status = room.server_public().live_status
    assert status is not None and status.player_count == 2
    for invalid in ("true", 1, None):
        with pytest.raises(ValueError):
            room.receive(first, {**pose, "spectating": invalid}, 3)
    room.receive(first, {**pose, "spectating": False}, 4)
    assert second.queue.get_nowait()["spectating"] is False
    assert len(room.members) == 2


def test_playable_maps_require_both_assets(tmp_path: Path) -> None:
    (tmp_path / "practice").mkdir()
    (tmp_path / "maps" / "kz_one").mkdir(parents=True)
    (tmp_path / "maps" / "kz_one" / "index.json").write_text("{}")
    (tmp_path / "practice" / "kz_one.json").write_text(
        json.dumps({"bspSha256": "hash"})
    )
    (tmp_path / "practice" / "kz_missing.json").write_text(
        json.dumps({"bspSha256": "hash"})
    )
    (tmp_path / "maps" / "bad.name").mkdir()
    (tmp_path / "maps" / "bad.name" / "index.json").write_text("{}")
    (tmp_path / "practice" / "bad.name.json").write_text(
        json.dumps({"bspSha256": "hash"})
    )
    assert playable_maps(tmp_path) == {"kz_one": "hash"}
