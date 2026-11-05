# Frontend Preferences

- Truncate server names when they are too long, and show the full server name on hover.
- Display players with `PlayerDisplay.tsx` whenever player identity is shown and the component applies.
- Display run times with `RunTime` and use `useRunTimeFormat` for chart labels, tooltips, and interpolated text. Use the shared `run-time` class for WR gaps. Keep session durations and accumulated playtime independent of the global milliseconds preference.
- The navbar gear's Run time font dialog offers Inter (default), Roboto Mono, and Plus Jakarta Sans, persisted under `gokz-run-time-font`. The compact gear menu shows toggle states and the current font. Shared displays use the `--font-run-time` CSS variable; chart labels use `useRunTimeFontFamily` and update when the selection changes.
- Mark required frontend form fields with a red asterisk (`*`).
- For leaderboard-style `DataTable` layouts, use the players leaderboard as the visual/behavioral reference. Keep sticky headers on the shared `DataTable` path with `stickyHeader`, `stickyHeaderTopClassName="top-16"`, `tableContainerClassName="md:overflow-visible"`, and `tableClassName="table-fixed border-separate border-spacing-0"`.
- Prefer explicit TanStack column `size` values for leaderboard tables that use `table-fixed`. Add or remove columns by adjusting the column definitions and widths instead of changing shared sticky-header behavior, adding table-specific masks, or raising shared z-indexes.
- When changing leaderboard columns, verify both the normal top-of-table state and the pinned sticky-header state in the browser. Check that the first row starts below the header, the table does not exceed its card/container at desktop widths, and the sticky header visually matches `/leaderboards/players`.
