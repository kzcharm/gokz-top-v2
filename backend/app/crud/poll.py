import uuid
from datetime import UTC, datetime

from sqlalchemy import func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import (
    AdminPollPublic,
    Player,
    Poll,
    PollCreate,
    PollListQuery,
    PollOption,
    PollOptionPublic,
    PollPublic,
    PollStatus,
    PollUpdate,
    PollVote,
    PollVoterPublic,
)
from app.models.utils import get_datetime_utc


def _now() -> datetime:
    return datetime.now(UTC)


async def get_poll(session: AsyncSession, poll_id: uuid.UUID) -> Poll | None:
    return (
        await session.exec(
            select(Poll).where(
                col(Poll.id) == poll_id,
                col(Poll.deleted_at).is_(None),
            )
        )
    ).first()


async def _options(session: AsyncSession, poll_id: uuid.UUID) -> list[PollOption]:
    return list(
        (
            await session.exec(
                select(PollOption)
                .where(col(PollOption.poll_id) == poll_id)
                .order_by(col(PollOption.position))
            )
        ).all()
    )


async def _votes(session: AsyncSession, poll_id: uuid.UUID) -> list[PollVote]:
    return list(
        (
            await session.exec(select(PollVote).where(col(PollVote.poll_id) == poll_id))
        ).all()
    )


def _is_closed(poll: Poll) -> bool:
    return poll.status == PollStatus.CLOSED or (
        poll.ends_at is not None and poll.ends_at <= _now()
    )


async def create_poll(
    session: AsyncSession, poll_in: PollCreate, created_by_steamid64: int | None = None
) -> Poll:
    now = get_datetime_utc()
    poll = Poll(
        **poll_in.model_dump(exclude={"options"}),
        created_by_steamid64=created_by_steamid64,
        created_at=now,
        updated_at=now,
        last_activity_at=now,
    )
    session.add(poll)
    await session.flush()
    for position, option in enumerate(poll_in.options):
        session.add(
            PollOption(poll_id=poll.id, position=position, **option.model_dump())
        )
    await session.commit()
    await session.refresh(poll)
    return poll


async def update_poll(session: AsyncSession, poll: Poll, poll_in: PollUpdate) -> Poll:
    changes = poll_in.model_dump(exclude_unset=True, exclude={"options"})
    option_count = (
        len(poll_in.options)
        if poll_in.options is not None
        else len(await _options(session, poll.id))
    )
    effective_max_selections = (
        poll_in.max_selections
        if poll_in.max_selections is not None
        else poll.max_selections
    )
    if effective_max_selections != 0 and effective_max_selections > option_count:
        raise ValueError("max_selections cannot exceed the number of options")
    if "status" in changes:
        if changes["status"] == PollStatus.CLOSED:
            poll.closed_at = get_datetime_utc()
        elif changes["status"] == PollStatus.ACTIVE:
            poll.closed_at = None
            if poll.ends_at is not None and poll.ends_at <= _now():
                poll.ends_at = None
    for key, value in changes.items():
        setattr(poll, key, value)
    if poll_in.options is not None:
        existing_votes = await session.exec(
            select(func.count())
            .select_from(PollVote)
            .where(col(PollVote.poll_id) == poll.id)
        )
        if int(existing_votes.one()) == 0:
            options = await _options(session, poll.id)
            for option in options:
                await session.delete(option)
            for position, option_input in enumerate(poll_in.options):
                session.add(
                    PollOption(
                        poll_id=poll.id, position=position, **option_input.model_dump()
                    )
                )
        else:
            raise ValueError("Poll options cannot be edited after the first vote")
    poll.updated_at = get_datetime_utc()
    poll.last_activity_at = poll.updated_at
    session.add(poll)
    await session.commit()
    await session.refresh(poll)
    return poll


async def delete_poll(session: AsyncSession, poll: Poll) -> None:
    poll.deleted_at = get_datetime_utc()
    poll.updated_at = poll.deleted_at
    session.add(poll)
    await session.commit()


async def read_polls(
    session: AsyncSession, query: PollListQuery
) -> tuple[list[Poll], int]:
    filters = [col(Poll.deleted_at).is_(None)]
    if query.status is not None:
        if query.status == PollStatus.ACTIVE:
            filters.extend(
                [
                    col(Poll.status) == PollStatus.ACTIVE,
                    (col(Poll.ends_at).is_(None) | (col(Poll.ends_at) > _now())),
                ]
            )
        else:
            filters.append(
                (col(Poll.status) == PollStatus.CLOSED)
                | (col(Poll.ends_at).is_not(None) & (col(Poll.ends_at) <= _now()))
            )
    count = int(
        (
            await session.exec(select(func.count()).select_from(Poll).where(*filters))
        ).one()
    )
    if query.sort == "activity":
        order = (col(Poll.last_activity_at).desc(), col(Poll.id).desc())
    elif query.sort == "votes":
        order = (
            select(func.count())
            .where(col(PollVote.poll_id) == col(Poll.id))
            .correlate(Poll)
            .scalar_subquery()
            .desc(),
            col(Poll.id).desc(),
        )
    else:
        order = (col(Poll.created_at).desc(), col(Poll.id).desc())
    rows = await session.exec(
        select(Poll)
        .where(*filters)
        .order_by(*order)
        .offset(query.offset)
        .limit(query.limit)
    )
    return list(rows.all()), count


