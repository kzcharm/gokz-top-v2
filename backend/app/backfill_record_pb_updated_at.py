import argparse
import asyncio
import logging

from sqlalchemy import text

from app.core.db import async_session_maker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


BACKFILL_SQL = text(
    """
    UPDATE record_pb
    SET updated_at = record.created_at
    FROM record
    WHERE record.uuid = record_pb.record_uuid
      AND record_pb.updated_at IS DISTINCT FROM record.created_at
    """
)

COUNT_SQL = text(
    """
    SELECT COUNT(*)
    FROM record_pb
    JOIN record ON record.uuid = record_pb.record_uuid
    WHERE record_pb.updated_at IS DISTINCT FROM record.created_at
    """
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Backfill record_pb.updated_at from the linked record.created_at.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report how many rows would change without updating them.",
    )
    return parser


async def _main_async(argv: list[str] | None = None) -> None:
    args = _build_parser().parse_args(argv)
    async with async_session_maker() as session:
        pending_rows = (await session.exec(COUNT_SQL)).one()[0]
        if args.dry_run:
            logger.info("record_pb updated_at backfill would update %s rows", pending_rows)
            return

        result = await session.exec(BACKFILL_SQL)
        await session.commit()
        logger.info(
            "record_pb updated_at backfill updated %s rows",
            result.rowcount if result.rowcount is not None else pending_rows,
        )


def main(argv: list[str] | None = None) -> None:
    asyncio.run(_main_async(argv))


if __name__ == "__main__":
    main()
