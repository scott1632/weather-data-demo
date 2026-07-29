import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import psycopg
import requests

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
HOURLY_FIELDS = (
    "temperature_2m",
    "apparent_temperature",
    "precipitation",
    "wind_speed_10m",
    "weather_code",
)
REQUIRED_FIELDS = ("time",) + HOURLY_FIELDS
PIPELINE_NAME = "weather_ingestion"


def create_session() -> requests.Session:
    retry = Retry(
        total=3,
        backoff_factor=2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )

    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))

    return session


def get_config() -> dict[str, Any]:
    return {
        "latitude": float(os.environ["OPEN_METEO_LATITUDE"]),
        "longitude": float(os.environ["OPEN_METEO_LONGITUDE"]),
        "timezone": os.environ["OPEN_METEO_TIMEZONE"],
    }


def get_database_connection() -> psycopg.Connection:
    return psycopg.connect(
        host=os.environ["POSTGRES_HOST"],
        port=os.environ["POSTGRES_PORT"],
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )


def fetch_weather(config: dict[str, Any]) -> dict[str, Any]:
    params = {
        "latitude": config["latitude"],
        "longitude": config["longitude"],
        "hourly": ",".join(HOURLY_FIELDS),
        "timezone": config["timezone"],
    }

    session = create_session()

    logger.info(
        "Fetching forecast from Open-Meteo for "
        f"lat={config['latitude']}, lon={config['longitude']}"
    )

    response = session.get(
        OPEN_METEO_URL,
        params=params,
        timeout=30,
    )

    response.raise_for_status()

    payload = response.json()

    if "hourly" not in payload:
        raise ValueError("Open-Meteo response did not contain hourly data")

    logger.info("Successfully fetched forecast data")
    return payload


def transform_weather_response(
    payload: dict[str, Any],
    request_id: int,
    config: dict[str, Any],
) -> list[tuple]:
    hourly = payload["hourly"]
    missing_fields = [field for field in REQUIRED_FIELDS if field not in hourly]

    if missing_fields:
        raise ValueError(
            f"Open-Meteo hourly data is missing fields: {', '.join(missing_fields)}"
        )

    row_count = len(hourly["time"])
    invalid_lengths = [
        field for field in REQUIRED_FIELDS if len(hourly[field]) != row_count
    ]

    if invalid_lengths:
        raise ValueError(
            f"Open-Meteo hourly fields have inconsistent lengths: {', '.join(invalid_lengths)}"
        )

    records = []

    for index, observation_time in enumerate(hourly["time"]):

        records.append(
            (
                request_id,
                observation_time,
                config["latitude"],
                config["longitude"],
                hourly["temperature_2m"][index],
                hourly["apparent_temperature"][index],
                hourly["precipitation"][index],
                hourly["wind_speed_10m"][index],
                hourly["weather_code"][index],
            )
        )

    logger.info(f"Transformed {len(records)} weather observations")
    return records


def insert_weather_request(
    connection: psycopg.Connection,
    payload: dict[str, Any],
    config: dict[str, Any],
) -> int:
    sql = """
        INSERT INTO raw.weather_requests (
            latitude,
            longitude,
            timezone,
            raw_payload
        )
        VALUES (
            %s,
            %s,
            %s,
            %s
        )
        RETURNING request_id
    """

    with connection.cursor() as cursor:

        cursor.execute(
            sql,
            (
                config["latitude"],
                config["longitude"],
                config["timezone"],
                json.dumps(payload),
            ),
        )

        request_id = cursor.fetchone()[0]

    logger.info(f"Inserted API request with request_id={request_id}")
    return request_id


def upsert_weather(
    connection: psycopg.Connection,
    records: list[tuple],
) -> None:
    sql = """
    INSERT INTO raw.weather
    (
        request_id,
        observation_time,
        latitude,
        longitude,
        temperature,
        apparent_temperature,
        precipitation,
        wind_speed,
        weather_code
    )
    VALUES
    (
        %s,%s,%s,%s,%s,%s,%s,%s,%s
    )

    ON CONFLICT
    (
        observation_time,
        latitude,
        longitude
    )
    DO UPDATE SET

        request_id = EXCLUDED.request_id,
        temperature = EXCLUDED.temperature,
        apparent_temperature = EXCLUDED.apparent_temperature,
        precipitation = EXCLUDED.precipitation,
        wind_speed = EXCLUDED.wind_speed,
        weather_code = EXCLUDED.weather_code,
        ingested_at = NOW();

    """

    with connection.cursor() as cursor:

        cursor.executemany(
            sql,
            records,
        )

    logger.info(f"Upserted {len(records)} weather observations")


def log_pipeline_run(
    connection: psycopg.Connection,
    started_at: datetime,
    completed_at: datetime,
    rows_loaded: int,
) -> None:
    sql = """
    INSERT INTO metadata.pipeline_runs
    (
        pipeline_name,
        status,
        started_at,
        completed_at,
        rows_loaded
    )

    VALUES
    (
        %s,
        'SUCCESS',
        %s,
        %s,
        %s
    )
    """

    with connection.cursor() as cursor:
        cursor.execute(
            sql,
            (PIPELINE_NAME, started_at, completed_at, rows_loaded),
        )

    logger.info(f"Logged pipeline run: {rows_loaded} rows loaded")


def main() -> None:
    started = datetime.now(timezone.utc)

    logger.info("Starting weather ingestion")

    try:
        config = get_config()

        payload = fetch_weather(config)

        with get_database_connection() as connection:
            request_id = insert_weather_request(
                connection,
                payload,
                config,
            )

            records = transform_weather_response(
                payload,
                request_id,
                config,
            )

            upsert_weather(connection, records)

            completed = datetime.now(timezone.utc)

            log_pipeline_run(connection, started, completed, len(records))

            connection.commit()
            logger.info("Transaction committed successfully")

        logger.info(f"Loaded {len(records)} weather records")
        logger.info(f"Completed at {completed}")

    except Exception as e:
        logger.error(f"Ingestion failed: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
