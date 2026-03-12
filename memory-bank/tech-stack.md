# Tech Stack - GOKZ.TOP v2

- Last Updated: 2026-03-12
- Source of truth: `backend/pyproject.toml`, `frontend/package.json`, `compose.yml`

## Architecture
- Monorepo with:
  - FastAPI backend in `backend/`
  - React + TypeScript frontend in `frontend/`
- API surfaces:
  - `/v0` for GlobalAPI v2.0 compatibility behavior
  - `/v1` for project-native endpoints
- Data strategy:
  - PostgreSQL as primary persistent store
  - PostgreSQL-centric derived/cache artifacts (no Redis runtime dependency)

## Backend Runtime and Libraries
- Python `>=3.14,<4.0`
- FastAPI (`fastapi[standard]`)
- Pydantic v2
- SQLModel
- Alembic
- psycopg3 (`psycopg[binary]`)
- pydantic-settings
- httpx
- python-multipart
- tenacity
- pyjwt
- pwdlib (`argon2`, `bcrypt`)
- sentry-sdk (FastAPI integration)

## Backend Quality Tooling
- uv for environment and dependency management
- Ruff for linting
- mypy (strict mode)
- pytest + pytest-asyncio
- coverage (CI threshold target >= 90%)

## Frontend Runtime and Libraries
- React 19
- TypeScript 5.9
- Vite 7 + `@vitejs/plugin-react-swc`
- Tailwind CSS 4 + `@tailwindcss/vite`
- Radix UI primitives
- TanStack:
  - React Router
  - React Query
  - React Table
- Forms and validation:
  - react-hook-form
  - @hookform/resolvers
  - zod
- HTTP and utilities:
  - axios
  - clsx
  - class-variance-authority
  - tailwind-merge
- UI helpers:
  - next-themes
  - sonner
  - lucide-react
  - react-icons
- Generated API client:
  - @hey-api/openapi-ts

## Frontend Tooling and Tests
- Bun workspace scripts at repository root
- Biome for linting/formatting
- Playwright for end-to-end tests

## Infrastructure and Operations
- Docker + Docker Compose
- PostgreSQL 18 container (`postgres:18`)
- Traefik for reverse proxy/routing
- Adminer for DB admin
- Frontend served by Nginx in production container

## External Integrations
- Steam OpenID and Steam Web API integration paths exist in backend flows.
- GlobalAPI endpoints are consumed for synchronization/compatibility behavior.

## Implementation Constraints
- Do not hand-edit generated frontend files:
  - `frontend/src/client/*`
  - `frontend/src/routeTree.gen.ts`
- Keep compatibility behavior under `/v0` stable; project-native changes should go to `/v1`.
