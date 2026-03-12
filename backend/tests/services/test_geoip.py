from pathlib import Path
from types import SimpleNamespace

from app.services.geoip import GeoIPCityDatabase, GeoIPLocation


class _FakeReader:
    def __init__(self, *, location: GeoIPLocation) -> None:
        self._location = location
        self.closed = False

    def city(self, ip_address: str) -> SimpleNamespace:
        del ip_address
        return SimpleNamespace(
            country=SimpleNamespace(iso_code=self._location.country_code),
            city=SimpleNamespace(name=self._location.city_name),
        )

    def close(self) -> None:
        self.closed = True


def test_geoip_city_database_skips_invalid_and_private_ips(tmp_path: Path) -> None:
    database = GeoIPCityDatabase(
        db_path=tmp_path / "GeoLite2-City.mmdb",
        reader_factory=lambda _: _FakeReader(
            location=GeoIPLocation(country_code="US", city_name="Chicago")
        ),
    )

    assert database.lookup("not-an-ip") is None
    assert database.lookup("127.0.0.1") is None


def test_geoip_city_database_reloads_reader_when_file_changes(tmp_path: Path) -> None:
    db_path = tmp_path / "GeoLite2-City.mmdb"
    db_path.write_text("version-1")
    created_readers: list[_FakeReader] = []
    locations = [
        GeoIPLocation(country_code="US", city_name="Chicago"),
        GeoIPLocation(country_code="CA", city_name="Toronto"),
    ]

    def _reader_factory(_: str) -> _FakeReader:
        reader = _FakeReader(location=locations[len(created_readers)])
        created_readers.append(reader)
        return reader

    database = GeoIPCityDatabase(
        db_path=db_path,
        reader_factory=_reader_factory,
    )

    assert database.lookup("8.8.8.8") == GeoIPLocation(
        country_code="US",
        city_name="Chicago",
    )
    assert database.lookup("8.8.8.8") == GeoIPLocation(
        country_code="US",
        city_name="Chicago",
    )
    assert len(created_readers) == 1

    db_path.write_text("version-2")

    assert database.lookup("1.1.1.1") == GeoIPLocation(
        country_code="CA",
        city_name="Toronto",
    )
    assert len(created_readers) == 2
    assert created_readers[0].closed is True
