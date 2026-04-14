import asyncio
from collections.abc import Coroutine, Sequence
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from app.models import ModeScope
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
sync_app = typer.Typer(
    help="Synchronize external data into backend state.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
app.add_typer(sync_app, name="sync")

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


def _run_async[T](coro: Coroutine[object, object, T]) -> T:
    return asyncio.run(coro)


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
