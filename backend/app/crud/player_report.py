import uuid

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models import (
    Map,
    ModeScope,
    PlayerNotificationType,
    PlayerReport,
    PlayerReportCreate,
    PlayerReportPublic,
    Record,
    RecordType,
    User,
    UserRole,
    normalize_player_report_description,
    normalize_user_roles,
)

from .player import get_player_by_steamid64
from .player_notification import COMMENT_PREVIEW_LENGTH, create_player_notification


class PlayerReportError(ValueError):
    pass


class PlayerReportTargetNotFoundError(PlayerReportError):
    pass


class PlayerReportRecordNotFoundError(PlayerReportError):
    pass


class PlayerReportRecordTargetMismatchError(PlayerReportError):
    pass


def to_player_report_public(*, report: PlayerReport) -> PlayerReportPublic:
    return PlayerReportPublic(
        id=report.id,
        reporter_steamid64=str(report.reporter_steamid64),
        target_steamid64=str(report.target_steamid64),
        record_uuid=report.record_uuid,
        description=report.description,
        created_at=report.created_at,
    )


def _preview_description(description: str | None) -> str | None:
    normalized = " ".join((description or "").strip().split())
    return normalized[:COMMENT_PREVIEW_LENGTH] or None


def _report_target_url(*, target_steamid64: int, record_uuid: uuid.UUID | None) -> str:
    if record_uuid is not None:
        return f"/profile/{target_steamid64}/records"
    return f"/profile/{target_steamid64}"


async def _read_player_report_notification_recipient_ids(
    *, session: AsyncSession
) -> list[int]:
    statement = select(User.steamid64, User.roles).where(col(User.is_active).is_(True))
    rows = (await session.exec(statement)).all()
    recipients: list[int] = []
    for steamid64, roles in rows:
        normalized_roles = normalize_user_roles(roles)
        if (
            steamid64 == settings.SUPER_USER_STEAMID64
            or UserRole.ADMIN in normalized_roles
            or UserRole.SUPERUSER in normalized_roles
        ):
            recipients.append(steamid64)
    return list(dict.fromkeys(recipients))


async def create_player_report(
    *,
    session: AsyncSession,
    reporter_steamid64: int,
    report_in: PlayerReportCreate,
) -> PlayerReport:
    description = normalize_player_report_description(report_in.description)

    try:
        target_steamid64 = int(report_in.target_steamid64)
    except ValueError as exc:
        raise PlayerReportTargetNotFoundError("Player not found") from exc

    target_player = await get_player_by_steamid64(
        session=session,
        steamid64=target_steamid64,
    )
    if target_player is None:
        raise PlayerReportTargetNotFoundError("Player not found")

    record: Record | None = None
    record_map: Map | None = None
    if report_in.record_uuid is not None:
        record = await session.get(Record, report_in.record_uuid)
        if record is None:
            raise PlayerReportRecordNotFoundError("Record not found")
        if record.steamid64 != target_steamid64:
            raise PlayerReportRecordTargetMismatchError(
                "Record does not belong to the reported player"
            )
        record_map = await session.get(Map, record.map_id)

    report = PlayerReport(
        reporter_steamid64=reporter_steamid64,
        target_steamid64=target_steamid64,
        record_uuid=report_in.record_uuid,
        description=description,
    )
    session.add(report)
    await session.flush()

    target_url = _report_target_url(
        target_steamid64=target_steamid64,
        record_uuid=report.record_uuid,
    )
    recipient_ids = await _read_player_report_notification_recipient_ids(
        session=session
    )
    for recipient_steamid64 in recipient_ids:
        await create_player_notification(
            session=session,
            recipient_steamid64=recipient_steamid64,
            actor_steamid64=reporter_steamid64,
            type=PlayerNotificationType.PLAYER_REPORT,
            source_key=f"player-report:{report.id}:{recipient_steamid64}",
            target_url=target_url,
            target_player_steamid64=target_steamid64,
            comment_preview=_preview_description(description),
            map_id=record.map_id if record is not None else None,
            map_name=record_map.name if record_map is not None else None,
            scope=ModeScope(record.mode.value) if record is not None else None,
            record_type=(
                RecordType.PRO
                if record is not None and record.teleports == 0
                else RecordType.NUB
                if record is not None
                else None
            ),
            new_record_uuid=report.record_uuid,
            new_record_time=record.time if record is not None else None,
            commit=False,
        )

    await session.commit()
    await session.refresh(report)
    return report
