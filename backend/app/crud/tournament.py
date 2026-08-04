import uuid
from datetime import date

from sqlalchemy.exc import IntegrityError
from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import (
    AdminTournamentAchievementPublic,
    Player,
    PlayerRefPublic,
    Tournament,
    TournamentAchievement,
    TournamentAchievementPublic,
    TournamentCreate,
    TournamentPublic,
    TournamentUpdate,
)
from app.models.utils import get_datetime_utc


class TournamentAchievementConflictError(ValueError):
    pass


async def get_tournament(*, session: AsyncSession, id: uuid.UUID) -> Tournament | None:
    return await session.get(Tournament, id)


async def get_tournament_achievement(
    *, session: AsyncSession, id: uuid.UUID
) -> TournamentAchievement | None:
    return await session.get(TournamentAchievement, id)


async def read_tournaments(
    *, session: AsyncSession, offset: int, limit: int
) -> tuple[list[Tournament], int]:
    count = int(
        (await session.exec(select(func.count()).select_from(Tournament))).one()
    )
    statement = (
        select(Tournament)
        .order_by(col(Tournament.ends_on).desc(), col(Tournament.id).desc())
        .offset(offset)
        .limit(limit)
    )
    return list((await session.exec(statement)).all()), count


async def create_tournament(
    *, session: AsyncSession, tournament_in: TournamentCreate
) -> Tournament:
    tournament = Tournament(**tournament_in.model_dump())
    session.add(tournament)
    await session.commit()
    await session.refresh(tournament)
    return tournament


async def update_tournament(
    *, session: AsyncSession, tournament: Tournament, tournament_in: TournamentUpdate
) -> Tournament:
    changes = tournament_in.model_dump(exclude_unset=True)
    starts_on = changes.get("starts_on", tournament.starts_on)
    ends_on = changes.get("ends_on", tournament.ends_on)
    if ends_on is None:
        ends_on = starts_on
        changes["ends_on"] = ends_on
    if not isinstance(starts_on, date) or not isinstance(ends_on, date):
        raise ValueError("Tournament dates are invalid")
    if ends_on < starts_on:
        raise ValueError("ends_on must not be before starts_on")

    for key, value in changes.items():
        setattr(tournament, key, value)
    tournament.updated_at = get_datetime_utc()
    session.add(tournament)
    await session.commit()
    await session.refresh(tournament)
    return tournament


async def delete_tournament(*, session: AsyncSession, tournament: Tournament) -> None:
    await session.delete(tournament)
    await session.commit()


async def create_tournament_achievement(
    *,
    session: AsyncSession,
    tournament_id: uuid.UUID,
    player_steamid64: int,
    placement: int,
) -> TournamentAchievement:
    achievement = TournamentAchievement(
        tournament_id=tournament_id,
        player_steamid64=player_steamid64,
        placement=placement,
    )
    session.add(achievement)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise TournamentAchievementConflictError(
            "This player already has an achievement for this tournament"
        ) from exc
    await session.refresh(achievement)
    return achievement


async def update_tournament_achievement(
    *,
    session: AsyncSession,
    achievement: TournamentAchievement,
    placement: int,
) -> TournamentAchievement:
    achievement.placement = placement
    achievement.updated_at = get_datetime_utc()
    session.add(achievement)
    await session.commit()
    await session.refresh(achievement)
    return achievement


async def delete_tournament_achievement(
    *, session: AsyncSession, achievement: TournamentAchievement
) -> None:
    await session.delete(achievement)
    await session.commit()


async def read_player_tournament_achievements(
    *, session: AsyncSession, player_steamid64: int
) -> list[tuple[TournamentAchievement, Tournament]]:
    statement = (
        select(TournamentAchievement, Tournament)
        .join(
            Tournament, col(Tournament.id) == col(TournamentAchievement.tournament_id)
        )
        .where(col(TournamentAchievement.player_steamid64) == player_steamid64)
        .order_by(col(Tournament.ends_on).desc(), col(Tournament.id).desc())
    )
    return list((await session.exec(statement)).all())


async def read_admin_tournament_achievements(
    *, session: AsyncSession, offset: int, limit: int
) -> tuple[list[tuple[TournamentAchievement, Tournament, Player]], int]:
    count = int(
        (
            await session.exec(select(func.count()).select_from(TournamentAchievement))
        ).one()
    )
    statement = (
        select(TournamentAchievement, Tournament, Player)
        .join(
            Tournament, col(Tournament.id) == col(TournamentAchievement.tournament_id)
        )
        .join(
            Player, col(Player.steamid64) == col(TournamentAchievement.player_steamid64)
        )
        .order_by(
            col(Tournament.ends_on).desc(),
            col(TournamentAchievement.placement).asc(),
            col(TournamentAchievement.id).desc(),
        )
        .offset(offset)
        .limit(limit)
    )
    return list((await session.exec(statement)).all()), count


def to_tournament_public(*, tournament: Tournament) -> TournamentPublic:
    return TournamentPublic(
        id=tournament.id,
        name=tournament.name,
        starts_on=tournament.starts_on,
        ends_on=tournament.ends_on,
        official_url=tournament.official_url,
        level=tournament.level,
        created_at=tournament.created_at,
        updated_at=tournament.updated_at,
    )


def to_tournament_achievement_public(
    *, achievement: TournamentAchievement, tournament: Tournament
) -> TournamentAchievementPublic:
    return TournamentAchievementPublic(
        id=achievement.id,
        tournament=to_tournament_public(tournament=tournament),
        placement=achievement.placement,
        created_at=achievement.created_at,
        updated_at=achievement.updated_at,
    )


def to_admin_tournament_achievement_public(
    *, achievement: TournamentAchievement, tournament: Tournament, player: Player
) -> AdminTournamentAchievementPublic:
    public = to_tournament_achievement_public(
        achievement=achievement, tournament=tournament
    )
    return AdminTournamentAchievementPublic(
        **public.model_dump(),
        player=PlayerRefPublic(
            steamid64=str(player.steamid64), display_name=player.alias or player.name
        ),
    )
