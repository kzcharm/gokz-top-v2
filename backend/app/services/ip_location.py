from __future__ import annotations

import ipaddress
import math
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.services.geoip import GeoIPLocation, lookup_geoip_city

IP_LOCATION_TIMEOUT_SECONDS = 5.0


class IPProviderParser(Protocol):
    def __call__(self, payload: dict[str, Any]) -> GeoIPLocation | None: ...


class IPHTTPClient(Protocol):
    async def get(self, url: str) -> httpx.Response: ...


@dataclass(frozen=True, slots=True)
class IPProvider:
    name: str
    url_template: str
    parser: IPProviderParser

    def build_url(self, ip_address: str) -> str:
        return self.url_template.format(ip=ip_address)


def _normalize_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_country_code(value: Any) -> str | None:
    normalized = _normalize_text(value)
    if normalized is None:
        return None
    return normalized.upper()[:2] or None


def _normalize_coordinate(value: Any, *, minimum: float, maximum: float) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
    try:
        coordinate = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(coordinate) or coordinate < minimum or coordinate > maximum:
        return None
    return coordinate


def _build_location(
    *,
    country_code: Any = None,
    city_name: Any = None,
    latitude: Any = None,
    longitude: Any = None,
) -> GeoIPLocation | None:
    normalized_country = _normalize_country_code(country_code)
    normalized_city = _normalize_text(city_name)
    normalized_latitude = _normalize_coordinate(latitude, minimum=-90, maximum=90)
    normalized_longitude = _normalize_coordinate(longitude, minimum=-180, maximum=180)

    if (
        normalized_country is None
        and normalized_city is None
        and normalized_latitude is None
        and normalized_longitude is None
    ):
        return None

    return GeoIPLocation(
        country_code=normalized_country,
        city_name=normalized_city,
        latitude=normalized_latitude,
        longitude=normalized_longitude,
    )


def _parse_ip_sb(payload: dict[str, Any]) -> GeoIPLocation | None:
    return _build_location(
        country_code=payload.get("country_code"),
        city_name=payload.get("city"),
        latitude=payload.get("latitude"),
        longitude=payload.get("longitude"),
    )


def _parse_ipapi_co(payload: dict[str, Any]) -> GeoIPLocation | None:
    return _build_location(
        country_code=payload.get("country_code") or payload.get("country"),
        city_name=payload.get("city"),
        latitude=payload.get("latitude"),
        longitude=payload.get("longitude"),
    )


def _parse_freeipapi(payload: dict[str, Any]) -> GeoIPLocation | None:
    return _build_location(
        country_code=payload.get("countryCode"),
        city_name=payload.get("cityName"),
        latitude=payload.get("latitude"),
        longitude=payload.get("longitude"),
    )


IP_LOCATION_PROVIDERS: tuple[IPProvider, ...] = (
    IPProvider(
        name="api.ip.sb",
        url_template="https://api.ip.sb/geoip/{ip}",
        parser=_parse_ip_sb,
    ),
    IPProvider(
        name="ipapi.co",
        url_template="https://ipapi.co/{ip}/json/",
        parser=_parse_ipapi_co,
    ),
    IPProvider(
        name="freeipapi",
        url_template="https://free.freeipapi.com/api/json/{ip}",
        parser=_parse_freeipapi,
    ),
)


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


async def lookup_ip_location(
    ip_address: str,
    *,
    client: IPHTTPClient | None = None,
    providers: tuple[IPProvider, ...] = IP_LOCATION_PROVIDERS,
) -> GeoIPLocation | None:
    parsed_ip = _parse_public_ip(ip_address)
    if parsed_ip is None:
        return None

    created_client: httpx.AsyncClient | None = None
    resolved_client = client
    if resolved_client is None:
        created_client = httpx.AsyncClient(
            timeout=IP_LOCATION_TIMEOUT_SECONDS,
            trust_env=False,
        )
        resolved_client = created_client
    try:
        for provider in providers:
            try:
                response = await resolved_client.get(provider.build_url(parsed_ip.compressed))
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError):
                continue
            if not isinstance(payload, dict):
                continue

            location = provider.parser(payload)
            if location is not None:
                return location
    finally:
        if created_client is not None:
            await created_client.aclose()

    return lookup_geoip_city(parsed_ip.compressed)
