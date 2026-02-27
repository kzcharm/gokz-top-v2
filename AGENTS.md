# Repository Guidelines

## Project Structure & Module Organization
This repository is a full-stack FastAPI template with separate backend and frontend apps.

- `backend/app/`: FastAPI code (routes in `api/routes/`, models in `models.py`, shared config in `core/`).
- `backend/tests/`: Pytest suites for API, CRUD, scripts, and utilities.
- `frontend/src/`: React + TypeScript app (routes, components, hooks, utils).
- `frontend/tests/`: Playwright end-to-end tests (`*.spec.ts`).
- `scripts/`: root automation (`test.sh`, `generate-client.sh`).
- `compose*.yml`: local/prod stack orchestration.

## Build, Test, and Development Commands
Use these commands from repository root unless noted:

- `docker compose watch`: start local stack (backend, frontend, db, tooling).
- `bun run dev`: run frontend dev server via workspace script.
- `cd backend && uv sync`: install backend dependencies.
- `cd backend && uv run bash scripts/lint.sh`: run `mypy`, `ruff check`, and format checks.
- `cd backend && uv run bash scripts/test.sh`: run backend tests with coverage output.
- `bun run test`: run frontend Playwright tests.
- `bash scripts/generate-client.sh`: regenerate `frontend/src/client/*` from backend OpenAPI.

## Coding Style & Naming Conventions
- Python: 4-space indentation, `snake_case` for functions/modules, type hints required (mypy strict).
- TypeScript/React: Biome-formatted, spaces for indentation, double quotes, semicolons as needed.
- Components use `PascalCase` filenames (for example `DeleteUser.tsx`); hooks use `useX` naming.
- Do not hand-edit generated frontend client files in `frontend/src/client/` or `frontend/src/routeTree.gen.ts`.

## Testing Guidelines
- Backend: Pytest tests in `backend/tests/`, file pattern `test_*.py`.
- Frontend: Playwright tests in `frontend/tests/`, file pattern `*.spec.ts`.
- CI enforces backend coverage (`coverage report --fail-under=90`), so keep coverage at or above 90%.
- Add or update tests whenever behavior changes.

## Commit & Pull Request Guidelines
- Commit messages in history are short and imperative, often with emoji prefixes (for example `⬆ Bump ...`, `📝 Update release notes`).
- Keep commits focused and scoped to one change.
- For PRs: ensure lint/tests pass, describe the change clearly, link related issues, and include screenshots for UI updates.
- For large features or refactors, open a GitHub Discussion before implementation.
