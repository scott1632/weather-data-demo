# Weather Data Demo

[![Python CI](https://github.com/scott1632/weather-data-demo/actions/workflows/python-ci.yml/badge.svg)](https://github.com/scott1632/weather-data-demo/actions/workflows/python-ci.yml)
[![dbt CI](https://github.com/scott1632/weather-data-demo/actions/workflows/dbt-ci.yml/badge.svg)](https://github.com/scott1632/weather-data-demo/actions/workflows/dbt-ci.yml)
[![Sanity Check](https://github.com/scott1632/weather-data-demo/actions/workflows/sanity.yml/badge.svg)](https://github.com/scott1632/weather-data-demo/actions/workflows/sanity.yml)

A containerised data-engineering project that retrieves hourly forecast data
from the [Open-Meteo API](https://open-meteo.com/), stores observations in
PostgreSQL, and transforms them using dbt for analytics.

The project demonstrates a complete analytics stack: raw data ingestion with
audit records, idempotent delta loading, dbt transformations with tests, and
tools for exploration and documentation. Built entirely in Docker for repeatable
local development.

## Architecture

```text
Open-Meteo API → Python ingestion → PostgreSQL (raw schema)
                                  ↓
                            dbt models (analytics schema)
                                  ↓
                     CloudBeaver UI + dbt-docs
```

### Data flow

**Ingestion pipeline:**

1. Fetches hourly temperature, apparent temperature, precipitation, wind speed,
   and weather code for the configured location.
2. Saves the complete API response to `raw.weather_requests` and receives a
   `request_id`.
3. Upserts hourly observations into `raw.weather`, unique by observation time
   and coordinates.
4. Associates updated observations with the newest `request_id`, preserving
   lineage to the source API payload.
5. Records a successful load in `metadata.pipeline_runs`.

All operations occur in a single database transaction—a failed load rolls back
rather than leaving partially loaded data.

**Transformation pipeline:**

dbt models transform raw weather data into an analytics-ready schema with:
- Staging models that clean and denormalize raw observations
- Tests to validate data quality and uniqueness
- Documentation of all tables and columns

## Continuous integration

Every pull request into `main` or `dev` runs three GitHub Actions workflows
(`.github/workflows/`), and all three must pass before a PR can be merged:

- **Python CI** — `black --check` and `flake8` against `ingestion/`
- **dbt CI** — starts PostgreSQL via Docker Compose, runs ingestion, then
  `dbt build` against real data
- **Sanity Check** — validates `docker-compose.yml` with `docker compose config`

## Requirements

- Docker Engine with Docker Compose
- GNU Make

No host Python installation is required for normal use: Python and project
dependencies are installed in the ingestion container.

## Configuration

Create a local environment file from the example:

```bash
cp .env.example .env
```

Ensure `.env` contains these values:

```dotenv
# PostgreSQL
POSTGRES_USER=weather_user
POSTGRES_PASSWORD=choose-a-local-password
POSTGRES_DB=weather_db
POSTGRES_HOST=postgres
POSTGRES_PORT=5432

# Open-Meteo location
OPEN_METEO_LATITUDE=51.5000
OPEN_METEO_LONGITUDE=-0.1200
OPEN_METEO_TIMEZONE=Europe/London

# Docker networking (don't change if using make setup)
DOCKER_NETWORK=data-platform

# Web UI ports
CLOUDBEAVER_PORT=8978
DBT_DOCS_PORT=8082
```

**Configuration notes:**

- `OPEN_METEO_LATITUDE`, `OPEN_METEO_LONGITUDE`, and `OPEN_METEO_TIMEZONE`
  determine the forecast location.
- `CLOUDBEAVER_PORT` is the port for the database UI (http://localhost:8978).
- `DBT_DOCS_PORT` is the port for dbt documentation (http://localhost:8082).
- The `.env` file is ignored by Git, so credentials are not committed.
- The Makefile creates the `data-platform` network; if you use a different
  `DOCKER_NETWORK`, create that external Docker network manually.

## Quick start

**First time setup:**

```bash
make setup
```

This creates the Docker network, starts PostgreSQL, runs ingestion, and
transforms data with dbt.

**Run another ingestion:**

```bash
make ingest
```

**Rebuild dbt models:**

```bash
make build
```

**Run dbt tests:**

```bash
make test
```

**View dbt documentation:**

```bash
make docs
```

Then open http://localhost:8082 to explore your models, tests, and lineage.

**Access the Streamlit dashboard:**

```bash
make app
```

Or simply run `docker compose up -d streamlit`. Then open http://localhost:8501 to view the dashboard.

The dashboard displays:
- **Header:** Database connection status, last pipeline run time, test results summary
- **Main content:** Weather analytics charts, data quality test results grouped by test type
- **Sidebar:** Quick action buttons (Ingest, Build, Test), key metrics, recent pipeline history, and links to tools

**Stop services (keep database):**

```bash
make down
```

**Reset everything (deletes database volume):**

```bash
make reset
```

This permanently deletes all local PostgreSQL data and runs a fresh setup.

**Fresh start (skip ingestion pipeline, use dashboard to run manually):**

```bash
make fresh
```

Stops all services, removes the database volume, and starts only PostgreSQL, Streamlit, CloudBeaver, and dbt-docs. Use the Streamlit dashboard to manually run ingestion, dbt build, and tests. Useful for testing the UI without waiting for full pipeline runs.

**Full cleanup:**

```bash
make clean
```

Stops all services and removes the database volume. For deep cleanup (removing Docker images and networks), uncomment the destructive lines in the Makefile. See "Advanced cleanup" below.

### Advanced cleanup (destructive)

If you need to rebuild Docker images from scratch or reset the Docker network, uncomment these lines in the Makefile targets (`setup`, `reset`, `fresh`, `clean`):

```bash
# docker image rm -f weather-data-demo-ingestion weather-data-demo-dbt weather-data-demo-streamlit
# docker network rm data-platform 2>/dev/null || true
# docker network create data-platform
```

These commands:
- **Remove images:** Forces a fresh build of all project containers (useful if you update dependencies or Dockerfiles)
- **Remove network:** Resets Docker networking (useful if you have connectivity issues or want to start completely fresh)

⚠️ These are commented out by default because they're irreversible. Only use them if:
1. You've made changes to `Dockerfile` or `requirements.txt` and need a clean rebuild
2. You're troubleshooting Docker network issues
3. You want to completely remove all traces of the project from Docker

## Query your data

### CloudBeaver UI

Open http://localhost:8978 to query the database with a web interface.

First-time setup:
1. Create a new PostgreSQL connection
2. Host: `postgres`
3. Port: `5432`
4. User: `weather_user` (from `.env`)
5. Password: (from `.env`)
6. Database: `weather_db`

### Command line

Inspect the current weather row count and latest source request:

```bash
docker compose exec postgres psql -U weather_user -d weather_db -c \
  "SELECT request_id, COUNT(*) AS weather_rows
   FROM raw.weather
   GROUP BY request_id
   ORDER BY request_id;"
```

After two runs for the same forecast window, the number of rows in `raw.weather`
should remain stable while pointing to the newer `request_id`. This demonstrates
idempotent delta loading—duplicate observations are not inserted.

View pipeline run history:

```bash
docker compose exec postgres psql -U weather_user -d weather_db -c \
  "SELECT pipeline_name, status, rows_loaded, started_at, completed_at
   FROM metadata.pipeline_runs
   ORDER BY run_id;"
```

View analytics data (fact table with clean column names and units):

```bash
docker compose exec postgres psql -U weather_user -d weather_db -c \
  "SELECT observation_time, temperature_c, wind_speed_kmh, precipitation_mm
   FROM analytics.fact_weather_observation
   ORDER BY observation_time DESC LIMIT 10;"
```

## Project structure

```text
.
├── docker-compose.yml           # All services (postgres, ingestion, dbt, etc.)
├── Makefile                     # Helpful commands (setup, ingest, build, etc.)
├── .env.example                 # Environment template
│
├── postgres/
│   └── init.sql                 # Raw and metadata schemas; tables
│
├── ingestion/
│   ├── Dockerfile               # Python 3.12 image
│   ├── ingest.py                # API fetch, deduplicate, database load
│   └── requirements.txt         # Dependencies (requests, psycopg2, etc.)
│
├── dbt/
│   ├── Dockerfile               # dbt image
│   ├── dbt_project.yml          # dbt project config
│   ├── profiles.yml             # dbt PostgreSQL connection
│   ├── macros/                  # dbt macros (schema name generation)
│   ├── tests/                   # Custom data quality tests
│   └── models/
│       ├── staging/             # Cleaned, deduplicated observations
│       ├── marts/               # Analytics-ready fact tables
│       └── sources/             # Source table definitions
│
└── cloudbeaver/                 # CloudBeaver config persistence
    ├── connections/
    └── workspace/
```

### Schemas

- **raw** — Full API responses (`weather_requests`) and hourly observations
  (`weather`)
- **metadata** — Pipeline run audit trail (`pipeline_runs`)
- **staging** — dbt staging models: cleaned and deduplicated observations
- **analytics** — dbt mart models: `fact_weather_observation` for analysis

## Portfolio highlights

**Data pipeline:**
- Idempotent delta load with deduplication at the observation level
- Transactional consistency across raw ingestion and metadata audit
- API retry logic and error handling

**Data transformation:**
- dbt models: staging layer for cleaning + mart layer for analytics
- Data quality tests: 17 tests including not_null, unique, and custom range validations
- Temperature range test catches unrealistic values (< -80°C or > 70°C)
- Version-controlled transformation logic and documentation

**Local development:**
- Docker Compose for reproducible infrastructure
- Single-command setup via `make setup`
- CloudBeaver web UI for exploratory queries
- dbt-docs for self-documenting data lineage
- PostgreSQL for production-like querying

**Key concepts:**
- Event-based data architecture (immutable raw layer)
- Slowly changing dimensions (latest observation tracking)
- Audit trails for data observability
- Containerization for portability and repeatability
