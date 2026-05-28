import pytest
from httpx import AsyncClient

from app.api.v1 import misc as misc_routes
from app.services.geoip import GeoIPLookupDetails

pytestmark = pytest.mark.asyncio


def _fake_addrinfo(ip: str) -> list[tuple[int, int, int, str, tuple[str, int]]]:
    return [
        (
            2,
            1,
            6,
            "",
            (ip, 0),
        )
    ]


async def test_lookup_ip_get_direct_public_ip_with_geoip_hit(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        misc_routes,
        "lookup_geoip_details",
        lambda ip: GeoIPLookupDetails(
            country_name="Germany",
            country_code="DE",
            subdivision_name="Berlin",
            city_name="Berlin",
        ),
    )

    response = await client.get("/v1/misc/ip/8.8.8.8")

    assert response.status_code == 200
    assert response.json() == {
        "ip": "8.8.8.8",
        "country": "Germany",
        "country_code": "DE",
        "region": "Berlin",
        "city": "Berlin",
        "region_name": "Europe",
        "region_code": "EU",
    }


async def test_lookup_ip_get_resolves_hostname(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        misc_routes.socket,
        "getaddrinfo",
        lambda *args, **kwargs: _fake_addrinfo("1.1.1.1"),
    )
    monkeypatch.setattr(
        misc_routes,
        "lookup_geoip_details",
        lambda ip: GeoIPLookupDetails(
            country_name="Australia",
            country_code="AU",
            subdivision_name="Queensland",
            city_name="South Brisbane",
        ),
    )

    response = await client.get("/v1/misc/ip/example.com")

    assert response.status_code == 200
    assert response.json() == {
        "ip": "1.1.1.1",
        "country": "Australia",
        "country_code": "AU",
        "region": "Queensland",
        "city": "South Brisbane",
        "region_name": "Oceania",
        "region_code": "OC",
    }


async def test_lookup_ip_get_geoip_miss_returns_null_location_fields(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        misc_routes,
        "lookup_geoip_details",
        lambda ip: None,
    )

    response = await client.get("/v1/misc/ip/8.8.4.4")

    assert response.status_code == 200
    assert response.json() == {
        "ip": "8.8.4.4",
        "country": None,
        "country_code": None,
        "region": None,
        "city": None,
        "region_name": None,
        "region_code": None,
    }


async def test_lookup_ip_get_unresolvable_hostname_returns_400(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise(*_args: object, **_kwargs: object) -> list[object]:
        raise OSError("no host")

    monkeypatch.setattr(misc_routes.socket, "getaddrinfo", _raise)

    response = await client.get("/v1/misc/ip/not-a-real-host.invalid")

    assert response.status_code == 400
    assert response.json() == {
        "detail": "Unable to resolve address: not-a-real-host.invalid"
    }


async def test_lookup_ip_post_returns_ordered_results_for_mixed_valid_inputs(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        misc_routes.socket,
        "getaddrinfo",
        lambda *args, **kwargs: _fake_addrinfo("1.1.1.1"),
    )

    def _lookup(ip: str) -> GeoIPLookupDetails | None:
        if ip == "8.8.8.8":
            return GeoIPLookupDetails(
                country_name="Germany",
                country_code="DE",
                subdivision_name="Berlin",
                city_name="Berlin",
            )
        if ip == "1.1.1.1":
            return GeoIPLookupDetails(
                country_name="Australia",
                country_code="AU",
                subdivision_name="Queensland",
                city_name="South Brisbane",
            )
        return None

    monkeypatch.setattr(misc_routes, "lookup_geoip_details", _lookup)

    response = await client.post(
        "/v1/misc/ip",
        json={"addresses": ["8.8.8.8", "example.com"]},
    )

    assert response.status_code == 200
    assert response.json() == [
        {
            "ip": "8.8.8.8",
            "country": "Germany",
            "country_code": "DE",
            "region": "Berlin",
            "city": "Berlin",
            "region_name": "Europe",
            "region_code": "EU",
        },
        {
            "ip": "1.1.1.1",
            "country": "Australia",
            "country_code": "AU",
            "region": "Queensland",
            "city": "South Brisbane",
            "region_name": "Oceania",
            "region_code": "OC",
        },
    ]


async def test_lookup_ip_get_legacy_gokz_top_v1_path(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        misc_routes,
        "lookup_geoip_details",
        lambda ip: GeoIPLookupDetails(
            country_name="Germany",
            country_code="DE",
            subdivision_name="Berlin",
            city_name="Berlin",
        ),
    )

    response = await client.get("/api/v1/misc/ip/8.8.8.8")

    assert response.status_code == 200
    assert response.json() == {
        "ip": "8.8.8.8",
        "country": "Germany",
        "country_code": "DE",
        "region": "Berlin",
        "city": "Berlin",
        "region_name": "Europe",
        "region_code": "EU",
    }


async def test_lookup_ip_post_legacy_gokz_top_v1_path(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        misc_routes,
        "lookup_geoip_details",
        lambda ip: GeoIPLookupDetails(
            country_name="Germany",
            country_code="DE",
            subdivision_name="Berlin",
            city_name="Berlin",
        ),
    )

    response = await client.post(
        "/api/v1/misc/ip",
        json={"addresses": ["8.8.8.8"]},
    )

    assert response.status_code == 200
    assert response.json() == [
        {
            "ip": "8.8.8.8",
            "country": "Germany",
            "country_code": "DE",
            "region": "Berlin",
            "city": "Berlin",
            "region_name": "Europe",
            "region_code": "EU",
        }
    ]


async def test_lookup_ip_post_fails_on_first_invalid_item(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise(*_args: object, **_kwargs: object) -> list[object]:
        raise OSError("no host")

    monkeypatch.setattr(misc_routes.socket, "getaddrinfo", _raise)

    response = await client.post(
        "/v1/misc/ip",
        json={"addresses": ["8.8.8.8", "not-a-real-host.invalid"]},
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "Unable to resolve address: not-a-real-host.invalid"
    }
