import json
import os
from datetime import datetime, timezone

import psycopg
import requests

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def create_session():
    retry = Retry(
        total=3,
        backoff_factor=2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )

    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))

    return session

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


def get_config():
    return {
        "latitude": float(os.environ["OPEN_METEO_LATITUDE"]),
        "longitude": float(os.environ["OPEN_METEO_LONGITUDE"]),
        "timezone": os.environ["OPEN_METEO_TIMEZONE"],
    }


def get_database_connection():
    return psycopg.connect(
        host=os.environ["POSTGRES_HOST"],
        port=os.environ["POSTGRES_PORT"],
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )


def fetch_weather(config):
    params = {
        "latitude": config["latitude"],
        "longitude": config["longitude"],
        "hourly": ",".join(
            [
                "temperature_2m",
                "apparent_temperature",
                "precipitation",
                "wind_speed_10m",
                "weather_code",
            ]
        ),
        "timezone": config["timezone"],
    }

    session = create_session()

    response = session.get(
        OPEN_METEO_URL,
        params=params,
        timeout=30,
    )

    response.raise_for_status()

    payload = response.json()

    if "hourly" not in payload:
        raise ValueError(
            "Open-Meteo response did not contain hourly data"
        )

    return payload



def transform_weather_response(payload, request_id, config):
    hourly = payload["hourly"]
    required_fields = (
        "time",
        "temperature_2m",
        "apparent_temperature",
        "precipitation",
        "wind_speed_10m",
        "weather_code",
    )
    missing_fields = [field for field in required_fields if field not in hourly]

    if missing_fields:
        raise ValueError(
            "Open-Meteo hourly data is missing fields: "
            + ", ".join(missing_fields)
        )

    row_count = len(hourly["time"])
    invalid_lengths = [
        field
        for field in required_fields
        if len(hourly[field]) != row_count
    ]

    if invalid_lengths:
        raise ValueError(
            "Open-Meteo hourly fields have inconsistent lengths: "
            + ", ".join(invalid_lengths)
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

    return records


def insert_weather_request(connection, payload, config):

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

    return request_id


def upsert_weather(connection, records):

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


def log_pipeline_run(connection, started_at, completed_at, rows_loaded):

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
        'weather_ingestion',
        'SUCCESS',
        %s,
        %s,
        %s
    )
    """

    with connection.cursor() as cursor:
        cursor.execute(
            sql,
            (started_at, completed_at, rows_loaded),
        )


def main():

    started = datetime.now(timezone.utc)

    print("Starting weather ingestion")

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

    print(
        f"Loaded {len(records)} weather records"
    )

    print(
        f"Completed at {completed}"
    )


if __name__ == "__main__":
    main()
