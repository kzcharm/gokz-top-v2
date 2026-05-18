from __future__ import annotations

import math
import struct

from app.models import KZMode

REPLAY_MAGIC = 0x676F6B7A
REPLAY_FORMAT_VERSION = 2
REPLAY_TYPE_RUN = 0
REPLAY_TYPE_JUMP = 2
REPLAY_STYLE_NRM = 0
UNIVERSE_PUBLIC = 1
STEAM_ID_TYPE_INDIVIDUAL = 1
STEAM_ID_INSTANCE_DESKTOP = 1

MODE_BY_INDEX: dict[int, KZMode] = {
    0: KZMode.VNL,
    1: KZMode.SKZ,
    2: KZMode.KZT,
    3: KZMode.NKZ,
}


class BinaryReader:
    def __init__(self, data: bytes) -> None:
        self._data = data
        self._pos = 0

    def read_u8(self) -> int:
        value = self._data[self._pos]
        self._pos += 1
        return value

    def read_i32(self) -> int:
        value = struct.unpack_from("<i", self._data, self._pos)[0]
        self._pos += 4
        return value

    def read_u32(self) -> int:
        value = struct.unpack_from("<I", self._data, self._pos)[0]
        self._pos += 4
        return value

    def read_len_string_u8(self) -> str:
        length = self.read_u8()
        value = self._data[self._pos : self._pos + length].decode("utf-8", "replace")
        self._pos += length
        return value


def float_from_i32(raw: int) -> float:
    return struct.unpack("<f", struct.pack("<I", raw & 0xFFFFFFFF))[0]


def ensure_finite(*, value: float, label: str, source_name: str, error_type: type[ValueError]) -> float:
    if not math.isfinite(value):
        raise error_type(f"{source_name}: replay contains non-finite {label}")
    return value


def steam_account_id_to_steamid64(
    account_id: int, *, error_type: type[ValueError]
) -> int:
    if account_id <= 0:
        raise error_type("Replay is missing a valid Steam account ID")
    return (
        (UNIVERSE_PUBLIC << 56)
        | (STEAM_ID_TYPE_INDIVIDUAL << 52)
        | (STEAM_ID_INSTANCE_DESKTOP << 32)
        | account_id
    )
