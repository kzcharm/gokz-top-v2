"""Inspect uncertain identities, or verify an operator-supplied upstream claim."""

import argparse
import asyncio
import json
import logging
import uuid

from sqlmodel import col, select

from app.core.db import async_session_maker
from app.models import RecordSourceClaim, RecordUploadReceipt
from app.services.record_reconciliation import reconcile_claim


async def run(
    record_uuid: uuid.UUID | None,
    upstream_id: int | None,
    limit: int,
    compatible: bool = False,
    apply: bool = False,
    after: uuid.UUID | None = None,
) -> None:
    async with async_session_maker() as session:
        if compatible:
            from app.services.record_reconciliation import reconcile_compatible_receipt

            statement = (
                select(RecordUploadReceipt)
                .order_by(col(RecordUploadReceipt.id))
                .limit(limit)
            )
            if after:
                statement = statement.where(RecordUploadReceipt.id > after)
            receipts = (await session.exec(statement)).all()
            matched = 0
            for receipt in receipts:
                matched += int(
                    await reconcile_compatible_receipt(session, receipt, apply=apply)
                )
                await session.commit()
            logging.warning(
                "compatibility=%s",
                json.dumps(
                    {
                        "scanned": len(receipts),
                        "matched": matched,
                        "apply": apply,
                        "next": str(receipts[-1].id) if receipts else None,
                    }
                ),
            )
            return
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
    parser.add_argument("--reconcile-compatible", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--after", type=uuid.UUID)
    args = parser.parse_args()
    if not 1 <= args.limit <= 10000 or (args.verify_upstream and not args.record):
        parser.error("Use a bounded limit and supply --record with --verify-upstream")
    asyncio.run(
        run(
            args.record,
            args.verify_upstream,
            args.limit,
            args.reconcile_compatible,
            args.apply,
            args.after,
        )
    )


if __name__ == "__main__":
    main()
