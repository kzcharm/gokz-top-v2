---
name: merge-dev-to-main-after-green-ci
description: Use when an agent needs to push `dev`, monitor the exact GitHub Actions runs triggered by that push, fix any failing CI with minimal targeted changes, and merge `dev` into `main` only after the pushed commit is fully green.
---

# Merge Dev To Main After Green CI

This skill is repository-specific for `kzcharm/gokz-top-v2`.

Use it when the task is to:
- push the current `dev` branch
- monitor the workflows triggered by that push
- inspect and fix failing GitHub Actions checks
- merge `dev` into `main` only after the pushed `dev` SHA is fully green

## Expected workflow set

For a push to `dev`, track the runs for the exact pushed `head_sha`.

Expected workflows:
- `Conflict detector`
- `Deploy Staging`
- `Test Docker Compose`
- `Test Backend`

Do not merge based on branch-level status alone. Confirm the exact workflow runs attached to the pushed SHA.

## GitHub auth and repo targeting

- Use the repo token via `GH_TOKEN="$GITHUB_TOKEN_KZCHARM"` for GitHub API and `gh` commands.
- Do not rely on ambient `gh` repo context. This machine may resolve `gh` against the wrong repository.
- Prefer explicit REST API calls like:
  - `gh api 'repos/kzcharm/gokz-top-v2/actions/runs?...'`
  - `gh api 'repos/kzcharm/gokz-top-v2/actions/runs/<run_id>/jobs'`
  - `gh api 'repos/kzcharm/gokz-top-v2/actions/jobs/<job_id>/logs'`

## Push and map the run set

1. Confirm the branch and local state with `git status --short --branch`.
2. Push `dev` non-interactively with `git push origin dev`.
3. Capture the pushed SHA with `git rev-parse HEAD`.
4. Resolve the triggered workflow runs with:

```bash
GH_TOKEN="$GITHUB_TOKEN_KZCHARM" gh api \
  'repos/kzcharm/gokz-top-v2/actions/runs?branch=dev&event=push&per_page=20'
```

5. Filter to `.workflow_runs[] | select(.head_sha=="<sha>")`.

## Monitoring

- Use `gh run watch <run_id> --repo kzcharm/gokz-top-v2 --interval 10` for live progress.
- Watch multiple runs in parallel when possible.
- Reconfirm final conclusions with one last `gh api` query on the exact `head_sha`.

## Failure investigation

If any workflow fails:

1. Identify the failed job from:

```bash
GH_TOKEN="$GITHUB_TOKEN_KZCHARM" gh api \
  'repos/kzcharm/gokz-top-v2/actions/runs/<run_id>/jobs'
```

2. Pull the exact job log:

```bash
GH_TOKEN="$GITHUB_TOKEN_KZCHARM" gh api \
  'repos/kzcharm/gokz-top-v2/actions/jobs/<job_id>/logs'
```

3. Fix only the actual failing cause. Do not make speculative cleanup changes.
4. Prefer focused local verification that matches the failure.

## When GitHub Actions are unavailable

Sometimes the hosted workflows are not usable even though the repository code is fine, for example:
- GitHub-hosted jobs fail immediately because the repo is out of minutes
- the pushed SHA gets `failure` conclusions without meaningful logs
- `gh api 'repos/kzcharm/gokz-top-v2/actions/jobs/<job_id>/logs'` returns `BlobNotFound` or another 404 for jobs that never really started
- only the self-hosted `Deploy Staging` workflow is still runnable

Treat those as CI infrastructure failures, not code regressions.

When that happens:

1. Still push `dev` and capture the exact `head_sha`.
2. Confirm whether `Deploy Staging` for that same SHA is still available.
3. Run focused local verification for the touched area instead of waiting on broken hosted workflows.
4. Require either:
   - a successful `Deploy Staging` run for the exact SHA, or
   - a manual staging deploy on `kzcharm-v2` with healthy containers
