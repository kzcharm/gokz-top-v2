#!/usr/bin/env sh
set -eu

PYTHON_BIN="${PYTHON_BIN:-}"
if [ -z "$PYTHON_BIN" ]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN=python3
  elif command -v python >/dev/null 2>&1 && python -c 'import sys; raise SystemExit(0 if sys.version_info[0] >= 3 else 1)' >/dev/null 2>&1; then
    PYTHON_BIN=python
  else
    echo "python3 is required to run the GOKZ map updater." >&2
    exit 1
  fi
fi

exec "$PYTHON_BIN" - "$@" <<'PY'
import bz2
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API_URL = os.environ.get(
    "GOKZ_MAPS_API_URL",
    "https://api.gokz.top/v1/maps?limit=10000&is_validated=true",
)
BZ2_MAX_BYTES = 150_000_000
PACKAGE_MAP_COUNT_THRESHOLD = 25
PACKAGE_BYTES_THRESHOLD = 1_500_000_000
DRY_RUN = os.environ.get("GOKZ_MAPS_DRY_RUN") == "1"
YES = os.environ.get("GOKZ_MAPS_YES") == "1"


def prompt_yes_no(message: str, *, default: bool = False) -> bool:
    if YES:
        return True
    suffix = " [Y/n] " if default else " [y/N] "
    answer = input(message + suffix).strip().lower()
    if not answer:
        return default
    return answer in {"y", "yes"}


def candidate_maps_dirs() -> list[Path]:
    cwd = Path.cwd().resolve()
    candidates: list[Path] = []

    if cwd.name == "maps" and cwd.parent.name == "csgo":
        candidates.append(cwd)
    if cwd.name == "csgo":
        candidates.append(cwd / "maps")

    common_csgo_dirs = [
        Path("/home/csgoserver/serverfiles/csgo"),
        Path.home() / "serverfiles/csgo",
        Path.home() / "Steam/steamapps/common/Counter-Strike Global Offensive/csgo",
        Path.home()
        / ".steam/steam/steamapps/common/Counter-Strike Global Offensive/csgo",
        Path("/opt/csgoserver/serverfiles/csgo"),
    ]
    candidates.extend(path / "maps" for path in common_csgo_dirs)

    seen: set[Path] = set()
    unique: list[Path] = []
    for path in candidates:
        resolved = path.expanduser().resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(resolved)
    return unique


def detect_maps_dir() -> Path:
    candidates = candidate_maps_dirs()
    for path in candidates:
        if path.is_dir():
            return path
    if candidates and candidates[0].parent.name == "csgo":
        return candidates[0]
    raise SystemExit(
        "Run this command from your csgo directory or csgo/maps directory."
    )


def fetch_json(url: str):
    with urlopen(Request(url, headers={"User-Agent": "gokz-map-updater/1"})) as response:
        return json.loads(response.read().decode("utf-8"))


def download_file(url: str, destination: Path) -> None:
    if DRY_RUN:
        print(f"DRY RUN download {url} -> {destination}")
        return
    with urlopen(Request(url, headers={"User-Agent": "gokz-map-updater/1"})) as response:
        with destination.open("wb") as output:
            shutil.copyfileobj(response, output)


def derive_package_url(maps: list[dict]) -> str | None:
    for map_info in maps:
        download_url = map_info.get("download_url")
        if isinstance(download_url, str) and "/maps/" in download_url:
            return download_url.split("/maps/", 1)[0] + "/packages/GlobalMaps.7z"
    return None


def local_needs_update(maps_dir: Path, map_info: dict) -> bool:
    name = map_info.get("name")
    filesize = map_info.get("filesize")
    if not isinstance(name, str) or not isinstance(filesize, int):
        return False
    local_path = maps_dir / f"{name}.bsp"
    return not local_path.exists() or local_path.stat().st_size != filesize


def atomic_raw_download(url: str, target: Path) -> None:
    temp_path = target.with_name(f".{target.name}.download")
    try:
        download_file(url, temp_path)
        if not DRY_RUN:
            temp_path.replace(target)
    finally:
        temp_path.unlink(missing_ok=True)


def atomic_bz2_download(url: str, target: Path) -> None:
    temp_bz2 = target.with_name(f".{target.name}.bz2.download")
    temp_bsp = target.with_name(f".{target.name}.download")
    try:
        download_file(url, temp_bz2)
        if not DRY_RUN:
            with bz2.open(temp_bz2, "rb") as source, temp_bsp.open("wb") as output:
                shutil.copyfileobj(source, output)
            temp_bsp.replace(target)
    finally:
        temp_bz2.unlink(missing_ok=True)
        temp_bsp.unlink(missing_ok=True)


