from __future__ import annotations

import ipaddress
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any, Protocol

from app.core.config import settings

try:
    from geoip2 import database as geoip2_database
    from geoip2.errors import AddressNotFoundError
except ImportError:  # pragma: no cover - exercised through runtime fallback
    geoip2_database = None

    class AddressNotFoundError(Exception):
        pass


class GeoIPCityReader(Protocol):
    def city(self, ip_address: str) -> Any: ...

    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class GeoIPLocation:
    country_code: str | None
    city_name: str | None


class GeoIPCityDatabase:
    def __init__(
        self,
        *,
        db_path: Path,
        reader_factory: Callable[[str], GeoIPCityReader | None] | None = None,
    ) -> None:
        self._db_path = db_path
        self._reader_factory = reader_factory or self._default_reader_factory
        self._reader: GeoIPCityReader | None = None
        self._reader_mtime_ns: int | None = None
        self._lock = Lock()

    def lookup(self, ip_address: str) -> GeoIPLocation | None:
        parsed_ip = _parse_public_ip(ip_address)
        if parsed_ip is None:
            return None

        reader = self._get_reader()
        if reader is None:
            return None

        try:
            response = reader.city(parsed_ip.compressed)
        except AddressNotFoundError:
            return None
        except ValueError:
            return None

        country_code = getattr(response.country, "iso_code", None)
        city_name = getattr(response.city, "name", None)
        normalized_country = (
            country_code.upper() if isinstance(country_code, str) else None
        )
        normalized_city = (
            city_name if isinstance(city_name, str) and city_name else None
        )
        if normalized_country is None and normalized_city is None:
            return None
        return GeoIPLocation(
            country_code=normalized_country,
            city_name=normalized_city,
        )

    def reset(self) -> None:
        with self._lock:
            self._close_reader_locked()

    def _get_reader(self) -> GeoIPCityReader | None:
        try:
            mtime_ns = self._db_path.stat().st_mtime_ns
        except OSError:
            with self._lock:
                self._close_reader_locked()
            return None

        with self._lock:
            if self._reader is not None and self._reader_mtime_ns == mtime_ns:
                return self._reader

            self._close_reader_locked()
            reader = self._reader_factory(str(self._db_path))
            self._reader = reader
            self._reader_mtime_ns = mtime_ns if reader is not None else None
            return self._reader

    def _close_reader_locked(self) -> None:
        if self._reader is not None:
            self._reader.close()
        self._reader = None
        self._reader_mtime_ns = None

    @staticmethod
    def _default_reader_factory(db_path: str) -> GeoIPCityReader | None:
        if geoip2_database is None:
            return None
        try:
            return geoip2_database.Reader(db_path)
        except OSError:
            return None


def _parse_public_ip(
    ip_address: str,
) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        parsed_ip = ipaddress.ip_address(ip_address)
    except ValueError:
        return None
    if not parsed_ip.is_global:
        return None
    return parsed_ip


_geoip_city_database = GeoIPCityDatabase(db_path=settings.GEOIP_CITY_DB_PATH)


def lookup_geoip_city(ip_address: str) -> GeoIPLocation | None:
    return _geoip_city_database.lookup(ip_address)


def reset_geoip_city_database_for_tests() -> None:
    _geoip_city_database.reset()