5. If staging-specific operational work is part of the task, complete and verify it on staging before touching `main`.
6. Merge `origin/dev` into `main` from a clean worktree even though the hosted checks are unavailable, and state explicitly why the normal gate was bypassed.
7. If the release workflow is unavailable, create the release tag manually with `gh release create`.
8. Deploy production manually on `kzcharm-v2` and verify container health plus at least one live public surface.

### Manual deploy fallback for this repo

If the server checkout cannot fetch from GitHub directly, sync a clean local tree to the server and deploy from that synced tree instead of relying on `git fetch` on the host.

Typical production fallback on `kzcharm-v2`:

```bash
cp /root/code/gokz-top-v2/.env /root/code/gokz-top-v2-manual/.env
cd /root/code/gokz-top-v2-manual
export VITE_APP_VERSION=vX.Y.Z
docker compose -f compose.yml --project-name gokz-top-v2 build
docker compose -f compose.yml --project-name gokz-top-v2 up -d
docker compose -f compose.yml --project-name gokz-top-v2 ps
```

Typical staging fallback on `kzcharm-v2`:

```bash
cd /root/code/gokz-top-v2-staging
docker compose -f compose.yml --project-name gokz-top-v2-staging build
docker compose -f compose.yml --project-name gokz-top-v2-staging up -d
docker compose -f compose.yml --project-name gokz-top-v2-staging ps
```

### Substitute gate when hosted CI is down

Before merging or deploying under this fallback path, gather all of:
- the exact pushed `dev` SHA
- the exact local verification commands that passed
- proof that staging for that SHA is healthy
- proof that production after deploy is healthy

In the final report, explicitly state:
- which workflows were unavailable and why
- which manual verifications replaced them
- the `dev` SHA used for the manual path
- the final `main` merge commit SHA

## Clean-worktree pattern

If the main checkout has unrelated uncommitted changes, do not fix CI directly there.

Use a temporary clean worktree from the pushed SHA:

```bash
git worktree add /private/tmp/gokz-top-v2-ci-fix <sha>
```

Use the clean worktree to:
- inspect the failing code at the pushed revision
- patch the minimal fix
- run focused verification
- commit the fix cleanly

Then apply that fix back to the real `dev` branch with `git cherry-pick <fix_commit>`.

This avoids mixing CI fixes with the user’s unrelated working tree edits.

## Sandbox and permission notes

This environment may block writes under `.git`, including:
- `.git/worktrees/*`
- `.git/index.lock`
- `.git/FETCH_HEAD`

When that happens, request escalation for the specific git command instead of working around it.

Commands that commonly need escalation here:
- `git worktree add ...`
- `git cherry-pick ...`
- `git fetch origin ...`
- `git checkout -B main origin/main`

## Merge strategy

Prefer merging from a clean worktree after CI is green.

Recommended sequence:

1. `git fetch origin main dev`
2. `git checkout -B main origin/main`
3. `git merge --no-ff origin/dev -m 'merge: dev into main after green CI'`
4. `git push origin main`

This is the safest fallback when PR APIs are blocked by token scope.

## Verification before merge

Before merging, list the exact successful workflows for the green `dev` SHA. Include the run URLs in the final report when useful.

Minimum required confirmation:
- `Conflict detector` passed
- `Deploy Staging` passed
- `Test Docker Compose` passed
- `Test Backend` passed

## Final report checklist

Report all of the following:
- what failed, if anything
- what was changed to fix it
- which workflows passed for the final green SHA
- the final merge status
- the final `dev` SHA that went green
- the final `main` merge commit SHA

## Example from this repo

During one real run:
- initial `dev` SHA `473f1ff...` failed only in `Test Backend`
- the failure was in `backend/tests/alembic/test_player_profile_field_change_migration.py`
- the fix was a minimal test-only update aligned with the current schema head
- fixed `dev` SHA `28c1f82...` then passed all four workflows
- `main` was pushed at merge commit `198e767...`