async def get_vote(
    session: AsyncSession, poll_id: uuid.UUID, steamid64: int
) -> PollVote | None:
    return (
        await session.exec(
            select(PollVote).where(
                col(PollVote.poll_id) == poll_id,
                col(PollVote.user_steamid64) == steamid64,
            )
        )
    ).first()


async def cast_vote(
    session: AsyncSession, poll: Poll, steamid64: int, option_ids: list[uuid.UUID]
) -> PollVote:
    options = await _options(session, poll.id)
    valid = {option.id for option in options}
    if len(set(option_ids)) != len(option_ids) or not set(option_ids).issubset(valid):
        raise ValueError("Invalid poll options")
    if poll.max_selections and len(option_ids) > poll.max_selections:
        raise ValueError(f"Select at most {poll.max_selections} options")
    vote = await get_vote(session, poll.id, steamid64)
    if vote is not None and not poll.allow_vote_change:
        raise ValueError("This poll does not allow changing your vote")
    now = get_datetime_utc()
    if vote is None:
        vote = PollVote(
            poll_id=poll.id,
            user_steamid64=steamid64,
            option_ids=[str(value) for value in option_ids],
            created_at=now,
            updated_at=now,
        )
    else:
        vote.option_ids = [str(value) for value in option_ids]
        vote.updated_at = now
    poll.last_activity_at = now
    poll.updated_at = now
    session.add(vote)
    session.add(poll)
    await session.commit()
    await session.refresh(vote)
    return vote


async def to_poll_public(
    session: AsyncSession, poll: Poll, steamid64: int | None, admin: bool = False
) -> PollPublic | AdminPollPublic:
    if _is_closed(poll) and poll.status != PollStatus.CLOSED:
        poll.status = PollStatus.CLOSED
        poll.closed_at = poll.ends_at
    options = await _options(session, poll.id)
    votes = await _votes(session, poll.id)
    current = (
        next((vote for vote in votes if vote.user_steamid64 == steamid64), None)
        if steamid64 is not None
        else None
    )
    can_results = admin or _is_closed(poll) or current is not None
    counts = {option.id: 0 for option in options}
    for vote in votes:
        for option_id in vote.option_ids:
            try:
                parsed = uuid.UUID(option_id)
            except ValueError:
                continue
            if parsed in counts:
                counts[parsed] += 1
    total = len(votes)
    voter_players = {}
    if can_results and votes:
        voter_ids = {vote.user_steamid64 for vote in votes}
        voter_players = {
            player.steamid64: player
            for player in (
                await session.exec(
                    select(Player).where(col(Player.steamid64).in_(voter_ids))
                )
            ).all()
        }
    public_options = [
        PollOptionPublic(
            id=option.id,
            label=option.label,
            description=option.description,
            position=option.position,
            votes=counts[option.id] if can_results else None,
            percentage=(
                counts[option.id] / total * 100
                if can_results and total
                else 0
                if can_results
                else None
            ),
        )
        for option in options
    ]
    base = {
        "id": poll.id,
        "created_by_steamid64": (
            str(poll.created_by_steamid64)
            if poll.created_by_steamid64 is not None
            else None
        ),
        "title": poll.title,
        "description": poll.description,
        "status": poll.status,
        "ends_at": poll.ends_at,
        "closed_at": poll.closed_at,
        "max_selections": poll.max_selections,
        "allow_vote_change": poll.allow_vote_change,
        "created_at": poll.created_at,
        "updated_at": poll.updated_at,
        "last_activity_at": poll.last_activity_at,
        "total_votes": total,
        "has_voted": current is not None,
        "selected_option_ids": [
            uuid.UUID(value) for value in (current.option_ids if current else [])
        ],
        "can_view_results": can_results,
        "options": public_options,
    }
    if can_results:
        voters = []
        for vote in votes:
            player = voter_players.get(vote.user_steamid64)
            voters.append(
                PollVoterPublic(
                    steamid64=str(vote.user_steamid64),
                    name=player.name if player else None,
                    alias=player.alias if player else None,
                    avatar_hash=player.avatar_hash if player else None,
                    option_ids=[uuid.UUID(value) for value in vote.option_ids],
                    voted_at=vote.updated_at,
                )
            )
    else:
        voters = []
    if admin:
        return AdminPollPublic(**base, voters=voters)
    return PollPublic(**base, voters=voters)
