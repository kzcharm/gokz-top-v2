# GOKZ.TOP Deployment Workflow

## Web GOKZ service

The `web-gokz` Compose service runs `app.web_gokz:app` with exactly one worker.
Its Traefik route takes precedence over the normal API for `/v1/web-gokz`.
Deploy the backend image and run Alembic before starting this service; migration
`888982fc689d` creates only the separate Web record schema. Do not copy Web times
into native records or rebuild native rankings from them.

Use matching `FRONTEND_HOST`, `REPLAY_VIEWER_HOSTNAME`, and the game build's
`VITE_WEBSITE_URL`. `/web-gokz/connect` shares a scoped session only with the
configured replay-viewer origin. Both rooms require authenticated website users.
The main frontend launches through `/web-gokz/connect?launch=1&room=<id>` or
`?launch=1&map=<name>`. Logged-in players receive a single-use, 60-second code in
the game URL fragment; the game strips and exchanges it for its scoped session.
Anonymous solo launches go directly to the game. Both flows use the configured
`VITE_REPLAY_VIEWER_URL`; access tokens never appear in launch URLs.

`REPLAY_VIEWER_RESOURCES_DIR` must contain both `maps/<name>/index.json` and
`practice/<name>.json` with a `bspSha256` field for each advertised room map.
Generate physics metadata with the replay-viewer's `scripts/export-practice-map.py`;
renderer-only exports are insufficient. Include the game's prepared player,
sound and font assets when deploying practice. The room service scans playable
maps at startup, so restart it after adding maps. Mount these assets read-only.
Use a separate staging asset directory when testing changed assets.

Both deployment workflows check out the exact `replay-viewer` submodule revision,
build the game, and start `web-gokz` and `replayviewer` alongside the website.
The repository secret `WEB_GOKZ_READ_SSH_KEY` holds a dedicated read-only deploy
key for the private `kzcharm/replay-viewer` repository; checkout does not persist
it. Register its public half only on that game repository with write access off.
Staging defaults to
`/root/code/gokz-top-v2-staging/.temp/web-gokz-resources`; override it with
`REPLAY_VIEWER_RESOURCES_DIR_STAGING` when moving the prepared assets.
Prepare the production resource directory separately before promoting this feature;
the staging asset transfer does not populate production.

The November 6 staging verification covered two real Chrome clients, website
login handoff, remote player rendering, chat, solo record submission and retry,
`!maptop`, and a shared RTV map change. The temporary accounts and all three test
finishes were removed; their native record and native PB counts remained zero.
The subsequent staging website/backend refresh also verified the shared server
cards (map tiers, Web group last, no country flags or copy controls), the real
website Play button's single-use login-code exchange and room join, the reference
replay endpoint, and an idempotent Web-only record submission. The temporary
accounts and record were removed after confirming zero native records and PBs.
Only `frontend`, `backend`, and `web-gokz` were replaced; the deployed game
container and production services were preserved, with prior images retained
for rollback.
The prepared catalog contains 828 maps. Another 151 BSP exports failed validation
and are excluded; prepared maps can still have unsupported collision features.

Service restarts disconnect players and reset votes/maps; stored Web records
survive. Keep one service instance until room state has shared ownership. Browser
results remain explicitly client-submitted, not server-verified race results.

This document describes the current trunk-based deployment workflow for future
contributors and automation agents.

## Overview

- Normal development happens directly on `main`.
- Every push to `main` runs the main CI gate and, if it passes, deploys
  **staging** automatically.
- **Production** deploys are manual and use the `Deploy Production` GitHub
  Actions workflow.
- Production releases are tagged when production is promoted, not on every
  `main` push.

## Development Workflow

1. Branch locally if you want, but merge or push finished work to `main`.
2. Push to `origin/main`.
3. GitHub Actions runs the staging workflow for that exact `main` SHA.
4. If staging succeeds, manually promote that same `main` commit to production.

The repository no longer relies on a long-lived `dev` branch for normal
deployment.

### Chronological record-history index

Revision `fa7caf33aca5` adds `ix_record_valid_map_stage_history` with
`CREATE INDEX CONCURRENTLY` in an Alembic autocommit block. Let Alembic manage
the transaction boundary; do not wrap this migration in an external transaction.
The downgrade drops only this index, also concurrently, and preserves records.

