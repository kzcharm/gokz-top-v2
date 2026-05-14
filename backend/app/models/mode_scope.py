from enum import IntEnum, StrEnum


class ModeScope(StrEnum):
    OVR = "OVR"
    KZT = "KZT"
    SKZ = "SKZ"
    VNL = "VNL"

    @property
    def scope_id(self) -> int:
        return MODE_SCOPE_ID_BY_SCOPE[self]


class ModeScopeId(IntEnum):
    OVR = 0
    KZT = 1
    SKZ = 2
    VNL = 3


MODE_SCOPE_ID_BY_SCOPE: dict[ModeScope, int] = {
    ModeScope.OVR: ModeScopeId.OVR,
    ModeScope.KZT: ModeScopeId.KZT,
    ModeScope.SKZ: ModeScopeId.SKZ,
    ModeScope.VNL: ModeScopeId.VNL,
}

def mode_scope_to_id(scope: ModeScope) -> int:
    return int(MODE_SCOPE_ID_BY_SCOPE[scope])


def mode_scope_from_id(scope_id: ModeScope | int) -> ModeScope:
    if isinstance(scope_id, ModeScope):
        return scope_id
    return ModeScope[ModeScopeId(scope_id).name]


def mode_scope_modes(scope: ModeScope):
    from .record import KZMode

    if scope is ModeScope.OVR:
        return (KZMode.KZT, KZMode.SKZ, KZMode.VNL, KZMode.NKZ)
    if scope is ModeScope.KZT:
        return (KZMode.KZT, KZMode.NKZ)
    if scope is ModeScope.SKZ:
        return (KZMode.SKZ,)
    return (KZMode.VNL,)


def mode_scope_mode_ids(scope_id: int) -> tuple[int, ...]:
    return tuple(mode.mode_id for mode in mode_scope_modes(mode_scope_from_id(scope_id)))


def normalize_mode_scope(value: ModeScope | str | int) -> ModeScope:
    if isinstance(value, ModeScope):
        return value
    if isinstance(value, int):
        return mode_scope_from_id(value)
    return ModeScope(value)
