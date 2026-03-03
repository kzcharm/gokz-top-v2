from unittest.mock import MagicMock, patch

from app import initial_data


def test_init_uses_session_and_calls_init_db() -> None:
    session_mock = MagicMock()
    session_mock.__enter__.return_value = session_mock

    with (
        patch("app.initial_data.Session", return_value=session_mock) as session_cls,
        patch("app.initial_data.init_db") as init_db_mock,
    ):
        initial_data.init()

    session_cls.assert_called_once_with(initial_data.engine)
    init_db_mock.assert_called_once_with(session_mock)


def test_main_logs_and_calls_init() -> None:
    with (
        patch("app.initial_data.init") as init_mock,
        patch.object(initial_data.logger, "info") as logger_info,
    ):
        initial_data.main()

    init_mock.assert_called_once_with()
    logger_info.assert_any_call("Creating initial data")
    logger_info.assert_any_call("Initial data created")
