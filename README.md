# GOKZ.TOP v2

GOKZ.TOP v2 is the FastAPI, React, and SourceMod-backed platform for GOKZ records, rankings, server status, player profiles, jumpstats, replays, and server-operator tooling.

## Repository Layout

- `backend/`: FastAPI service, SQLModel models, Alembic migrations, background tasks, and pytest suites.
- `frontend/`: React + TypeScript app with TanStack Router, TanStack Query, Tailwind CSS, and generated API client code.
- `sourcemod/`: SourceMod plugin submodule for `kzcharm/gokz-top-plugins`.
- `memory-bank/`: product and architecture notes that guide implementation.
- `notes/`: public documentation submodule.

## Local Development

Start the full stack with Docker Compose:

```bash
docker compose watch
```

Run the frontend only:

```bash
bun run dev
```

Run backend checks:

```bash
cd backend
uv sync
uv run bash scripts/lint.sh
uv run bash scripts/test.sh
```

Run the frontend production build:

```bash
cd frontend
bun run build
```

Regenerate the frontend API client after backend OpenAPI changes:

```bash
bash scripts/generate-client.sh
```

## SourceMod Plugin Setup

Server-side integration is provided by [`kzcharm/gokz-top-plugins`](https://github.com/kzcharm/gokz-top-plugins). The admin server page at `https://gokz.top/admin/servers` includes an install link to that repository.

### 1. Create Or Select A Server Group

1. Sign in to `https://gokz.top`.
2. Open `https://gokz.top/admin/servers`.
3. Go to the `Server Group` tab.
4. Create a group for your community or select an existing group you own.
5. Copy the group API key from the `API Key` column.

The API key authenticates SourceMod requests with the `X-Server-Group-Key` header. Treat it like a secret. If it leaks, regenerate it from the same `Server Group` tab and update every server using the old key.

### 2. Install The Plugin Package

1. Open [`kzcharm/gokz-top-plugins`](https://github.com/kzcharm/gokz-top-plugins).
2. Download the latest release package.
3. Copy the package contents into your CS:GO server so the `addons/` and `cfg/` paths merge with the server's existing SourceMod installation.
4. Restart the server or load the plugins through SourceMod.

The plugins expect an existing GOKZ and SourceMod setup. Keep GOKZ, SourceMod, and required extension dependencies installed before enabling the GOKZ.TOP plugins.

### 3. Apply The API Key

After `gokz-top-core` starts once, it creates:

```text
cfg/sourcemod/gokz-top/apikey.cfg
```

Paste the copied server group API key directly in that file:

```cfg
paste-your-server-group-api-key-here
```

The older `gokz_top_api_key "paste-your-server-group-api-key-here"` format is still supported. Then reload the API key or restart the server:

```cfg
gokz_top_reload_api_key
```

The default API base URL points at production. For a custom deployment, set `gokz_top_api_base_url` in the generated GOKZ.TOP config to the API origin without a trailing slash.

### 4. Link Servers To The Group

Back on `https://gokz.top/admin/servers`, assign your GlobalAPI or public server rows to the same server group. Once the plugin is running with the API key, the site can accept live server status, player-session events, reviews, and other authenticated server-side submissions for that group.

## Deployment Configuration

Set production secrets through environment variables, never in committed files. At minimum configure:

- `SECRET_KEY`
- `POSTGRES_PASSWORD`
- `SUPER_USER_STEAMID64`
- `STEAM_API_KEY`

See [docs/deployment.md](./docs/deployment.md) and [development.md](./development.md) for Docker, Traefik, and environment details.
