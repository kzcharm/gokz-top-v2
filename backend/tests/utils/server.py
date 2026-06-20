import random
import uuid

from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.models import (
    Server,
    ServerCreate,
    ServerGroup,
    ServerGroupCreate,
    ServerGroupStatus,
    ServerGroupUpdate,
    ServerStatus,
)
from tests.utils.user import create_random_user
from tests.utils.utils import random_lower_string


def random_server_ip() -> str:
    return f"127.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(1, 254)}"


def random_server_port() -> int:
    return random.randint(20_000, 40_000)


async def create_server_group(
    db: AsyncSession,
    *,
    name: str | None = None,
    owner_steamid64: int | None = None,
    status: ServerGroupStatus | None = None,
) -> tuple[ServerGroup, str]:
    if owner_steamid64 is None:
        owner_steamid64 = (await create_random_user(db)).steamid64
    group_name = name or f"group-{random_lower_string()[:8]}"
    group, api_key = await crud.create_server_group(
        session=db,
        group_in=ServerGroupCreate(
            name=group_name,
            custom_id=f"group-{random_lower_string()[:8]}",
        ),
        owner_steamid64=owner_steamid64,
    )
    if status is not None and status != group.status:
        group = await crud.update_server_group(
            session=db,
            group=group,
            group_in=ServerGroupUpdate(status=status),
        )
    return group, api_key


async def create_server(
    db: AsyncSession,
    *,
    group_id: uuid.UUID | None = None,
    ip: str | None = None,
    port: int | None = None,
    status: ServerStatus = ServerStatus.ENABLED,
    country: str | None = "DE",
    city: str | None = "Berlin",
    latitude: float | None = None,
    longitude: float | None = None,
    hostname: str = "Test Server",
    map_name: str = "kz_testmap",
    player_count: int = 5,
    max_players: int = 16,
) -> Server:
    return await crud.create_server(
        session=db,
        server_in=ServerCreate(
            group_id=group_id,
            ip=ip or random_server_ip(),
            port=port or random_server_port(),
            status=status,
            country=country,
            city=city,
            latitude=latitude,
            longitude=longitude,
        ),
        steamid64=76561198000000001,
        queried_hostname=hostname,
        queried_map=map_name,
        queried_player_count=player_count,
        queried_max_players=max_players,
        queried_players=[],
    )
