from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.services import server_query


@pytest.mark.asyncio
async def test_request_a2s_protocol_closes_transport_on_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeTransport:
        def __init__(self) -> None:
            self.close_calls = 0

        def close(self) -> None:
            self.close_calls += 1

    class _FakeConn:
        def __init__(self, transport: _FakeTransport) -> None:
            self.transport = transport

    transport = _FakeTransport()
    conn = _FakeConn(transport)

    async def _fake_create(
        address: tuple[str, int],
        timeout: float,
    ) -> _FakeConn:
        assert address == ("127.0.0.1", 27015)
        assert timeout == 5.0
        return conn

    async def _fake_request_async_impl(
        connection: _FakeConn,
        encoding: str,
        protocol: type[object],
    ) -> None:
        assert connection is conn
        assert encoding == "utf-8"
        assert protocol is object
        raise TimeoutError("boom")

    monkeypatch.setattr(server_query.A2SStreamAsync, "create", _fake_create)
    monkeypatch.setattr(server_query, "request_async_impl", _fake_request_async_impl)

    with pytest.raises(TimeoutError, match="boom"):
        await server_query.request_a2s_protocol(
            address=("127.0.0.1", 27015),
            timeout=5.0,
            encoding="utf-8",
            protocol=object,
        )

    assert transport.close_calls == 1
    assert isinstance(conn.transport, server_query._ClosedTransport)


@pytest.mark.asyncio
async def test_query_server_a2s_info_only_calls_players_when_needed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Info:
        server_name = "Test Host"
        map_name = "kz_test"
        player_count = 0
        max_players = 16
        folder = "csgo"
        game = "Counter-Strike: Global Offensive"
        app_id = 730

    calls: list[type[object]] = []

    async def _fake_request_a2s_protocol(
        *,
        address: tuple[str, int],
        timeout: float,
        encoding: str,
        protocol: type[object],
    ) -> object:
        del address, timeout, encoding
        calls.append(protocol)
        return _Info()

    monkeypatch.setattr(server_query, "request_a2s_protocol", _fake_request_a2s_protocol)

    result = await server_query.query_server_a2s_info(
        ip="127.0.0.1",
        port=27015,
        timeout=5.0,
        players_timeout=5.0,
    )

    assert result.hostname == "Test Host"
    assert result.player_count == 0
    assert result.players == []
    assert calls == [server_query.InfoProtocol]


def test_validate_server_addition_info_rejects_non_kz_map() -> None:
    with pytest.raises(server_query.ServerQueryError, match="expected one of"):
        server_query.validate_server_addition_info(
            server_query.A2SInfoResult(
                hostname="Test Host",
                map_name="de_dust2",
                player_count=0,
                max_players=16,
                players=[],
                observed_at=datetime.now(UTC),
                game_directory="csgo",
                game_name="Counter-Strike: Global Offensive",
                app_id=730,
            )
        )