def update_map(map_info: dict, maps_dir: Path) -> bool:
    name = map_info.get("name")
    filesize = map_info.get("filesize")
    download_url = map_info.get("download_url")
    if not isinstance(name, str) or not isinstance(filesize, int):
        return False
    if not isinstance(download_url, str) or not download_url:
        print(f"Skipping {name}: no download URL")
        return False

    target = maps_dir / f"{name}.bsp"
    if filesize <= BZ2_MAX_BYTES:
        try:
            print(f"Downloading {name}.bsp.bz2")
            atomic_bz2_download(download_url + ".bz2", target)
            return True
        except (HTTPError, URLError, OSError, EOFError) as error:
            print(f"BZ2 failed for {name}, using raw BSP: {error}")

    print(f"Downloading {name}.bsp")
    atomic_raw_download(download_url, target)
    return True


def extract_package(package_url: str, maps_dir: Path) -> None:
    seven_zip = shutil.which("7z") or shutil.which("7zz")
    if not seven_zip:
        raise RuntimeError("7z is not installed")

    temp_path = maps_dir / ".GlobalMaps.7z.download"
    try:
        print("Downloading GlobalMaps.7z")
        download_file(package_url, temp_path)
        if not DRY_RUN:
            subprocess.run(
                [seven_zip, "x", "-y", f"-o{maps_dir}", str(temp_path)],
                check=True,
            )
    finally:
        temp_path.unlink(missing_ok=True)


def valid_local_map_names(maps: list[dict], maps_dir: Path) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for map_info in maps:
        name = map_info.get("name")
        if not isinstance(name, str) or name in seen:
            continue
        if not (maps_dir / f"{name}.bsp").is_file():
            continue
        seen.add(name)
        names.append(name)
    return names


def write_map_list_files(*, maps: list[dict], maps_dir: Path) -> None:
    csgo_dir = maps_dir.parent
    map_names = valid_local_map_names(maps, maps_dir)
    content = "\n".join(map_names)
    if content:
        content += "\n"

    for filename in ("maplist.txt", "mapcycle.txt"):
        path = csgo_dir / filename
        if DRY_RUN:
            print(f"DRY RUN write {len(map_names)} valid map(s) -> {path}")
            continue
        temp_path = path.with_name(f".{path.name}.download")
        try:
            temp_path.write_text(content, encoding="utf-8")
            temp_path.replace(path)
        finally:
            temp_path.unlink(missing_ok=True)
    print(f"Updated maplist.txt and mapcycle.txt with {len(map_names)} valid map(s).")


def main() -> int:
    maps_dir = detect_maps_dir()
    print(f"Detected CS:GO maps directory: {maps_dir}")
    if not prompt_yes_no("Update maps in this directory?"):
        print("Cancelled.")
        return 1

    maps_dir.mkdir(parents=True, exist_ok=True)
    print("Fetching map list...")
    maps = fetch_json(API_URL)
    if not isinstance(maps, list):
        raise SystemExit("Unexpected /v1/maps response.")

    downloadable_maps = [
        item
        for item in maps
        if isinstance(item, dict)
        and isinstance(item.get("download_url"), str)
        and item.get("download_url")
    ]
    pending = [item for item in downloadable_maps if local_needs_update(maps_dir, item)]
    total_bytes = sum(
        item.get("filesize", 0) for item in pending if isinstance(item.get("filesize"), int)
    )

    print(f"{len(pending)} map(s) need download or update.")

    prefer_package = (
        len(pending) >= PACKAGE_MAP_COUNT_THRESHOLD
        or total_bytes >= PACKAGE_BYTES_THRESHOLD
    )
    package_url = derive_package_url(downloadable_maps)

    if prefer_package and package_url:
        if shutil.which("7z") or shutil.which("7zz"):
            extract_package(package_url, maps_dir)
            print("Map package extracted.")
            write_map_list_files(maps=maps, maps_dir=maps_dir)
            return 0
        if not prompt_yes_no(
            "7z is not installed. Download maps one by one instead?"
        ):
            print("Cancelled.")
            return 1

    updated = 0
    for map_info in pending:
        if update_map(map_info, maps_dir):
            updated += 1
    print(f"Updated {updated} map(s).")
    write_map_list_files(maps=maps, maps_dir=maps_dir)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nCancelled.")
        raise SystemExit(1)
PY
