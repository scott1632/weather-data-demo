# Weather Data Demo

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

**Stop services (keep database):**

```bash
make down
```

**Reset everything (deletes database volume):**

```bash
make reset
```

This permanently deletes all local PostgreSQL data and runs a fresh setup.

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

View analytics staging data:

```bash
docker compose exec postgres psql -U weather_user -d weather_db -c \
  "SELECT * FROM analytics_staging.weather LIMIT 10;"
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
│   └── models/
│       ├── staging/             # Staging models and tests
│       └── sources/             # Source table definitions
│
└── cloudbeaver/                 # CloudBeaver config persistence
    ├── connections/
    └── workspace/
```

### Schemas

- **raw** — Full API responses (`weather_requests`) and hourly observations
  (`weather`)
- **metadata** — Pipeline run audit trail
- **analytics_staging** — dbt-transformed, production-ready weather data

## Portfolio highlights

**Data pipeline:**
- Idempotent delta load with deduplication at the observation level
- Transactional consistency across raw ingestion and metadata audit
- API retry logic and error handling

**Data transformation:**
- dbt models with staging and source definitions
- Data quality tests for uniqueness and nullability
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