Plan disk and WAL headroom before rollout. On a local database with approximately
27.8 million records, the index occupied 2.63 GB and built in 43 seconds; these
are local measurements, not production duration or capacity guarantees.
Concurrent construction still scans the table, consumes CPU and I/O, and can
wait for existing transactions. Monitor `pg_stat_progress_create_index` and
verify `pg_index.indisvalid` and `indisready` after completion.

If construction fails, inspect the index and Alembic revision before retrying.
When this revision has not advanced and its named index is invalid, remove that
invalid index with `DROP INDEX CONCURRENTLY` outside a transaction, then rerun
the migration. Do not use `IF NOT EXISTS` to silently accept an invalid index.
Use a checkout containing this revision when operating a local database already
upgraded to it; older checkouts cannot resolve the new Alembic revision.

## Staging Deployment Flow

The `.github/workflows/deploy-staging.yml` workflow runs on every push to
`main`.

It performs three steps in one workflow:

1. `test-backend`
   - seeds `.env` from `.env.example`
   - starts PostgreSQL
   - runs backend migrations
   - runs the backend test suite
2. `test-docker-compose`
   - builds the backend and frontend images with the local override stack
   - starts the local Compose stack
   - verifies backend and frontend health
3. `deploy-staging`
   - runs only after both jobs pass
   - builds the staging backend and frontend images on the self-hosted runner
   - updates the staging stack
   - verifies the staging frontend URL, staging API URL, and backend container
     health endpoint

Only one staging deploy runs at a time. New pushes to `main` cancel an older
staging deploy that is still in progress.

## Production Deployment Flow

Production deploys are manual.

Trigger them from GitHub UI or GitHub CLI:

```bash
gh workflow run deploy-production.yml -f ref=main
```

You can also deploy a specific tag or SHA that is already contained in
`origin/main`:

```bash
gh workflow run deploy-production.yml -f ref=v1.13.6
gh workflow run deploy-production.yml -f ref=17cae085be4a0839efc74d466fa0fe1eafe41e28
```

The `.github/workflows/deploy-production.yml` workflow:

1. checks out the requested ref
2. verifies that the selected commit is reachable from `origin/main`
3. reuses an existing semver tag if the commit already has one
4. otherwise computes the next semver tag from conventional commits, creates
   the tag, and creates the GitHub release
5. builds and deploys production on the self-hosted runner
6. verifies public frontend, public API, and in-container backend health

Only one production deploy runs at a time. Production deploys are never
auto-cancelled.

## GitHub Actions Map

Primary workflows:

- `deploy-staging.yml`
  - trigger: push to `main`
  - purpose: gate `main` with backend + Compose checks, then deploy staging
- `deploy-production.yml`
  - trigger: manual `workflow_dispatch`
  - purpose: create/reuse the production release tag and deploy production

Supporting workflows:

- `test-backend.yml`
  - trigger: pull requests only
  - purpose: backend CI for PR review without duplicating the `main` push gate
- `test-docker-compose.yml`
  - trigger: pull requests only
  - purpose: Compose smoke/build CI for PR review
- `playwright.yml`
  - trigger: manual
  - purpose: optional browser end-to-end test run
- `latest-changes.yml`
  - trigger: merged PRs into `main`
  - purpose: update `release-notes.md` for the `/updates` page
- `smokeshow.yml`
  - trigger: successful `Test Backend` runs
  - purpose: publish coverage artifacts when available

## Required Secrets And Environment Variables

The deploy workflows expect repository secrets with these names.

Shared deploy secrets:

- `SECRET_KEY`
- `SUPER_USER_STEAMID64`
- `STEAM_API_KEY`
- `POSTGRES_PASSWORD`
- `SENTRY_DSN`
- `GEOIPUPDATE_ACCOUNT_ID`
- `GEOIPUPDATE_LICENSE_KEY`
- `TWITCH_CLIENT_ID`
- `TWITCH_CLIENT_SECRET`
- `YOUTUBE_CLIENT_ID`
- `YOUTUBE_CLIENT_SECRET`

Staging-specific deploy secrets:

