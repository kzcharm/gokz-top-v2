import asyncio
import json
import math
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.server import (
    ServerGroupSummary,
    ServerLiveStatusPublic,
    ServerPlayerPublic,
    ServerPlayerRunStatus,
    ServerPublic,
)
from app.models.web_gokz import WebIdentity, WebMode

WEB_GROUP_ID = uuid.UUID("01a1b19d-8123-7329-b0eb-554c875f33c4")
WEB_SERVER_IDS = (
    uuid.UUID("01a1b19d-8123-7329-b0eb-554d70a3157f"),
    uuid.UUID("01a1b19d-8123-7329-b0eb-554e79d813ce"),
)


def playable_maps(root: Path) -> dict[str, str]:
    """Only advertise maps with both rendering and physics assets."""
    result = {}
    for path in sorted((root / "practice").glob("*.json")):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", path.stem):
            continue
        if not (root / "maps" / path.stem / "index.json").is_file():
            continue
        try:
            payload = json.loads(path.read_text())
            version = payload.get("bspSha256")
            if isinstance(version, str) and 0 < len(version) <= 128:
                result[path.stem] = version
        except (OSError, ValueError, AttributeError):
            continue
    return result


class Movement(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    type: Literal["state"]
    generation: uuid.UUID
    position: tuple[float, float, float]
    angles: tuple[float, float]
    crouched: bool
    mode: WebMode
    timer_running: bool
    timer_paused: bool = False
    spectating: bool = Field(default=False, strict=True)
    time_ms: int = Field(default=0, ge=0, le=2147483647, strict=True)
    teleports: int = Field(default=0, ge=0, le=1000000, strict=True)
    progress: float | None = Field(default=None, ge=0, le=100)


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["chat", "rtv", "nominate", "vote", "map", "timer_start"]
    generation: uuid.UUID | None = None
    text: str = Field(default="", max_length=400)
    map_name: str = Field(default="", max_length=128)


@dataclass
class Member:
    player: WebIdentity
    admin: bool = False
    queue: asyncio.Queue[dict[str, Any]] = field(
        default_factory=lambda: asyncio.Queue(128)
    )
    state: dict[str, Any] | None = None
    running: bool = False
    last_state: float = 0
    granted_at: float = 0
    finished: bool = False
    last_command: float = 0

    def send(self, message: dict[str, Any]) -> None:
        if self.queue.full():
            # A stalled client must reconnect rather than accumulate stale movement.
            while not self.queue.empty():
                self.queue.get_nowait()
            self.queue.put_nowait({"type": "disconnect"})
        else:
            self.queue.put_nowait(message)


@dataclass
class Room:
    id: int
    maps: dict[str, str]
    map_name: str
    generation: uuid.UUID = field(default_factory=uuid.uuid7)
    members: dict[str, Member] = field(default_factory=dict)
    rtv: set[str] = field(default_factory=set)
    nominations: dict[str, str] = field(default_factory=dict)
    votes: dict[str, str] = field(default_factory=dict)
    options: list[str] = field(default_factory=list)
    vote_ends: float = 0
    pending_map: str | None = None
    change_at: float = 0
    requester: str | None = None
    opened_at: float = field(default_factory=time.time)

    @property
    def needed(self) -> int:
        return max(1, math.ceil(len(self.members) * 0.6))

    @property
    def block_starts(self) -> bool:
        return bool(self.vote_ends or self.pending_map)

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": f"Web GOKZ #{self.id}",
            "map_name": self.map_name,
            "generation": str(self.generation),
            "players": [member.player.model_dump() for member in self.members.values()],
            "max_players": 16,
            "rtv_votes": len(self.rtv),
            "rtv_needed": self.needed,
            "vote": {"options": self.options, "ends_at": self.vote_ends}
            if self.vote_ends
            else None,
            "pending_map": self.pending_map,
            "block_starts": self.block_starts,
            "available": bool(self.map_name),
        }

    def server_public(self) -> ServerPublic:
        now = datetime.now(UTC)
        players = []
        for member in self.members.values():
            state = member.state or {}
            progress = state.get("progress")
            players.append(
                ServerPlayerPublic.model_validate(
                    {
                        **member.player.model_dump(),
                        "mode": state.get("mode", "NKZ"),
                        "score": round(progress * 10) if progress is not None else None,
                        "is_paused": member.running
                        and state.get("timer_paused", False),
                        "timer_time": state.get("time_ms", 0) / 1000,
                        "teleports": state.get("teleports", 0),
                        "status": (
                            ServerPlayerRunStatus.FINISHED
                            if member.finished
                            else ServerPlayerRunStatus.IN_PROGRESS
                            if member.running
                            else ServerPlayerRunStatus.NOT_STARTED
                        ),
                    }
                )
            )
        return ServerPublic(
            id=WEB_SERVER_IDS[self.id - 1],
            ip="web-gokz",
            port=self.id,
            is_public=True,
            group_id=WEB_GROUP_ID,
            group=ServerGroupSummary(
                id=WEB_GROUP_ID, name="Web GOKZ", custom_id="web-gokz"
            ),
            source={"type": "web_gokz", "room_id": self.id},
            created_at=datetime.fromtimestamp(self.opened_at, UTC),
            updated_at=now,
            live_status=ServerLiveStatusPublic(
                hostname=f"Web GOKZ #{self.id}",
                map=self.map_name,
                player_count=len(players),
                max_players=16,
                players=players,
                is_online=bool(self.map_name),
                updated_at=now,
            ),
        )

    def broadcast(self, message: dict[str, Any]) -> None:
        for member in list(self.members.values()):
            member.send(message)

    def snapshot(self) -> None:
        self.broadcast(
            {
                "type": "room",
                "room": self.public(),
                "states": [m.state for m in self.members.values() if m.state],
            }
        )

    def say(self, text: str) -> None:
        self.broadcast({"type": "chat", "player": None, "text": text})

    def join(self, member: Member) -> None:
        key = member.player.steamid64
        if key in self.members:
            raise ValueError("This account is already connected to this room.")
        if len(self.members) >= 16:
            raise ValueError("This room is full.")
        if not self.map_name:
            raise ValueError("No playable maps are installed.")
        self.members[key] = member
        self.snapshot()

    def leave(self, member: Member) -> None:
        key = member.player.steamid64
        if self.members.get(key) is not member:
            return
        del self.members[key]
        self.rtv.discard(key)
        self.votes.pop(key, None)
        self.nominations.pop(key, None)
        if not self.members:
            self.options.clear()
            self.vote_ends = 0
            self.pending_map = None
            self.change_at = 0
            self.requester = None
        self.tick(time.time())
        self.snapshot()

    def can_change(self, key: str) -> bool:
        member = self.members.get(key)
        return bool(member and (member.admin or len(self.members) == 1))

    def start_vote(self, now: float) -> None:
        candidates = list(dict.fromkeys(self.nominations.values()))
        candidates.extend(name for name in self.maps if name not in candidates)
        self.options = [name for name in candidates if name != self.map_name][:5]
        if not self.options:
            self.rtv.clear()
            self.say("No other playable maps are available.")
            return
        self.vote_ends = now + 20
        self.votes.clear()
        self.say("Map vote started. Existing runs may finish; new timers are paused.")
        self.snapshot()

    def tick(self, now: float) -> None:
        if (
            not self.block_starts
            and self.rtv
            and len(self.rtv) >= self.needed
            and now >= self.opened_at + 30
        ):
            self.start_vote(now)
        if self.vote_ends and now >= self.vote_ends:
            winner = max(
                self.options, key=lambda name: list(self.votes.values()).count(name)
            )
            self.vote_ends = 0
            self.pending_map = winner
            self.requester = None
            self.say(f"Next map: {winner}. Waiting for active runs to finish.")
            self.snapshot()
        if not self.pending_map:
            return
        if self.requester and not self.can_change(self.requester):
            self.pending_map = None
            self.change_at = 0
            self.requester = None
            self.say(
                "Map change cancelled: the requester left or another player joined."
            )
            self.snapshot()
            return
        if not self.requester and any(m.running for m in self.members.values()):
            return
        if not self.change_at:
            self.change_at = now + 3
            self.say(f"Changing to {self.pending_map} in 3 seconds.")
        elif now >= self.change_at:
            self.map_name = self.pending_map
            self.generation = uuid.uuid7()
            self.pending_map = None
            self.change_at = 0
            self.requester = None
            self.opened_at = now
            self.rtv.clear()
            self.nominations.clear()
            self.votes.clear()
            self.options.clear()
            for member in self.members.values():
                member.state = None
                member.running = False
                member.finished = False
            self.broadcast(
                {
                    "type": "map_change",
                    "map_name": self.map_name,
                    "generation": str(self.generation),
                }
            )
            self.snapshot()

    def receive(self, member: Member, payload: dict[str, Any], now: float) -> None:
        key = member.player.steamid64
        if payload.get("type") == "state":
            state = Movement.model_validate(payload)
            if state.generation != self.generation or now - member.last_state < 0.045:
                return
            if any(abs(value) > 1000000 for value in (*state.position, *state.angles)):
                raise ValueError("Movement coordinates are out of bounds.")
            member.last_state = now
            # Idle poses sent before the start acknowledgement can still be in flight.
            member.running = member.running and (
                state.timer_running or now < member.granted_at + 1
            )
            member.state = {
                **state.model_dump(mode="json"),
                "steamid64": key,
                "timer_running": member.running,
                "timer_paused": member.running and state.timer_paused,
            }
            self.broadcast(member.state)
            return
        command = Command.model_validate(payload)
        if now - member.last_command < 0.3:
            raise ValueError("Please wait before sending another command.")
        member.last_command = now
        action: str = command.type
        name = command.map_name
        if action == "chat":
            message = " ".join(command.text.split())
            if not message:
                return
            first, _, argument = message.partition(" ")
            if first.lower().lstrip("!/") in {"rtv", "rockthevote", "nominate", "map"}:
                action = (
                    "rtv"
                    if first.lower().lstrip("!/") in {"rtv", "rockthevote"}
                    else first.lower().lstrip("!/")
                )
                name = argument
            else:
                self.broadcast(
                    {
                        "type": "chat",
                        "player": member.player.model_dump(),
                        "text": message,
                    }
                )
                return
        if action == "timer_start":
            allowed = command.generation == self.generation and not self.block_starts
            if allowed:
                member.finished = False
                member.running = True
                member.granted_at = now
            member.send(
                {
                    "type": "timer_start",
                    "allowed": allowed,
                    "generation": str(self.generation),
                }
            )
            return
        if action == "rtv":
            if self.block_starts:
                raise ValueError("A map vote or change is already in progress.")
            if now < self.opened_at + 30:
                raise ValueError("RTV is available 30 seconds after a map starts.")
            self.rtv.add(key)
            self.say(
                f"{member.player.name} requested RTV ({len(self.rtv)}/{self.needed})."
            )
        elif action in {"map", "nominate", "vote"}:
            if name not in self.maps:
                raise ValueError("Choose a map from the playable map list.")
            if action == "vote":
                if (
                    not self.vote_ends
                    or now >= self.vote_ends
                    or name not in self.options
                ):
                    raise ValueError("That map is not in the current vote.")
                self.votes[key] = name
            elif action == "nominate":
                if self.block_starts:
                    raise ValueError(
                        "Nominations are closed during a vote or map change."
                    )
                self.nominations[key] = name
                self.say(f"{member.player.name} nominated {name}.")
            else:
                if self.block_starts or not self.can_change(key):
                    raise ValueError("Use RTV when other players are connected.")
                self.pending_map = name
                self.requester = key
        self.tick(now)
        self.snapshot()


# shortcut: rooms live in one dedicated process; use a shared room owner before scaling it.
rooms: dict[int, Room] = {}
