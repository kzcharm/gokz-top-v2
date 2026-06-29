---
name: deploy-main-after-green-staging
description: Use when an agent needs to push `main`, monitor the exact staging workflow triggered by that push, fix any failing CI or deploy steps with minimal targeted changes, and manually promote the same `main` SHA to production after staging is green.
---

# Deploy Main After Green Staging

This skill is repository-specific for `kzcharm/gokz-top-v2`.

Use it when the task is to:

- push the current `main` branch
- monitor the workflows triggered by that push
- inspect and fix failing GitHub Actions checks
- manually deploy production only after the pushed `main` SHA is green on staging
- verify the resulting release is actually deployed to production

## Expected workflow set

For a push to `main`, track the runs for the exact pushed `head_sha`.

Expected workflows:

- `Conflict detector`
- `Deploy Staging`

Do not rely on branch-level status alone. Confirm the exact workflow runs
attached to the pushed SHA.

## GitHub auth and repo targeting

- Use the repo token via `GH_TOKEN="$GITHUB_TOKEN_KZCHARM"` for GitHub API and
  `gh` commands.
- Do not rely on ambient `gh` repo context. This machine may resolve `gh`
  against the wrong repository.
- Prefer explicit REST API calls like:
  - `gh api 'repos/kzcharm/gokz-top-v2/actions/runs?...'`
  - `gh api 'repos/kzcharm/gokz-top-v2/actions/runs/<run_id>/jobs'`
  - `gh api 'repos/kzcharm/gokz-top-v2/actions/jobs/<job_id>/logs'`

## Push and map the run set

1. Confirm the branch and local state with `git status --short --branch`.
2. Push `main` non-interactively with `git push origin main`.
3. Capture the pushed SHA with `git rev-parse HEAD`.
4. Resolve the triggered workflow runs with:

```bash
GH_TOKEN="$GITHUB_TOKEN_KZCHARM" gh api \
  'repos/kzcharm/gokz-top-v2/actions/runs?branch=main&event=push&per_page=20'
```

5. Filter to `.workflow_runs[] | select(.head_sha=="<sha>")`.

## Monitoring

- Use `gh run watch <run_id> --repo kzcharm/gokz-top-v2 --interval 10` for
  live progress.
- Watch multiple runs in parallel when possible.
- Reconfirm final conclusions with one last `gh api` query on the exact
  `head_sha`.

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

## Production promotion

After staging is green for the pushed `main` SHA:

1. Capture the final `origin/main` SHA.
2. Trigger production manually for that SHA or for `main`:

```bash
GH_TOKEN="$GITHUB_TOKEN_KZCHARM" gh workflow run deploy-production.yml \
  --repo kzcharm/gokz-top-v2 \
  -f ref=<green-main-sha>
```

3. Inspect recent releases and tags:

```bash
GH_TOKEN="$GITHUB_TOKEN_KZCHARM" gh api \
  'repos/kzcharm/gokz-top-v2/releases?per_page=5'
```

4. Verify the production host is serving the expected release:

```bash
curl -sS https://gokz.top | rg -o 'assets/index-[^" ]+\.js|v[0-9]+\.[0-9]+\.[0-9]+'
curl -sS https://api.gokz.top/v1/utils/health-check/
```

If `gokz.top` still shows an older version, or the latest `main` changes are
not visible, treat the task as not done even if the workflow succeeded.

## Manual release fallback

Use this only when the `Deploy Production` workflow cannot create the release
tag or GitHub is failing operationally.

1. Determine the next patch or minor version from the latest semver release.
2. Create the missing release/tag against the exact final `origin/main` SHA:

```bash
GH_TOKEN="$GITHUB_TOKEN_KZCHARM" gh release create vX.Y.Z \
  --repo kzcharm/gokz-top-v2 \
  --target <main_sha> \
  --title vX.Y.Z \
  --notes '<short release notes>'
```

3. Re-run the production deploy for that tag:

```bash
GH_TOKEN="$GITHUB_TOKEN_KZCHARM" gh workflow run deploy-production.yml \
  --repo kzcharm/gokz-top-v2 \
  -f ref=vX.Y.Z
```

## Clean-worktree pattern

If the main checkout has unrelated uncommitted changes, do not fix CI directly
there.

Use a temporary clean worktree from the pushed SHA:

```bash
git worktree add /private/tmp/gokz-top-v2-ci-fix <sha>
```

Use the clean worktree to:

- inspect the failing code at the pushed revision
- patch the minimal fix
- run focused verification
- commit the fix cleanly

Then apply that fix back to the real `main` branch with
`git cherry-pick <fix_commit>`.

## Sandbox and permission notes

This environment may block writes under `.git`, including:

- `.git/worktrees/*`
- `.git/index.lock`
- `.git/FETCH_HEAD`

When that happens, request escalation for the specific git command instead of
working around it.
