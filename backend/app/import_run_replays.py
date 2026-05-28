# ruff: noqa: F403, I001
from app.importers.run_replays import *  # noqa: F403
from app.importers.run_replays import main


if __name__ == "__main__":
    raise SystemExit(main())
