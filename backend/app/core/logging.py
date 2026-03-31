import logging

_APP_LOG_HANDLER_NAME = "gokz-top-app-handler"


def configure_app_logging(log_level: str) -> None:
    resolved_level = getattr(logging, log_level.upper(), logging.INFO)
    app_logger = logging.getLogger("app")
    app_logger.setLevel(resolved_level)

    if not any(
        getattr(handler, "name", "") == _APP_LOG_HANDLER_NAME
        for handler in app_logger.handlers
    ):
        handler = logging.StreamHandler()
        handler.set_name(_APP_LOG_HANDLER_NAME)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s [%(name)s] %(message)s",
            )
        )
        app_logger.addHandler(handler)

    app_logger.propagate = False