- `DOMAIN_STAGING`
- `BASE_DOMAIN_STAGING`
- `FRONTEND_HOSTNAME_STAGING`
- `API_HOST_STAGING`
- `ADMINER_HOST_STAGING`
- `STACK_NAME_STAGING`
- `R2_ACCOUNT_ID_STAGING`
- `R2_ACCESS_KEY_ID_STAGING`
- `R2_SECRET_ACCESS_KEY_STAGING`
- `R2_BUCKET_NAME_STAGING`
- `R2_PUBLIC_BASE_URL_STAGING`
- `REPLAY_VIEWER_HOSTNAME_STAGING`
- `REPLAY_VIEWER_RESOURCES_DIR_STAGING`

Production-specific deploy secrets:

- `STACK_NAME_PRODUCTION`
- `FRONTEND_HOST_ALIASES_PRODUCTION`
- `R2_ACCOUNT_ID_PRODUCTION`
- `R2_ACCESS_KEY_ID_PRODUCTION`
- `R2_SECRET_ACCESS_KEY_PRODUCTION`
- `R2_BUCKET_NAME_PRODUCTION`
- `R2_PUBLIC_BASE_URL_PRODUCTION`
- `YOUTUBE_API_KEY`
- `REPLAY_VIEWER_HOSTNAME_PRODUCTION`
- `REPLAY_VIEWER_RESOURCES_DIR_PRODUCTION`

Optional repository automation secrets:

- `LATEST_CHANGES` for `latest-changes.yml`
- `SMOKESHOW_AUTH_KEY` for coverage publishing

The self-hosted runner also needs working Docker, access to the target stack
directories, and any host-mounted data directories already used by production
or staging.

## Troubleshooting

### Staging did not deploy after a push to `main`

Check the `Deploy Staging` workflow run first.

- If `test-backend` failed, fix the backend or migration issue and push again.
- If `test-docker-compose` failed, fix the image or runtime startup issue and
  push again.
- If the deploy job failed, inspect the self-hosted runner logs and the
  Compose service status on the runner host.

### Production workflow rejects the requested ref

The manual production workflow only accepts commits that are already contained
in `origin/main`. If you want to deploy a commit, merge or push it to `main`
first.

### Production deploy succeeded but the site looks old

Check:

- the workflow used the expected `ref`
- the workflow output reused or created the expected semver tag
- the frontend build received the expected `VITE_APP_VERSION`
- the self-hosted runner updated the correct Compose project name

### Health checks fail after deploy

Inspect the self-hosted runner host:

- `docker compose -f compose.yml --project-name <stack> ps`
- `docker compose -f compose.yml --project-name <stack> logs backend`
- `docker compose -f compose.yml --project-name <stack> logs frontend`

Also confirm that DNS, Traefik, and host-mounted directories still match the
secrets written into the deploy `.env`.

## Recovery And Rollback

### Staging rollback

Push a revert to `main`. The next `main` push will redeploy staging
automatically.

### Production rollback

Redeploy the previous good production tag or SHA:

```bash
gh workflow run deploy-production.yml -f ref=v1.13.5
```

This is the preferred rollback path because it reuses the same GitHub Actions
workflow, release metadata, and verification checks instead of requiring direct
SSH work.

### When direct server access is still needed

Direct SSH should be the exception, not the default. Use it only if GitHub
Actions cannot reach the self-hosted runner or the runner host itself is in a
broken state that prevents workflow execution.

## Codex Agent Deployment Runbook

Codex agents should follow this procedure:

1. Finish the implementation.
2. Run the smallest local verification that matches the change.
3. Commit changes if a commit is appropriate.
4. Push to `main`.
5. Monitor the `Deploy Staging` workflow for the exact pushed SHA.
6. If any job fails:
   - inspect the failing job logs
   - find the root cause
   - implement the smallest real fix
   - push to `main` again
   - repeat until staging is green
7. After staging succeeds, trigger production manually:

```bash
gh workflow run deploy-production.yml -f ref=main
```

8. Wait for `Deploy Production` to finish successfully.
9. Verify production health:
   - `https://gokz.top`
   - `https://api.gokz.top/v1/utils/health-check/`
10. Report the final status, including:
    - final `main` SHA
    - staging workflow result
    - production workflow result
    - deployed tag/version
    - any follow-up risks or manual checks still needed

Agents should prefer GitHub Actions, GitHub CLI, releases, tags, workflow logs,
and repository state. Do not default to SSH-based manual deployment when the
GitHub path is healthy.
