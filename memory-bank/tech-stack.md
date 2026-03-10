# Tech Stack

This repository is a FastAPI + React rewrite of the GlobalAPI-compatible GOKZ.TOP platform. It keeps strict GlobalAPI v2 public API compatibility and adds v3 endpoints on top of a PostgreSQL-only data and cache layer.

## Backend
- Python 3.14
- FastAPI (fastapi[standard]) and Pydantic v2
- SQLModel ORM and Alembic migrations
- psycopg3 PostgreSQL driver
- pydantic-settings for config
- httpx for outbound HTTP
- python-multipart for upload handling
- pyjwt for JWT handling
- pwdlib with argon2 and bcrypt for password hashing
- tenacity for retries
- Sentry SDK for error reporting

## Data and Cache
- PostgreSQL 18
- Postgres-only cache strategy with unlogged tables and materialized views
- No Redis dependency by design

## Frontend
- React 19 and TypeScript 5.9
- Vite 7 with SWC
- Tailwind CSS 4 with tailwind-merge and class-variance-authority
- Radix UI primitives
- TanStack Router, Query, and Table
- React Hook Form with @hookform/resolvers and Zod
- Axios for HTTP
- next-themes for theming
- lucide-react and react-icons for icons
- sonner for toasts
- OpenAPI client generation via @hey-api/openapi-ts

## Tooling and Tests
- Bun for package management and scripts
- Biome for frontend linting and formatting
- Playwright for frontend E2E tests
- uv for Python dependency management
- Ruff for Python linting
- mypy for Python type checking
- pytest and pytest-asyncio for backend tests
- coverage for test coverage reporting

## Infra and Deployment
- Docker and Docker Compose
- Traefik as reverse proxy for frontend and backend
- Nginx serving the frontend build
- Adminer for database administration

## Compatibility Target (Legacy Reference)
- GlobalAPI v2 compatibility target is based on an ASP.NET Core stack with Dapper, MySQL, Redis, Hangfire, and NLog
- Those components are not used in this repository but are the contract and behavior reference for parity work
