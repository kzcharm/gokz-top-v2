"""Inspect uncertain identities, or verify an operator-supplied upstream claim."""

import argparse
import asyncio
import json
import logging
import uuid

from sqlmodel import col, select

from app.core.db import async_session_maker
from app.models import RecordSourceClaim
from app.services.record_reconciliation import reconcile_claim


async def run(
    record_uuid: uuid.UUID | None, upstream_id: int | None, limit: int
) -> None:
    async with async_session_maker() as session:
        if record_uuid and upstream_id:
            claim = (
                await session.exec(
                    select(RecordSourceClaim).where(
                        RecordSourceClaim.record_uuid == record_uuid,
                        RecordSourceClaim.globalapi_id == upstream_id,
                    )
                )
            ).first()
            if claim is None:
                claim = RecordSourceClaim(
                    record_uuid=record_uuid, globalapi_id=upstream_id
                )
                session.add(claim)
                await session.flush()
            await reconcile_claim(session, claim)
            await session.commit()
            logging.warning("identity=%s", json.dumps(claim.model_dump(mode="json")))
            return
        query = (
            select(RecordSourceClaim)
            .where(col(RecordSourceClaim.state) != "verified")
            .order_by(col(RecordSourceClaim.created_at))
            .limit(limit)
        )
        if record_uuid:
            query = query.where(RecordSourceClaim.record_uuid == record_uuid)
        for claim in (await session.exec(query)).all():
            logging.warning("identity=%s", json.dumps(claim.model_dump(mode="json")))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", type=uuid.UUID)
    parser.add_argument("--verify-upstream", type=int)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    if not 1 <= args.limit <= 10000 or (args.verify_upstream and not args.record):
        parser.error("Use a bounded limit and supply --record with --verify-upstream")
    asyncio.run(run(args.record, args.verify_upstream, args.limit))


if __name__ == "__main__":
    main()
