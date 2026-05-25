from collections.abc import Iterable
from enum import StrEnum


class UserRole(StrEnum):
    SUPERUSER = "superuser"
    ADMIN = "admin"
    MAP_ADMIN = "map_admin"
    SERVER_OWNER = "server_owner"


USER_ROLE_ORDER: tuple[UserRole, ...] = (
    UserRole.SUPERUSER,
    UserRole.ADMIN,
    UserRole.MAP_ADMIN,
    UserRole.SERVER_OWNER,
)


def normalize_user_roles(
    roles: Iterable[UserRole | str] | None,
) -> list[UserRole]:
    if roles is None:
        return []

    role_set = {role if isinstance(role, UserRole) else UserRole(role) for role in roles}
    return [role for role in USER_ROLE_ORDER if role in role_set]
