# ruff: noqa: F403, I001
from app.importers.jump_replays_archive import *  # noqa: F403
from app.importers.jump_replays_archive import main


if __name__ == "__main__":
    raise SystemExit(main())
