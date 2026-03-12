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

## Coding Style & Naming Conventions
Use 4-space indentation in Python and explicit type hints; backend code is checked with strict `mypy` and `ruff`. Use `snake_case` for Python modules and functions.

Frontend code uses TypeScript and Biome. Keep component filenames in `PascalCase` such as `DeleteUser.tsx`, hooks prefixed with `use`, and follow the formatter for quotes and semicolons.

## Testing Guidelines
Backend tests use `pytest` and live under `backend/tests/` as `test_*.py`. Frontend tests use Playwright and live under `frontend/tests/` as `*.spec.ts`. Keep backend coverage at or above 90%, and update or add tests whenever behavior changes.

## Commit & Pull Request Guidelines
Recent history favors short, focused commit messages such as `Fix missing frontend Vite install`. Keep each commit scoped to one change.

Pull requests should include a clear summary, linked issues or discussions for larger changes, updated tests, and screenshots for UI work. Open a GitHub Discussion before major features or refactors.

## Memory Bank Workflow
Before writing code, read `memory-bank/tech-stack.md` for architecture and runtime constraints, plus `memory-bank/product-requirements-document.md` and `memory-bank/gokz-top-v1.md` for product scope and legacy behavior.

There is no schema document in `memory-bank/`. If your change touches persistence, use `backend/app/models.py` and `backend/app/alembic/versions/` as the schema reference.

After a major feature or completed milestone, update `memory-bank/tech-stack.md` and `memory-bank/product-requirements-document.md` if the architecture, scope, or constraints changed.

## Generated Files & Configuration
Do not hand-edit generated files in `frontend/src/client/` or `frontend/src/routeTree.gen.ts`. Keep secrets in local `.env` files.

For database schema changes, create migrations with Alembic autogenerate rather than writing migration files by hand.
