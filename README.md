# Weather Data Demo

A containerised Python weather-ingestion project. It retrieves hourly forecast
data from the [Open-Meteo API](https://open-meteo.com/), stores the original API
response in PostgreSQL, and maintains a current, deduplicated weather table.

The project is designed as a small data-engineering portfolio demo: it includes
repeatable local infrastructure, ingestion audit records, API retry handling,
and an idempotent delta load.

## How it works

```text
Open-Meteo API -> Python ingestion -> PostgreSQL
                               |-> raw.weather_requests (full API payload)
                               |-> raw.weather (latest hourly values)
                               |-> metadata.pipeline_runs (run audit)
```

Each ingestion run:

1. Fetches hourly temperature, apparent temperature, precipitation, wind
   speed, and weather code for the configured location.
2. Saves the complete response to `raw.weather_requests` and receives a
   `request_id`.
3. Upserts hourly observations into `raw.weather`, unique by observation time
   and coordinates.
4. Associates updated observations with the newest `request_id`, preserving
   lineage to the payload that supplied their current values.
5. Records a successful load in `metadata.pipeline_runs`.

The request insert, weather upsert, and run audit are performed in one database
transaction. A failed load is rolled back rather than leaving partially loaded
weather data.

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
POSTGRES_USER=weather_user
POSTGRES_PASSWORD=choose-a-local-password
POSTGRES_DB=weather_db
POSTGRES_HOST=postgres
POSTGRES_PORT=5432

OPEN_METEO_LATITUDE=51.5072
OPEN_METEO_LONGITUDE=-0.1276
OPEN_METEO_TIMEZONE=Europe/London

# Keep this value as data-platform when using make setup
DOCKER_NETWORK=data-platform
```

`OPEN_METEO_LATITUDE`, `OPEN_METEO_LONGITUDE`, and `OPEN_METEO_TIMEZONE`
determine the forecast location. The `.env` file is ignored by Git, so local
credentials are not committed. The Makefile creates the `data-platform`
network; if you choose another network name, create that external Docker
network before starting the stack.

## Run it

Start PostgreSQL and run the initial ingestion:

```bash
make setup
```

Run another ingestion (a delta load):

```bash
make ingest
```

Stop the services while retaining database data:

```bash
make down
```

Reset local database data and run ingestion again:

```bash
make reset
```

`make reset` runs `docker compose down -v`, which permanently deletes the local
PostgreSQL volume.

## Verify the load

Inspect the current weather row count and latest source request:

```bash
docker compose exec postgres psql -U weather_user -d weather_db -c \
  "SELECT request_id, COUNT(*) AS weather_rows
   FROM raw.weather
   GROUP BY request_id
   ORDER BY request_id;"
```

After two runs for the same forecast window, the number of rows in
`raw.weather` should remain stable, while the rows point to the newer
`request_id`. This demonstrates that duplicate observations are not inserted.

View run history:

```bash
docker compose exec postgres psql -U weather_user -d weather_db -c \
  "SELECT pipeline_name, status, rows_loaded, started_at, completed_at
   FROM metadata.pipeline_runs
   ORDER BY run_id;"
```

## Project structure

```text
.
├── docker-compose.yml       # PostgreSQL and ingestion services
├── Makefile                 # Local setup and run commands
├── postgres/init.sql        # Schemas and tables
└── ingestion/
    ├── Dockerfile           # Python 3.12 ingestion image
    ├── ingest.py            # API fetch, transform, and database load
    └── requirements.txt     # Python dependencies
```
