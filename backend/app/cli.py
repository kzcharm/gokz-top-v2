import asyncio
from collections.abc import Coroutine, Sequence
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from app.models import MapFileDistributionSyncResult, ModeScope
from app.services.map_authors import seed_map_authors_from_kz_map_info
from app.services.map_file_distribution import seed_map_package, sync_map_files
from app.services.map_file_distribution_worker import run_map_file_distribution_runner
from app.tasks import friends as friends_task
from app.tasks import record_transfer as record_transfer_task
from app.tasks.build import maps as maps_task
from app.tasks.build import pb as pb_task
from app.tasks.build import points as points_task
from app.tasks.build import profile as profile_task
from app.tasks.build import rating as rating_task

app = typer.Typer(
    help="GOKZ.TOP backend operator CLI.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
build_app = typer.Typer(
    help="Build and rebuild derived backend data.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
app.add_typer(build_app, name="build")
rebuild_app = typer.Typer(
    help="Rebuild derived backend data on demand.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
app.add_typer(rebuild_app, name="rebuild")
sync_app = typer.Typer(
    help="Synchronize external data into backend state.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
app.add_typer(sync_app, name="sync")
map_files_app = typer.Typer(
    help="Manage map BSP distribution artifacts.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
app.add_typer(map_files_app, name="map-files")
transfer_app = typer.Typer(
    help="Run narrowly scoped operator data transfers.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
app.add_typer(transfer_app, name="transfer")

console = Console()

ScopeOption = Annotated[
    list[str] | None,
    typer.Option(
        "--scope",
        help="Filter by scope. Repeat the option to target multiple scopes.",
    ),
]
SteamIdOption = Annotated[
    list[int] | None,
    typer.Option(
        "--steamid64",
        help="Filter by SteamID64. Repeat the option to target multiple players.",
    ),
]


def _parse_scopes(scope_names: Sequence[str] | None) -> tuple[ModeScope, ...]:
    if not scope_names:
        return ()

    scopes: list[ModeScope] = []
    for raw_scope in scope_names:
        normalized_scope = raw_scope.strip().upper()
        try:
            scopes.append(ModeScope[normalized_scope])
        except KeyError as exc:
            valid_scopes = ", ".join(scope.name for scope in ModeScope)
            raise typer.BadParameter(
                f"Invalid scope {raw_scope!r}. Expected one of: {valid_scopes}"
            ) from exc
    return tuple(scopes)


def _render_summary(title: str, rows: Sequence[tuple[str, str]]) -> None:
    table = Table(title=title)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")
    for label, value in rows:
        table.add_row(label, value)
    console.print(table)


def _render_record_transfer_summary(
    *, result: record_transfer_task.RecordTransferResult
) -> None:
    _render_summary(
        "Record Transfer Complete" if not result.dry_run else "Record Transfer Dry Run",
        [
            ("Source SteamID64", str(result.source_steamid64)),
            ("Target SteamID64", str(result.target_steamid64)),
            ("Dry run", "yes" if result.dry_run else "no"),
            ("Source records before", str(result.source_records_before)),
            ("Target records before", str(result.target_records_before)),
            ("Source records after", str(result.source_records_after)),
            ("Target records after", str(result.target_records_after)),
            ("Transferred records", str(result.transferred_records)),
            ("Touched PB keys", str(result.touched_pb_keys)),
            ("Touched PB buckets", str(result.touched_courses)),
            ("Source record_pb after", str(result.source_record_pb_after)),
            ("Leaderboard rows created", str(result.leaderboard_created)),
            ("Leaderboard rows updated", str(result.leaderboard_updated)),
            ("Player stats deleted", str(result.player_stats_deleted)),
            ("Rating rows selected", str(result.rating_rows_selected)),
            ("Rating rows created", str(result.rating_rows_created)),
            ("Rating rows updated", str(result.rating_rows_updated)),
            ("Audit path", str(result.audit_path)),
            ("Summary path", str(result.summary_path)),
            ("Audit sha256", result.checksum),
        ],
    )


def _run_async[T](coro: Coroutine[object, object, T]) -> T:
    return asyncio.run(coro)


@transfer_app.command("records")
def transfer_records(
    source_steamid64: Annotated[
        int,
        typer.Option(
            "--source-steamid64",
            help="SteamID64 whose records will be transferred.",
        ),
    ] = record_transfer_task.DEFAULT_SOURCE_STEAMID64,
    target_steamid64: Annotated[
        int,
        typer.Option(
            "--target-steamid64",
            help="SteamID64 that will receive the records.",
        ),
    ] = record_transfer_task.DEFAULT_TARGET_STEAMID64,
    audit_path: Annotated[
        Path | None,
        typer.Option(
            "--audit-path",
            help="JSONL audit output path. Defaults to .temp/record-transfers/.",
        ),
    ] = None,
    after: Annotated[
        str | None,
        typer.Option(
            "--after",
            help="Inclusive UTC date/datetime lower bound (ISO 8601).",
        ),
    ] = None,
    before: Annotated[
        str | None,
        typer.Option(
            "--before",
            help="Inclusive UTC date/datetime upper bound (ISO 8601).",
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run/--apply",
            help="Inspect and write a dry-run audit file without committing DB changes.",
        ),
    ] = True,
) -> None:
    result = _run_async(
        record_transfer_task.transfer_records(
            source_steamid64=source_steamid64,
            target_steamid64=target_steamid64,
            audit_path=audit_path,
            after=after,
            before=before,
            dry_run=dry_run,
        )
    )
    _render_record_transfer_summary(result=result)


@rebuild_app.command("maps")
def rebuild_maps(
    scope_names: ScopeOption = None,
    map_ids: Annotated[
        list[int] | None,
        typer.Option("--map-id", help="Filter by map id. Repeat for multiple maps."),
    ] = None,
) -> None:
    scopes = _parse_scopes(scope_names)
    result = _run_async(
        maps_task.rebuild_map_leaderboards(
            scopes=scopes if scopes else None,
            map_ids=map_ids,
        )
    )
    _render_summary(
        "Maps Rebuild Complete",
        [
            ("Scopes", ", ".join(scope.name for scope in result.scopes)),
            ("Map IDs", "*" if not result.map_ids else ", ".join(map(str, result.map_ids))),
            ("Rows rebuilt", str(result.rows_rebuilt)),
        ],
    )


@build_app.command("rating")
def build_rating(
    scope_names: ScopeOption = None,
    steamid64s: SteamIdOption = None,
    limit: Annotated[
        int | None,
        typer.Option(help="Optional limit on selected leaderboard rows."),
    ] = None,
    full: Annotated[
        bool,
        typer.Option(
            "--full",
            help="Rebuild rating dependencies first by recalculating main-course points.",
        ),
    ] = False,
) -> None:
    scopes = _parse_scopes(scope_names)
    scope_ids = rating_task.resolve_scope_ids(scope_names)
    result = _run_async(
        rating_task.rebuild_ratings(
            scope_ids=scope_ids,
            scopes=scopes if scopes else None,
            steamid64s=steamid64s,
            limit=limit,
            full=full,
        )
    )
    rows = [
        ("Rows selected", str(result.leaderboard.selected)),
        ("Rows created", str(result.leaderboard.created)),
        ("Rows updated", str(result.leaderboard.updated)),
    ]
    if result.full:
        rows.insert(0, ("PB points updated", str(result.pb_points_updated)))
    _render_summary("Rating Build Complete", rows)


@build_app.command("points")
def build_points(
    scope_names: ScopeOption = None,
    map_names: Annotated[
        list[str] | None,
        typer.Option("--map-name", help="Filter by map name. Repeat for multiple maps."),
    ] = None,
    stage: Annotated[
        int | None,
        typer.Option(help="Optional stage filter. Defaults to main course only."),
    ] = None,
    all_stages: Annotated[
        bool,
        typer.Option("--all-stages", help="Process all stages instead of only stage 0."),
    ] = False,
    limit: Annotated[
        int | None,
        typer.Option(help="Optional limit on selected courses."),
    ] = None,
) -> None:
    if stage is not None and all_stages:
        raise typer.BadParameter("Use either --stage or --all-stages, not both.")

    scopes = _parse_scopes(scope_names)
    selected_scopes = scopes if scopes else tuple(ModeScope)
    selected_stage = points_task.resolve_stage(stage=stage, all_stages=all_stages)
    updated_rows = _run_async(
        points_task.rebuild_record_pb_points(
            scopes=selected_scopes,
            map_names=map_names,
            stage=selected_stage,
            limit=limit,
        )
    )
    _render_summary(
        "Points Build Complete",
        [
            ("Scopes", ", ".join(scope.name for scope in selected_scopes)),
            ("Stage filter", "*" if selected_stage is None else str(selected_stage)),
            ("Rows updated", str(updated_rows)),
        ],
    )


def _build_pb_impl(
    *,
    list_only: bool,
    force_all: bool,
    limit: int | None,
    analyze: bool,
    ensure_map_courses: bool,
) -> None:
    if list_only:
        buckets = _run_async(pb_task.list_record_pb_buckets(force_all=force_all))
        console.print(pb_task.format_bucket_plan(buckets=buckets), end="")
        return

    result = _run_async(
        pb_task.rebuild_record_pbs(
            force_all=force_all,
            limit=limit,
            analyze=analyze,
            ensure_map_courses=ensure_map_courses,
        )
    )
    _render_summary(
        "PB Build Complete",
        [
            ("Courses processed", str(result.course_count)),
            ("Rows after rebuild", str(result.row_count)),
            ("Ensured map courses", "yes" if result.ensured_map_courses else "no"),
            ("Elapsed (s)", f"{result.elapsed_seconds:.1f}"),
        ],
    )


@build_app.command("pb")
def build_pb(
    list_only: Annotated[
        bool,
        typer.Option("--list-only", help="List the rebuild plan without mutating record_pb."),
    ] = False,
    force_all: Annotated[
        bool,
        typer.Option("--force-all", help="Rebuild every bucket, not only dirty buckets."),
    ] = False,
    limit: Annotated[
        int | None,
        typer.Option(help="Only process the first N selected courses."),
    ] = None,
    analyze: Annotated[
        bool,
        typer.Option("--analyze", help="Run ANALYZE on map_course and record_pb after rebuild."),
    ] = False,
    ensure_map_courses: Annotated[
        bool,
        typer.Option(
            "--ensure-map-courses",
            help="Backfill missing map_course rows before planning the rebuild.",
        ),
    ] = False,
) -> None:
    _build_pb_impl(
        list_only=list_only,
        force_all=force_all,
        limit=limit,
        analyze=analyze,
        ensure_map_courses=ensure_map_courses,
    )


@build_app.command("pbs")
def build_pbs(
    list_only: Annotated[
        bool,
        typer.Option("--list-only", help="List the rebuild plan without mutating record_pb."),
    ] = False,
    force_all: Annotated[
        bool,
        typer.Option("--force-all", help="Rebuild every bucket, not only dirty buckets."),
    ] = False,
    limit: Annotated[
        int | None,
        typer.Option(help="Only process the first N selected courses."),
    ] = None,
    analyze: Annotated[
        bool,
        typer.Option("--analyze", help="Run ANALYZE on map_course and record_pb after rebuild."),
    ] = False,
    ensure_map_courses: Annotated[
        bool,
        typer.Option(
            "--ensure-map-courses",
            help="Backfill missing map_course rows before planning the rebuild.",
        ),
    ] = False,
) -> None:
    _build_pb_impl(
        list_only=list_only,
        force_all=force_all,
        limit=limit,
        analyze=analyze,
        ensure_map_courses=ensure_map_courses,
    )


def _sync_profiles_impl(
    *,
    steamid64s: list[int] | None = None,
    missing_avatar: bool = False,
    leaderboard: str | None = None,
    stale_days: int | None = None,
    limit: int | None = None,
) -> None:
    selection_flags = sum(
        (
            1 if missing_avatar else 0,
            1 if leaderboard is not None else 0,
            1 if stale_days is not None else 0,
        )
    )
    if selection_flags > 1:
        raise typer.BadParameter(
            "Use only one of --missing-avatar, --stale-days, or --leaderboard."
        )
    if steamid64s is not None and selection_flags > 0:
        raise typer.BadParameter(
            "Use either --steamid64 or one selection filter, not both."
        )

    leaderboard_scope: ModeScope | None = None
    if leaderboard is not None:
        parsed_scopes = _parse_scopes([leaderboard])
        leaderboard_scope = parsed_scopes[0]

    try:
        result = _run_async(
            profile_task.rebuild_player_profiles(
                steamid64s=steamid64s,
                only_missing_avatar=missing_avatar,
                leaderboard_scope=leaderboard_scope,
                stale_days=stale_days,
                limit=limit,
            )
        )
    except profile_task.RebuildPlayerProfileInterruptedError as exc:
        result = exc.result
        _render_summary(
            "Profile Sync Interrupted",
            [
                ("Players selected", str(result.selected)),
                ("Players created", str(result.created)),
                ("Players updated", str(result.updated)),
                ("Players skipped", str(result.skipped)),
            ],
        )
        raise typer.Exit(code=130) from exc

    _render_summary(
        "Profile Sync Complete",
        [
            ("Players selected", str(result.selected)),
            ("Players created", str(result.created)),
            ("Players updated", str(result.updated)),
            ("Players skipped", str(result.skipped)),
        ],
    )


def _sync_friends_impl(
    *,
    steamid64s: list[int] | None = None,
    leaderboard: str | None = None,
    limit: int | None = None,
) -> None:
    leaderboard_scope: ModeScope | None = None
    if leaderboard is not None:
        parsed_scopes = _parse_scopes([leaderboard])
        leaderboard_scope = parsed_scopes[0]

    try:
        result = _run_async(
            friends_task.sync_player_friends_for_players(
                steamid64s=steamid64s,
                leaderboard_scope=leaderboard_scope,
                limit=limit,
            )
        )
    except friends_task.SyncPlayerFriendsInterruptedError as exc:
        result = exc.result
        _render_summary(
            "Friends Sync Interrupted",
            [
                ("Players selected", str(result.selected)),
                ("Players synced", str(result.synced)),
                ("Rate limited", str(result.rate_limited)),
                ("Private", str(result.private)),
                ("Failed", str(result.failed)),
            ],
        )
        raise typer.Exit(code=130) from exc

    _render_summary(
        "Friends Sync Complete",
        [
            ("Players selected", str(result.selected)),
            ("Players synced", str(result.synced)),
            ("Rate limited", str(result.rate_limited)),
            ("Private", str(result.private)),
            ("Failed", str(result.failed)),
        ],
    )


@sync_app.command("profiles")
def sync_profiles(
    steamid64s: SteamIdOption = None,
    missing_avatar: Annotated[
        bool,
        typer.Option(
            "--missing-avatar",
            help="Select only players that do not have an avatar hash yet.",
        ),
    ] = False,
    leaderboard: Annotated[
        str | None,
        typer.Option("--leaderboard", help="Select all players on a leaderboard scope."),
    ] = None,
    stale_days: Annotated[
        int | None,
        typer.Option(
            "--stale-days",
            min=1,
            help="Select players whose Steam profile was last updated at least N days ago.",
        ),
    ] = None,
    limit: Annotated[
        int | None,
        typer.Option(help="Optional limit on selected players."),
    ] = None,
) -> None:
    _sync_profiles_impl(
        steamid64s=steamid64s,
        missing_avatar=missing_avatar,
        leaderboard=leaderboard,
        stale_days=stale_days,
        limit=limit,
    )


@sync_app.command("friends")
def sync_friends(
    steamid64s: SteamIdOption = None,
    leaderboard: Annotated[
        str | None,
        typer.Option("--leaderboard", help="Select all players on a leaderboard scope."),
    ] = None,
    limit: Annotated[
        int | None,
        typer.Option(help="Optional limit on selected players."),
    ] = None,
) -> None:
    _sync_friends_impl(
        steamid64s=steamid64s,
        leaderboard=leaderboard,
        limit=limit,
    )


@sync_app.command("map-authors")
def sync_map_authors() -> None:
    from app.core.db import async_session_maker

    async def _run():
        async with async_session_maker() as session:
            return await seed_map_authors_from_kz_map_info(session=session)

    result = _run_async(_run())
    _render_summary(
        "Map Author Seed Complete",
        [
            ("Rows processed", str(result.processed)),
            ("Maps matched", str(result.matched)),
            ("Maps updated", str(result.updated)),
            ("Rows skipped", str(result.skipped)),
        ],
    )


@map_files_app.command("seed")
def seed_map_files(
    package_path: Annotated[
        Path,
        typer.Argument(help="Path to an operator-provided GlobalMaps.7z package."),
    ],
    copy_package: Annotated[
        bool,
        typer.Option(
            "--copy-package",
            help="Persist this archive as the local GlobalMaps.7z package seed.",
        ),
    ] = False,
) -> None:
    result = _run_async(
        seed_map_package(package_path=package_path, copy_package=copy_package)
    )
    _render_summary(
        "Map File Seed Complete",
        [
            ("BSPs processed", str(result.processed)),
            ("BSPs extracted", str(result.extracted)),
            ("Package copied", "yes" if result.package_copied else "no"),
        ],
    )


@map_files_app.command("sync")
def sync_map_files_command(
    force: Annotated[
        bool,
        typer.Option("--force", help="Process all validated maps, even if metadata is current."),
    ] = False,
    map_ids: Annotated[
        list[int] | None,
        typer.Option("--map-id", help="Filter by map id. Repeat for multiple maps."),
    ] = None,
) -> None:
    from app.core.db import async_session_maker

    async def _run() -> MapFileDistributionSyncResult:
        async with async_session_maker() as session:
            return await sync_map_files(session=session, force=force, map_ids=map_ids)

    result = _run_async(_run())
    _render_summary(
        "Map File Sync Complete",
        [
            ("Processed", str(result.processed)),
            ("Downloaded", str(result.downloaded)),
            ("Uploaded", str(result.uploaded)),
            ("BZ2 uploaded", str(result.bz2_uploaded)),
            ("Full package uploaded", str(result.package_uploaded)),
            ("Release packages uploaded", str(result.release_packages_uploaded)),
            ("Skipped", str(result.skipped)),
            ("Errors", str(result.errors)),
            ("Disabled", "yes" if result.disabled else "no"),
        ],
    )


@map_files_app.command("run-worker")
def run_map_files_worker() -> None:
    _run_async(run_map_file_distribution_runner())


@build_app.command("profile", hidden=True)
def build_profile(
    steamid64s: SteamIdOption = None,
    all_players: Annotated[
        bool,
        typer.Option("--all", help="Process all existing players instead of only missing avatars."),
    ] = False,
    leaderboard: Annotated[
        str | None,
        typer.Option(
            "--leaderboard",
            help="Select players by leaderboard rating order for a specific scope.",
        ),
    ] = None,
    limit: Annotated[
        int | None,
        typer.Option(help="Optional limit on selected players."),
    ] = None,
) -> None:
    _sync_profiles_impl(
        steamid64s=steamid64s,
        missing_avatar=not all_players and leaderboard is None,
        leaderboard=leaderboard,
        limit=limit,
    )


def main() -> None:
    app(prog_name="./kztop")


if __name__ == "__main__":
    main()
