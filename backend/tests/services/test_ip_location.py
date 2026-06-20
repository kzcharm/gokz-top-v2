from __future__ import annotations

from typing import Any

import httpx
import pytest

from app.services import ip_location
from app.services.geoip import GeoIPLocation
from app.services.ip_location import IPProvider, lookup_ip_location


class _FakeClient:
    def __init__(self, responses: list[httpx.Response | Exception]) -> None:
        self._responses = responses
        self.urls: list[str] = []

    async def get(self, url: str) -> httpx.Response:
        self.urls.append(url)
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _response(payload: Any, *, status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        json=payload,
        request=httpx.Request("GET", "https://example.test"),
    )


@pytest.mark.asyncio
async def test_lookup_ip_location_uses_first_valid_online_provider() -> None:
    client = _FakeClient(
        [
            _response(
                {
                    "country_code": "de",
                    "city": "Nuremberg",
                    "latitude": 49.4521,
                    "longitude": 11.0767,
                }
            )
        ]
    )

    location = await lookup_ip_location("8.8.8.8", client=client)

    assert location == GeoIPLocation(
        country_code="DE",
        city_name="Nuremberg",
        latitude=49.4521,
        longitude=11.0767,
    )
    assert client.urls == ["https://api.ip.sb/geoip/8.8.8.8"]


@pytest.mark.asyncio
async def test_lookup_ip_location_falls_through_online_provider_failures() -> None:
    client = _FakeClient(
        [
            httpx.ConnectError("network down"),
            _response({"error": True}),
            _response(
                {
                    "countryCode": "CA",
                    "cityName": "Beauharnois",
                    "latitude": "45.3168",
                    "longitude": "-73.8659",
                }
            ),
        ]
    )

    location = await lookup_ip_location("8.8.4.4", client=client)

    assert location == GeoIPLocation(
        country_code="CA",
        city_name="Beauharnois",
        latitude=45.3168,
        longitude=-73.8659,
    )
    assert client.urls == [
        "https://api.ip.sb/geoip/8.8.4.4",
        "https://ipapi.co/8.8.4.4/json/",
        "https://free.freeipapi.com/api/json/8.8.4.4",
    ]


@pytest.mark.asyncio
async def test_lookup_ip_location_uses_local_geoip_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeClient(
        [
            _response({}, status_code=429),
            _response({"reason": "rate limited"}, status_code=429),
            _response({"message": "unavailable"}, status_code=503),
        ]
    )
    fallback = GeoIPLocation(
        country_code="US",
        city_name="Chicago",
        latitude=41.8781,
        longitude=-87.6298,
    )
    monkeypatch.setattr(ip_location, "lookup_geoip_city", lambda _ip: fallback)

    assert await lookup_ip_location("1.1.1.1", client=client) == fallback


@pytest.mark.asyncio
async def test_lookup_ip_location_skips_private_and_invalid_ips() -> None:
    client = _FakeClient([_response({"country_code": "US"})])

    assert await lookup_ip_location("127.0.0.1", client=client) is None
    assert await lookup_ip_location("not-an-ip", client=client) is None
    assert client.urls == []


@pytest.mark.asyncio
async def test_lookup_ip_location_rejects_out_of_range_coordinates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = IPProvider(
        name="invalid",
        url_template="https://invalid.example/{ip}",
        parser=lambda payload: ip_location._build_location(
            country_code=payload.get("country_code"),
            city_name=payload.get("city"),
            latitude=payload.get("latitude"),
            longitude=payload.get("longitude"),
        ),
    )
    client = _FakeClient(
        [
            _response(
                {
                    "country_code": "US",
                    "city": "Chicago",
                    "latitude": 120,
                    "longitude": -200,
                }
            )
        ]
    )
    monkeypatch.setattr(ip_location, "lookup_geoip_city", lambda _ip: None)

    location = await lookup_ip_location("8.8.8.8", client=client, providers=(provider,))

    assert location == GeoIPLocation(country_code="US", city_name="Chicago")
