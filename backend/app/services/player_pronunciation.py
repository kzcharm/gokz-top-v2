from typing import cast

from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Player, PlayerPronunciation, PlayerPronunciationPublic
from app.services import pronunciation


async def request_player_pronunciation(
    *, session: AsyncSession, player: Player, force: bool = False
) -> PlayerPronunciation:
    return cast(
        PlayerPronunciation,
        await pronunciation.request_pronunciation(
            session=session, target=player, force=force
        ),
    )


async def read_player_pronunciation(
    *, session: AsyncSession, player: Player, row: PlayerPronunciation | None
) -> PlayerPronunciationPublic:
    result = await pronunciation.read_public_pronunciation(
        session=session, target=player, row=row
    )
    return PlayerPronunciationPublic(**result.model_dump())
