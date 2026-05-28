import argparse
import asyncio
import logging
import uuid
from typing import Any, cast

from sqlalchemy import text

from app.core.db import async_session_maker
from app.services.geoip import lookup_geoip_city

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


SELECT_BATCH_SQL = text(
    """
    SELECT id, connected_at, host(ip_address) AS ip_address
    FROM player_session
    WHERE geo_country IS NULL
      AND geo_region IS NULL
      AND geo_city IS NULL
      AND (
        CAST(:last_connected_at AS timestamptz) IS NULL
        OR (
          connected_at,
          id::text
        ) < (
          CAST(:last_connected_at AS timestamptz),
          CAST(:last_id AS text)
        )
      )
    ORDER BY connected_at DESC, id::text DESC
    LIMIT :limit
    """
)

COUNT_PENDING_SQL = text(
    """
    SELECT COUNT(*)
    FROM player_session
    WHERE geo_country IS NULL
      AND geo_region IS NULL
      AND geo_city IS NULL
    """
)

UPDATE_SESSION_SQL = text(
    """
    UPDATE player_session
    SET geo_country = :geo_country,
        geo_region = :geo_region,
        geo_city = :geo_city
    WHERE id = :session_id
    """
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Backfill player_session GeoIP snapshot fields.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report how many rows would be scanned without updating them.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Maximum rows to process per transaction.",
    )
    return parser


async def _main_async(argv: list[str] | None = None) -> None:
    args = _build_parser().parse_args(argv)
    if args.batch_size < 1:
        raise ValueError("--batch-size must be at least 1")

    total_updated = 0
    total_scanned = 0
    async with async_session_maker() as session:
        pending_rows = (await session.exec(cast(Any, COUNT_PENDING_SQL))).one()[0]
        if args.dry_run:
            logger.info(
                "player_session GeoIP backfill would scan %s rows",
                pending_rows,
            )
            return

        last_connected_at = None
        last_id = None
        while True:
            rows = (
                await session.exec(
                    cast(Any, SELECT_BATCH_SQL),
                    params={
                        "limit": args.batch_size,
                        "last_connected_at": last_connected_at,
                        "last_id": last_id,
                    },
                )
            ).all()
            if not rows:
                break

            for row in rows:
                values = row._mapping
                location = lookup_geoip_city(values["ip_address"])
                await session.exec(
                    cast(Any, UPDATE_SESSION_SQL),
                    params={
                        "session_id": uuid.UUID(str(values["id"])),
                        "geo_country": (
                            location.country_code if location is not None else None
                        ),
                        "geo_region": (
                            location.region_name if location is not None else None
                        ),
                        "geo_city": location.city_name if location is not None else None,
                    },
                )
                total_scanned += 1
                if location is not None:
                    total_updated += 1

            last_values = rows[-1]._mapping
            last_connected_at = last_values["connected_at"]
            last_id = str(last_values["id"])
            await session.commit()

    logger.info(
        "player_session GeoIP backfill scanned %s rows and populated %s rows",
        total_scanned,
        total_updated,
    )


def main(argv: list[str] | None = None) -> None:
    asyncio.run(_main_async(argv))


if __name__ == "__main__":
    main()
