# Weather Data Demo

[![Python CI](https://github.com/scott1632/weather-data-demo/actions/workflows/python-ci.yml/badge.svg)](https://github.com/scott1632/weather-data-demo/actions/workflows/python-ci.yml)
[![dbt CI](https://github.com/scott1632/weather-data-demo/actions/workflows/dbt-ci.yml/badge.svg)](https://github.com/scott1632/weather-data-demo/actions/workflows/dbt-ci.yml)
[![Sanity Check](https://github.com/scott1632/weather-data-demo/actions/workflows/sanity.yml/badge.svg)](https://github.com/scott1632/weather-data-demo/actions/workflows/sanity.yml)

A containerised data-engineering project that retrieves hourly forecast data
from the [Open-Meteo API](https://open-meteo.com/), stores observations in
PostgreSQL, transforms them using dbt for analytics, and orchestrates the
whole thing hourly with Apache Airflow.

The project demonstrates a complete analytics stack: raw data ingestion with
audit records, idempotent delta loading, dbt transformations with tests,
Airflow orchestration, and tools for exploration and documentation. Built
entirely in Docker for repeatable local development.

## Architecture

```text
Airflow (weather_pipeline DAG, @hourly)
        │
        ▼
Open-Meteo API → Python ingestion → PostgreSQL (raw schema)
                                  ↓
                            dbt models (analytics schema)
                                  ↓
                     CloudBeaver UI + dbt-docs + Streamlit
```

Airflow orchestrates the same ingestion/dbt code the Streamlit dashboard's
"Quick Actions" buttons and `make ingest`/`make build`/`make test` already
run — there's one `ingestion/` and one `dbt/` directory, bind-mounted into
whichever service runs them, not a separate copy per consumer.

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
5. Records the run's outcome — `SUCCESS` or `FAILED`, with an error message
   on failure — in `metadata.pipeline_runs`.

All operations occur in a single database transaction—a failed load rolls back
rather than leaving partially loaded data.

**Transformation pipeline:**

dbt models transform raw weather data into an analytics-ready schema with:
- Staging models that clean and denormalize raw observations
- Tests to validate data quality and uniqueness
- Documentation of all tables and columns

**Orchestration:**

Apache Airflow runs the `weather_pipeline` DAG hourly: `ingest_weather` →
`dbt_build` → `dbt_test`, each a `PythonOperator`/`BashOperator` running the
project's own `ingestion`/`dbt` code directly inside the Airflow container
(no `DockerOperator`, no Docker-socket mount, no separate sibling images to
build and keep in sync). `dbt_build`/`dbt_test` record their outcome to
`metadata.pipeline_runs` the same way the ingestion step and the Streamlit
buttons do, so Airflow-triggered, dashboard-triggered, and CLI-triggered runs
all land in one consistent, honest audit trail — a run that fails is recorded
as `FAILED` with a reason, not silently missing.

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

# Web UI ports
CLOUDBEAVER_PORT=8978
STREAMLIT_PORT=8501
DBT_DOCS_PORT=8082
AIRFLOW_PORT=8088

# Airflow webserver session key + default admin user (created once at init)
AIRFLOW_WEBSERVER_SECRET_KEY=change-me-for-anything-beyond-local-dev
AIRFLOW_ADMIN_USERNAME=admin
AIRFLOW_ADMIN_PASSWORD=admin
```

**Configuration notes:**

- `OPEN_METEO_LATITUDE`, `OPEN_METEO_LONGITUDE`, and `OPEN_METEO_TIMEZONE`
  determine the forecast location.
- `CLOUDBEAVER_PORT` is the port for the database UI (http://localhost:8978).
- `DBT_DOCS_PORT` is the port for dbt documentation (http://localhost:8082).
- `AIRFLOW_PORT` is the port for the Airflow webserver (http://localhost:8088,
  log in with `AIRFLOW_ADMIN_USERNAME`/`AIRFLOW_ADMIN_PASSWORD`).
- The `.env` file is ignored by Git, so credentials are not committed.
- The Docker network is compose-managed (a plain bridge network) — no manual
  network creation is needed, unlike some Compose setups you may have seen
  that require a pre-existing external network.

## Quick start

**First time setup:**

```bash
make setup
```

This starts PostgreSQL, runs ingestion, transforms data with dbt, and brings
up Airflow (webserver + scheduler) with the `weather_pipeline` DAG ready to
run hourly.

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
- **Main content:** Weather analytics charts (with a small map of the configured location), data quality test results grouped by test type
- **Sidebar:** Quick action buttons (Ingest, Build, Test), key metrics, recent pipeline history, and links to tools

**Access Airflow:**

`make setup` already starts the webserver and scheduler. Open
http://localhost:8088 and log in with `AIRFLOW_ADMIN_USERNAME`/
`AIRFLOW_ADMIN_PASSWORD` from `.env` (`admin`/`admin` by default). The
`weather_pipeline` DAG runs `ingest_weather` → `dbt_build` → `dbt_test`
hourly — trigger it manually from the UI ("Trigger DAG" button) to see it
run immediately rather than waiting for the schedule.

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

Stops all services, removes the database volume, and starts only PostgreSQL, Streamlit, CloudBeaver, dbt-docs, and Airflow. Use the Streamlit dashboard or the Airflow UI to manually run ingestion, dbt build, and tests. Useful for testing the UI without waiting for full pipeline runs.

**Full cleanup:**

```bash
make clean
```

Stops all services and removes the database volume. For deep cleanup (removing Docker images), uncomment the destructive line in the Makefile. See "Advanced cleanup" below.

### Advanced cleanup (destructive)

If you need to rebuild Docker images from scratch (e.g. after changing a `Dockerfile` or `requirements.txt`), uncomment this line in the Makefile targets (`fresh`, `clean`):

```bash
# docker image rm -f weather-data-demo-ingestion weather-data-demo-dbt weather-data-demo-streamlit
```

This forces a fresh build of all project containers. It's commented out by default because it's irreversible — only use it if you want to guarantee a clean rebuild rather than reusing cached image layers.

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

View pipeline run history (a failed run shows `FAILED` with `error_message`
populated, not a missing row):

```bash
docker compose exec postgres psql -U weather_user -d weather_db -c \
  "SELECT pipeline_name, status, rows_loaded, error_message, started_at, completed_at
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
├── docker-compose.yml           # All services (postgres, ingestion, dbt, airflow, etc.)
├── Makefile                     # Helpful commands (setup, ingest, build, etc.)
├── .env.example                 # Environment template
├── requirements-dev.txt         # pytest, for tests/ below
├── tests/                       # Unit tests for ingestion/ingest.py (no live DB needed)
│
├── postgres/
│   └── init.sql                 # airflow DB + raw/metadata/analytics schemas and tables
│
├── ingestion/
│   ├── Dockerfile               # Python 3.12 image
│   ├── __init__.py              # makes this importable as `ingestion.ingest` from Airflow
│   ├── ingest.py                # API fetch, deduplicate, database load, audit-trail logging
│   └── requirements.txt         # Dependencies (requests, psycopg, etc.)
│
├── dbt/
│   ├── Dockerfile               # dbt image
│   ├── dbt_project.yml          # dbt project config
│   ├── profiles.yml             # dbt PostgreSQL connection
│   ├── macros/                  # dbt macros (schema name generation)
│   ├── tests/                   # Custom data quality tests
│   └── models/
│       ├── staging/             # Cleaned, renamed observations (dedup happens
│       │                        #   upstream via Postgres ON CONFLICT in ingest.py)
│       ├── marts/               # Analytics-ready fact tables
│       └── sources/             # Source table definitions
│
├── airflow/
│   ├── Dockerfile               # Airflow image + ingestion/dbt deps installed in-process
│   └── dags/
│       └── weather_pipeline_dag.py  # ingest_weather -> dbt_build -> dbt_test, hourly
│
├── streamlit/
│   ├── Dockerfile
│   └── app.py                   # Dashboard: charts, quick actions, pipeline history
│
└── cloudbeaver/                 # CloudBeaver config persistence
    ├── connections/
    └── workspace/
```

### Schemas

All in the `weather_db` database:

- **raw** — Full API responses (`weather_requests`) and hourly observations
  (`weather`)
- **metadata** — Pipeline run audit trail (`pipeline_runs`, with `status`
  and `error_message` reflecting the real outcome of every run)
- **staging** — dbt staging models: cleaned and renamed observations
  (deduplication itself happens upstream, via Postgres's `ON CONFLICT` in
  `ingestion/ingest.py` — staging models don't dedupe)
- **analytics** — dbt mart models: `fact_weather_observation` for analysis

Airflow's own task/DAG metadata lives in a separate `airflow` database on
the same Postgres instance — kept apart from this project's own schemas
rather than mixed in.

## Portfolio highlights

**Data pipeline:**
- Idempotent delta load with deduplication at the observation level
- Transactional consistency across raw ingestion and metadata audit
- API retry logic and error handling
- Honest audit trail: `metadata.pipeline_runs` records `SUCCESS`/`FAILED`
  with an error message for every run, whether triggered by Airflow, the
  Streamlit dashboard, or a manual `make ingest`/`build`/`test` — a failure
  is never silently missing from the history

**Orchestration:**
- Apache Airflow DAG (`ingest_weather` → `dbt_build` → `dbt_test`, hourly)
  running the same `ingestion`/`dbt` code as every other entry point, not a
  separate copy
- No `DockerOperator`/Docker-socket dependency — tasks run in-process in the
  Airflow container, so the DAG is self-contained and doesn't depend on
  sibling images being built elsewhere

**Data transformation:**
- dbt models: staging layer for cleaning + mart layer for analytics
- Data quality tests: `not_null`/`unique` schema tests on every key column
  across sources, staging, and marts, plus a custom range-validation test —
  run `dbt test` (or check CI) for the current count rather than trusting a
  number here, since it'll drift as models are added
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
