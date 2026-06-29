# Repository Guidelines

## Project Structure & Module Organization
- `backend/app/`: FastAPI service code. Routes live in `api/routes/`, shared settings in `core/`, models in `models.py`, and integrations in `services/`.
- `backend/app/alembic/versions/`: database migrations.
- `backend/tests/`: backend pytest suites for API routes, CRUD, services, and scripts.
- `frontend/src/`: React + TypeScript app. Routes are in `routes/`, shared UI in `components/`, hooks in `hooks/`, and generated API client code in `client/`.
- `frontend/tests/`: Playwright end-to-end tests.
- `scripts/` and root `compose*.yml`: local automation and Docker orchestration.

## Build, Test, and Development Commands
- `docker compose watch`: start the full local stack with live updates.
- `bun run dev`: run the frontend dev server.
- `cd backend && uv sync`: install backend dependencies.
- `cd backend && uv run bash scripts/lint.sh`: run backend `mypy`, `ruff check`, and format checks.
- `cd backend && uv run bash scripts/test.sh`: run backend tests and coverage reporting.
- `cd frontend && bun run build`: build the frontend for production.
- `bun run test`: run Playwright end-to-end tests.
- `bash scripts/generate-client.sh`: regenerate `frontend/src/client/` from the backend OpenAPI schema.

## Docker Data Safety
Never run `docker compose down -v`, `docker-compose down -v`, or any command that removes Docker volumes for this repository's local stack unless the user explicitly approves destroying local database state first. The local PostgreSQL data lives in the named Compose volume (for example `gokz-top-v2_app-db-data`), and removing volumes will permanently delete the user's local DB data.

## Coding Style & Naming Conventions
Use 4-space indentation in Python and explicit type hints; backend code is checked with strict `mypy` and `ruff`. Use `snake_case` for Python modules and functions.

Use UUIDv7 for new UUID fields/defaults and, when touching existing UUID default factories, migrate them to UUIDv7 unless there is a documented compatibility reason not to.

Frontend code uses TypeScript and Biome. Keep component filenames in `PascalCase` such as `DeleteUser.tsx`, hooks prefixed with `use`, and follow the formatter for quotes and semicolons.

## Testing Guidelines
Backend tests use `pytest` and live under `backend/tests/` as `test_*.py`. Frontend tests use Playwright and live under `frontend/tests/` as `*.spec.ts`. Keep backend coverage at or above 90%, and update or add tests whenever behavior changes.

## Commit & Pull Request Guidelines
Use Conventional Commit subjects so release automation can determine the correct semantic version bump, and write the subject so it can double as a user-facing update note.

Format:

```text
<type>(optional-scope): <user-facing problem solved or outcome>[; <technical implementation detail>]
```

Allowed primary types:

- `feat:` for user-facing features or meaningful new capabilities. This bumps the minor version.
- `fix:` for bug fixes, production fixes, regressions, and correctness changes. This bumps the patch version.
- `docs:` for documentation-only changes.
- `test:` for test-only changes.
- `chore:` for maintenance, tooling, CI, dependency, or operational-only changes.
- `refactor:` for behavior-preserving code restructuring.

When the thread starts with a user-facing request such as "fix something", "improve xxx", or "make xxx work", write the commit subject around what problem the change solves first. Put the common technical commit-message detail after that, separated by a semicolon, only when it adds useful context.

For frontend changes, include the exact affected route path in the user-facing part of the subject whenever there is a clear page or workflow route. Prefer concrete paths such as `/maps`, `/leaderboards`, `/profile/:identifier`, or `/settings/social-links` over vague areas like "maps page" or "profile UI". This lets the `/updates` page enrich release notes with direct "try it" links.

Examples:

```text
feat(maps): let server operators download map files from /maps; add R2-backed BSP links
feat(profile): show favorite servers on /profile/:identifier; add grouped favorite links
fix(r2): prevent small file uploads from failing; stream async upload bodies
fix(prod): make the frontend call the production API domain; route requests to api.gokz.top
docs(maps): explain how operators distribute map files
chore(ci): include map data in production deploys; add map data dir env
```

Do not use Title Case subjects like `Fix production domain routing` or `Implement map file distribution`; use `fix:` / `feat:` prefixes instead.

Normal development happens directly on `main`. Do not introduce a `dev -> main`
merge step for routine deployments; use the manual production deployment
workflow after staging succeeds instead.

Pull requests should include a clear summary, linked issues or discussions for larger changes, updated tests, and screenshots for UI work. Open a GitHub Discussion before major features or refactors.

## Memory Bank Workflow
Before writing code, read `memory-bank/tech-stack.md` for architecture and runtime constraints, plus `memory-bank/product-requirements-document.md` and `memory-bank/gokz-top-v1.md` for product scope and legacy behavior.

There is no schema document in `memory-bank/`. If your change touches persistence, use `backend/app/models.py` and `backend/app/alembic/versions/` as the schema reference.

After a major feature or completed milestone, update `memory-bank/tech-stack.md` and `memory-bank/product-requirements-document.md` if the architecture, scope, or constraints changed.

## Generated Files & Configuration
Do not hand-edit generated files in `frontend/src/client/` or `frontend/src/routeTree.gen.ts`. Keep secrets in local `.env` files.

For database schema changes, create migrations with Alembic autogenerate rather than writing migration files by hand.

## Temporary Artifact Workflow
Store disposable artifacts under `/.temp/` at the repository root. This includes screenshots, Playwright reports, test result files, ad-hoc exports, one-off debug logs, and scratch task folders.

Use task-specific subdirectories such as `/.temp/frontend/test-results`, `/.temp/frontend/playwright-report`, `/.temp/screenshots`, or `/.temp/<task-name>/`. Do not create temporary files at the repo root or inside tracked source directories unless the file is meant to be committed.

Before finishing a task, either delete ad-hoc artifacts or move them into `/.temp/`. Treat anything outside `/.temp/` as potentially commit-worthy.

## Documentation Workflow
Public documentation lives in the `notes/` submodule, backed by the separate `kzcharm/gokz-top-docs` repository.

When a change affects public behavior, APIs, plugin setup, rating logic, server operator workflows, or troubleshooting, update the docs in `notes/`.

When editing public docs, keep English and translated docs content-matched. If a page is added, removed, renamed, shortened, or materially changed in English, make the corresponding change in every available language under `notes/docs/` in the same task. Deleting or cleaning up a doc also means deleting or cleaning up its translated counterparts.

Before editing docs, initialize the submodule with `git submodule update --init --recursive` and make sure `notes/` is on a branch, not a detached HEAD.

Commit documentation changes inside `notes/` first. Update this parent repository's submodule pointer only when the app should pin a specific docs revision alongside a product or behavior change.
