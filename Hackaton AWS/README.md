# QueimAlerta Brasil

Interactive Python dashboard for monitoring near-real-time active-fire detections in Brazil.

> A satellite hotspot is not automatically a confirmed wildfire. The feed can include controlled burns, agricultural fires, other heat sources, and false positives.

## Current capabilities

- Imports the official INPE Brazil daily CSV feed and archives every downloaded snapshot.
- Validates coordinates and required source fields.
- Deduplicates records by the stable INPE `id`.
- Stores detections and ingestion runs in SQLite locally or PostgreSQL in containers.
- Displays an interactive Plotly map, time series, state ranking, filters, and recent-record table.
- Refreshes the browser dashboard every 60 seconds.
- Shows source freshness and pipeline status.
- Exposes separate liveness, readiness, and data-health endpoints.
- Emits structured JSON ingestion logs suitable for CloudWatch collection.

The detailed roadmap is in [`PROJECT_PLAN.md`](PROJECT_PLAN.md).

## Data source

The primary source is the [INPE Programa Queimadas open-data portal](https://terrabrasilis.dpi.inpe.br/queimadas/portal/dados-abertos/). The current adapter reads Brazil daily CSV files from the official INPE data server. Those files are updated during the day and contain source IDs, GMT observation time, coordinates, satellite, municipality, state, IBGE identifiers, biome, weather/fire-risk fields, and FRP when available.

Content describing external sources was rephrased for compliance with licensing restrictions.

## Run locally with Python

Python 3.12 or newer is required. From PowerShell, run the Windows launcher:

```powershell
.\run-local.cmd
```

The launcher creates `.venv` when needed, installs the project, initializes the local SQLite database, refreshes the latest INPE file, prints pipeline status, and starts the dashboard. Keep the terminal open while using it, then open <http://127.0.0.1:8050>. Press `Ctrl+C` to stop it.

Useful launcher options:

```powershell
# Start immediately from already downloaded data
.\run-local.cmd --skip-ingest

# Download the latest seven daily files before starting
.\run-local.cmd --days 7

# Prepare and validate everything without starting the web server
.\run-local.cmd --prepare-only
```

`run-local.ps1` provides the same workflow when PowerShell script execution is enabled. The `.cmd` launcher is the default because it does not require changing your execution policy.

You can also use the individual Python commands:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m queimalerta.cli init-db
.\.venv\Scripts\python.exe -m queimalerta.cli ingest --days 1
.\.venv\Scripts\python.exe -m queimalerta.dashboard.app
```

The source files can be large. Start with one day when checking a new setup.

## Run with Docker Compose

Docker is not required for direct Python execution. When Docker is available:

```powershell
docker compose up --build database dashboard
docker compose --profile jobs run --rm ingestion
```

The Compose stack uses PostgreSQL/PostGIS. The current first slice stores coordinates in indexed numeric columns and remains compatible with SQLite; native PostGIS geometry and viewport queries are scheduled in the next implementation phase.

## Configuration

Copy `.env.example` to `.env` and change values as needed. Environment variables override defaults.

| Variable | Default | Purpose |
|---|---|---|
| `QUEIMALERTA_DATABASE_URL` | `sqlite:///data/queimalerta.db` | SQLAlchemy database URL |
| `QUEIMALERTA_INPE_DAILY_URL` | official INPE Brazil daily directory | Source directory |
| `QUEIMALERTA_ARCHIVE_DIR` | `data/raw` | Raw snapshot archive |
| `QUEIMALERTA_REFRESH_SECONDS` | `60` | Browser refresh interval |
| `QUEIMALERTA_STALE_AFTER_MINUTES` | `30` | Stale-ingestion threshold |
| `QUEIMALERTA_MAX_MAP_POINTS` | `5000` | Maximum points sent to map |
| `QUEIMALERTA_HOST` | `127.0.0.1` | Web bind address |
| `QUEIMALERTA_PORT` | `8050` | Web port |
| `QUEIMALERTA_DEBUG` | `false` | Dash development mode |
| `QUEIMALERTA_LOG_LEVEL` | `INFO` | Application log level |

Do not commit `.env` or credentials.

## Commands

```powershell
queimalerta init-db
queimalerta ingest --days 1
queimalerta status
queimalerta-dashboard
```

In AWS, EventBridge Scheduler should invoke the ingestion container every 10 minutes. Do not embed a scheduler in the dashboard process because multiple web replicas would duplicate jobs.

## Health endpoints

- `GET /health/live`: confirms that the web process is running.
- `GET /health/ready`: checks database connectivity.
- `GET /health/data`: reports ingestion/data freshness and returns HTTP 503 when stale.

## Known first-slice limits

- AWS CDK infrastructure and CloudWatch alarms are not implemented yet.
- Coordinates are not yet stored as native PostGIS geometry.
- Municipality filtering and map viewport queries are planned next.
- The current dashboard retrieves at most 50,000 filtered rows for charts and 5,000 for map rendering.
- There is no authentication; do not expose this development build as an administrative interface.
