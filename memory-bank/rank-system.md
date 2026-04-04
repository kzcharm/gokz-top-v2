# GOKZ.TOP v2 Rank System

## Summary

GOKZ uses two linked systems to represent competitive performance:

1. `PB points` measure how strong a player's personal best is on a single eligible course leaderboard.
2. `Player rating` measures a player's overall performance across eligible PB points.

Both systems are mode-specific.

## Terminology

- `Main course`: the course with `stage = 0`.
- `Bonus course`: any course with `stage > 0`.
- `Play map X`: unless stated otherwise, this means playing the map's main course.
- `NUB`: teleports allowed.
- `PRO`: no teleports.
- `Tier`: the difficulty tier for a course in a given mode.
- `Scope Tier`: the tier used for a scope-wide view of a course. It is the minimum non-null tier among the modes included in that scope.
- `Validated map`: a map whose main course is considered ranked. This is the GOKZ v2 equivalent of the old `Globalled` concept.
- `PB points`: integer points in the range `1..1000` attached to a player's current PB on an eligible leaderboard.
- `0 points`: the run does not have PB points. This includes non-PB runs and runs that are not eligible for ranked PB points.

There is no separate tier for `NUB` and `PRO`. A course has one tier per mode. That shared tier is used by both the `NUB` and `PRO` point formulas.

For scope-wide tier views, `Scope Tier` is derived from the tiers of the modes inside that scope:

- Ignore `null` mode tiers.
- Use the minimum remaining tier value.
- If all included mode tiers are `null`, the scope tier is `null`.

Example:

- `KZT = T3`
- `SKZ = T4`
- `VNL = T5`
- `NKZ = null`

Then the course `OVR` tier is `T3`.

## Ranked Course Rules

Only the validated main course is ranked for player aggregates.

- If a map is validated, its main course (`stage = 0`) is the ranked course for that map.
- If a map is not validated, it does not award ranked PB points.
- Bonus courses (`stage > 0`) never contribute to player rating or total points.
- Each validated main course has two eligible PB leaderboards:
  - `Main NUB`
  - `Main PRO`

If a player has both a `Main NUB` PB and a `Main PRO` PB on the same validated map:

- both PBs contribute to `total points`
- only the higher of the two PB-point values contributes to `rating`

## PB Points

Only a player's current PB on an eligible leaderboard can have PB points.

- Eligible PB points are only awarded on validated main-course leaderboards.
- `Main NUB` PB points count.
- `Main PRO` PB points count.
- Bonus PBs never count toward player rating or total points.

PB points use the direct `1..1000` public scale:

```text
PBPoints = Clamp(1, 1000,
  MinPoints + (1000 - MinPoints) * (
    0.125 * RankPointsPortion +
    0.875 * DistPointsPortion
  )
)
```

### MinPoints

`MinPoints` is the baseline reward for finishing a ranked main course. Higher tiers give higher minimums, and `PRO` receives a higher baseline than `NUB`.

| Tier | MinPoints (NUB) | MinPoints (PRO) |
| ---- | --------------- | --------------- |
| 1    | 1               | 10              |
| 2    | 50              | 145             |
| 3    | 200             | 280             |
| 4    | 350             | 415             |
| 5    | 500             | 550             |
| 6    | 650             | 685             |
| 7    | 800             | 820             |
| 8    | 950             | 955             |

The purpose of `MinPoints` is to ensure harder courses still reward meaningful skill even when a player's leaderboard placement is low.

### RankPointsPortion

`RankPointsPortion` is a multiplier between `0.0` and `1.0` based on leaderboard position.

- `Top 100`: `+0.004` per rank above `#100`
- `Top 20`: additional `+0.02` per rank above `#20`
- `Top 5`: extra fixed bonuses

| Rank | Bonus |
| ---- | ----- |
| 5    | +0.02 |
| 4    | +0.06 |
| 3    | +0.09 |
| 2    | +0.12 |
| 1    | +0.20 |

Examples:

| Rank | Multiplier |
| ---- | ---------- |
| 120  | `0.000`    |
| 100  | `0.004`    |
| 80   | `0.080`    |
| 15   | `0.464`    |
| 2    | `0.896`    |
| 1    | `1.000`    |

### DistPointsPortion

`DistPointsPortion` is a multiplier between `0.0` and `1.0` based on how strong the run is relative to the leaderboard distribution.

Roughly:

```text
DistPointsPortion ~= rank / total percentile
```

Intuition:

- Faster than `75%` of players -> about `0.75`
- Faster than `90%` of players -> about `0.90`

For low-completion leaderboards, use this fallback:

```text
P(time, wr, tier) =
    (1 + exp((2.1 - 0.25 * tier) * -0.5))
    --------------------------------------
    (1 + exp((2.1 - 0.25 * tier) * (time / wr - 1.5)))
```

Notes:

- The curve is centered at `1.5x` world-record time.
- Higher tiers reduce the scaling factor, so time gaps matter less aggressively on harder courses.
- This preserves the legacy GOKZ intent while using the direct `1..1000` PB-point scale in this spec.

## Player Aggregates

Only validated main-course PB points contribute to player aggregates.

### Total Points

`Total points` is the sum of a player's qualifying PB points:

- include `Main NUB` PB points on validated maps
- include `Main PRO` PB points on validated maps
- exclude all bonus PBs
- exclude all PBs on unvalidated maps

If a player has both `Main NUB` and `Main PRO` PB points on the same validated map, both are included in `total points`.

### Player Rating

`Player rating` is a weighted sum of a player's qualifying PB points:

```text
Rating = Sum(MapRatingPoints * 0.975^(n-1))
```

Where:

- `MapRatingPoints` is the per-map value used for rating
- for each validated map, `MapRatingPoints = max(Main NUB PB points, Main PRO PB points)`
- `n` is the map's position after sorting all qualifying `MapRatingPoints` in descending order
- bonus courses are never included
- unvalidated maps are never included

This weighting makes a player's best results matter most while still rewarding breadth and continued improvement.

With a maximum PB value of `1000`, the theoretical maximum rating is `40000`.

If a player has no qualifying PB points, both `total points` and `rating` are `0`.

## Practical Examples

- A `stage = 0` `NUB` PB on a validated map awards `1..1000` PB points and counts toward both total points and rating.
- A `stage = 0` `PRO` PB on a validated map also awards `1..1000` PB points and counts toward both total points and rating.
- If a player has both `Main NUB` and `Main PRO` PBs on the same validated map, both increase total points, but rating uses only the higher PB-point value from that map.
- A `stage = 2` bonus PB never counts toward total points or rating, even if the map is validated.
- A main-course PB on an unvalidated map has `0` PB points for ranking purposes and does not affect total points or rating.

## Contract Notes

- This document is the source-of-truth ranking spec for future GOKZ v2 implementation work.
- It intentionally uses `NUB` instead of the old public-facing `Overall` terminology.
- It intentionally does not introduce an `unranked` / `pending` / `ranked` state model for courses or filters.
- Ranked eligibility is determined by the validated main course only.
