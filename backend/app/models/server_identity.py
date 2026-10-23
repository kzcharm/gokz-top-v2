"""Steam game-server identities, serialized as strings to preserve all 64 bits."""

from typing import Annotated

from pydantic import AfterValidator, StringConstraints


def validate_server_steamid(value: str) -> str:
    steamid = int(value)
    if (
        steamid >> 56 != 1
        or (steamid >> 52) & 15 not in {3, 4}
        or not steamid & 0xFFFFFFFF
    ):
        raise ValueError("Expected an authenticated Steam game-server ID")
    return value


ServerSteamID = Annotated[
    str,
    StringConstraints(pattern=r"^[1-9][0-9]{16,19}$"),
    AfterValidator(validate_server_steamid),
]
