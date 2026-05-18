from __future__ import annotations

import ipaddress
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any, Protocol, cast

from app.core.config import settings

geoip2_database: Any
GeoIPAddressNotFoundError: type[Exception]
try:
    from geoip2 import database as geoip2_database
    from geoip2.errors import AddressNotFoundError

    GeoIPAddressNotFoundError = AddressNotFoundError
except ImportError:  # pragma: no cover - exercised through runtime fallback
    geoip2_database = None

    class FallbackGeoIPAddressNotFoundError(Exception):
        pass

    GeoIPAddressNotFoundError = FallbackGeoIPAddressNotFoundError


class GeoIPCityReader(Protocol):
    def city(self, ip_address: str) -> Any: ...

    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class GeoIPLocation:
    country_code: str | None
    region_name: str | None = None
    city_name: str | None = None


@dataclass(frozen=True, slots=True)
class GeoIPLookupDetails:
    country_name: str | None
    country_code: str | None
    subdivision_name: str | None = None
    city_name: str | None = None


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
        details = self.lookup_details(ip_address)
        if details is None:
            return None
        return GeoIPLocation(
            country_code=details.country_code,
            region_name=details.subdivision_name,
            city_name=details.city_name,
        )

    def lookup_details(self, ip_address: str) -> GeoIPLookupDetails | None:
        parsed_ip = _parse_public_ip(ip_address)
        if parsed_ip is None:
            return None

        reader = self._get_reader()
        if reader is None:
            return None

        try:
            response = reader.city(parsed_ip.compressed)
        except GeoIPAddressNotFoundError:
            return None
        except ValueError:
            return None

        country_name = getattr(response.country, "name", None)
        registered_country = getattr(response, "registered_country", None)
        if not isinstance(country_name, str) or not country_name:
            registered_name = getattr(registered_country, "name", None)
            country_name = registered_name if isinstance(registered_name, str) else None

        country_code = getattr(response.country, "iso_code", None)
        if not isinstance(country_code, str) or not country_code:
            registered_code = getattr(registered_country, "iso_code", None)
            country_code = registered_code if isinstance(registered_code, str) else None
        subdivision_name = None
        subdivisions = getattr(response, "subdivisions", None)
        if subdivisions is not None:
            most_specific = getattr(subdivisions, "most_specific", None)
            subdivision_name = getattr(most_specific, "name", None)
        city_name = getattr(response.city, "name", None)
        normalized_country_name = (
            country_name if isinstance(country_name, str) and country_name else None
        )
        normalized_country = (
            country_code.upper() if isinstance(country_code, str) else None
        )
        normalized_region = (
            subdivision_name
            if isinstance(subdivision_name, str) and subdivision_name
            else None
        )
        normalized_city = (
            city_name if isinstance(city_name, str) and city_name else None
        )
        if (
            normalized_country_name is None
            and normalized_country is None
            and normalized_region is None
            and normalized_city is None
        ):
            return None
        return GeoIPLookupDetails(
            country_name=normalized_country_name,
            country_code=normalized_country,
            subdivision_name=normalized_region,
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
            return cast(GeoIPCityReader, geoip2_database.Reader(db_path))
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


def lookup_geoip_details(ip_address: str) -> GeoIPLookupDetails | None:
    return _geoip_city_database.lookup_details(ip_address)


def reset_geoip_city_database_for_tests() -> None:
    _geoip_city_database.reset()
