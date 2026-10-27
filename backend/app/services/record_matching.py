"""Conservative compatibility matching for plugins without upstream identity receipts."""

from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import (
    Record,
    RecordUploadReceipt,
    Server,
    ServerGlobalapi,
    ServerGroup,
    ServerGroupStatus,
)

# Both timestamps have second precision. Cap future client clocks at receipt time;
# never expand the window to accommodate arbitrary historical clock offsets.
MATCH_WINDOW = timedelta(seconds=5)
RECEIPT_DELAY_WINDOW = timedelta(seconds=30)
LEGACY_PRECISION = Decimal("0.001")


async def same_owner(session: AsyncSession, native: Record, upstream: Record) -> bool:
    server = (
        await session.get(Server, native.native_server_id)
        if native.native_server_id
        else None
    )
    source = (
        await session.get(ServerGlobalapi, upstream.server_id)
        if upstream.server_id
        else None
    )
    if not server or not source or server.group_id != source.group_id:
        return False
    group = await session.get(ServerGroup, server.group_id)
    return bool(group and group.status == ServerGroupStatus.VALIDATED)


def statistics_match(native: Record, upstream: Record, *, legacy: bool = False) -> bool:
    if any(
        getattr(native, field) != getattr(upstream, field)
        for field in ("steamid64", "map_id", "stage", "mode", "teleports")
    ):
        return False
    # Client float serialization and upstream millisecond conversion can differ
    # by one millisecond in either direction. All other statistics remain exact.
    return native.time == upstream.time or (
        legacy and abs(native.time - upstream.time) <= LEGACY_PRECISION
    )


def finish_window(native: Record, received_at: datetime) -> tuple[datetime, datetime]:
    if native.created_at > received_at + MATCH_WINDOW:
        # A fast client clock leaves receipt time as the useful anchor. The
        # plugin's queue/check cycle can delay delivery beyond five seconds.
        # Bound that delay, and require a run longer than the entire interval
        # below so this cannot collapse rapid repeated finishes.
        return received_at - RECEIPT_DELAY_WINDOW, received_at + MATCH_WINDOW
    effective = min(native.created_at, received_at)
    return effective - MATCH_WINDOW, effective + MATCH_WINDOW


async def unique_compatible_pair(
    session: AsyncSession, native: Record, upstream: Record, received_at: datetime
) -> bool:
    start, end = finish_window(native, received_at)
    if min(native.time, upstream.time) <= Decimal(str((end - start).total_seconds())):
        # Whole-second timestamps cannot distinguish rapid repeated short runs.
        return False
    if not statistics_match(native, upstream, legacy=True) or not await same_owner(
        session, native, upstream
    ):
        return False
    if not start <= upstream.created_at <= end:
        return False
    # Check both directions, including already linked records. Two finishes in
    # this window remain ambiguous, even if one happened to arrive first.
    base = (
        Record.steamid64 == upstream.steamid64,
        Record.map_id == upstream.map_id,
        Record.stage == upstream.stage,
        Record.mode == upstream.mode,
        Record.teleports == upstream.teleports,
    )
    mirrors = (
        await session.exec(
            select(Record)
            .where(
                *base,
                Record.time >= native.time - LEGACY_PRECISION,
                Record.time <= native.time + LEGACY_PRECISION,
                col(Record.id).is_not(None),
                Record.created_at >= start,
                Record.created_at <= end,
            )
            .limit(3)
        )
    ).all()
    if len(mirrors) >= 3:
        return False
    for other in mirrors:
        if other.id != upstream.id and await same_owner(session, native, other):
            return False
    # Native candidates may come from multiple game instances in the group.
    natives = (
        await session.exec(
            select(Record, RecordUploadReceipt.created_at)
            .join(
                RecordUploadReceipt,
                col(RecordUploadReceipt.record_uuid) == col(Record.uuid),
            )
            .where(
                *base,
                Record.time >= upstream.time - LEGACY_PRECISION,
                Record.time <= upstream.time + LEGACY_PRECISION,
                func.least(Record.created_at, RecordUploadReceipt.created_at)
                >= upstream.created_at - MATCH_WINDOW,
                func.least(Record.created_at, RecordUploadReceipt.created_at)
                <= upstream.created_at + RECEIPT_DELAY_WINDOW,
            )
            .limit(100)
        )
    ).all()
    for other, other_received_at in natives:
        other_start, other_end = finish_window(other, other_received_at)
        if (
            other.uuid != native.uuid
            and other_start <= upstream.created_at <= other_end
            and await same_owner(session, other, upstream)
        ):
            return False
    return len(natives) < 100


async def upstream_match(
    session: AsyncSession, native: Record, received_at: datetime
) -> Record | None:
    start, end = finish_window(native, received_at)
    candidates = (
        await session.exec(
            select(Record)
            .where(
                Record.steamid64 == native.steamid64,
                Record.map_id == native.map_id,
                Record.stage == native.stage,
                Record.mode == native.mode,
                Record.teleports == native.teleports,
                Record.time >= native.time - LEGACY_PRECISION,
                Record.time <= native.time + LEGACY_PRECISION,
                col(Record.id).is_not(None),
                col(Record.native_server_id).is_(None),
                Record.created_at >= start,
                Record.created_at <= end,
            )
            .limit(100)
        )
    ).all()
    if len(candidates) >= 100:
        return None
    matches = [
        candidate
        for candidate in candidates
        if await unique_compatible_pair(session, native, candidate, received_at)
    ]
    return matches[0] if len(matches) == 1 else None


async def native_match(session: AsyncSession, upstream: Record) -> Record | None:
    candidates = (
        await session.exec(
            select(Record, RecordUploadReceipt.created_at)
            .join(
                RecordUploadReceipt,
                col(RecordUploadReceipt.record_uuid) == col(Record.uuid),
            )
            .where(
                Record.steamid64 == upstream.steamid64,
                Record.map_id == upstream.map_id,
                Record.stage == upstream.stage,
                Record.mode == upstream.mode,
                Record.teleports == upstream.teleports,
                Record.time >= upstream.time - LEGACY_PRECISION,
                Record.time <= upstream.time + LEGACY_PRECISION,
                col(Record.id).is_(None),
                func.least(Record.created_at, RecordUploadReceipt.created_at)
                >= upstream.created_at - MATCH_WINDOW,
                func.least(Record.created_at, RecordUploadReceipt.created_at)
                <= upstream.created_at + RECEIPT_DELAY_WINDOW,
            )
            .limit(100)
        )
    ).all()
    if len(candidates) >= 100:
        return None
    matches = [
        native
        for native, received_at in candidates
        if await unique_compatible_pair(session, native, upstream, received_at)
    ]
    return matches[0] if len(matches) == 1 else None
