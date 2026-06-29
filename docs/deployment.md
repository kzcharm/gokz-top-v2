# GOKZ.TOP Deployment Workflow

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
