import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from requests.adapters import HTTPAdapter

import ingest


def _config():
    return {"latitude": 52.0, "longitude": 13.0, "timezone": "UTC"}


def test_transform_weather_response_happy_path():
    payload = {
        "hourly": {
            "time": ["2026-01-01T00:00", "2026-01-01T01:00"],
            "temperature_2m": [5.0, 6.0],
            "apparent_temperature": [3.0, 4.0],
            "precipitation": [0.0, 0.1],
            "wind_speed_10m": [10.0, 12.0],
            "weather_code": [1, 2],
        }
    }

    records = ingest.transform_weather_response(
        payload, request_id=42, config=_config()
    )

    assert records == [
        (42, "2026-01-01T00:00", 52.0, 13.0, 5.0, 3.0, 0.0, 10.0, 1),
        (42, "2026-01-01T01:00", 52.0, 13.0, 6.0, 4.0, 0.1, 12.0, 2),
    ]


def test_transform_weather_response_missing_field_raises():
    payload = {"hourly": {"time": ["2026-01-01T00:00"]}}

    with pytest.raises(ValueError, match="missing fields"):
        ingest.transform_weather_response(payload, request_id=1, config=_config())


def test_transform_weather_response_mismatched_lengths_raises():
    payload = {
        "hourly": {
            "time": ["2026-01-01T00:00", "2026-01-01T01:00"],
            "temperature_2m": [5.0],  # one element short of the other fields
            "apparent_temperature": [3.0, 4.0],
            "precipitation": [0.0, 0.1],
            "wind_speed_10m": [10.0, 12.0],
            "weather_code": [1, 2],
        }
    }

    with pytest.raises(ValueError, match="inconsistent lengths"):
        ingest.transform_weather_response(payload, request_id=1, config=_config())


def test_create_session_mounts_retry_adapter():
    session = ingest.create_session()
    adapter = session.get_adapter("https://api.open-meteo.com")

    assert isinstance(adapter, HTTPAdapter)
    retry = adapter.max_retries
    assert retry.total == 3
    assert retry.backoff_factor == 2
    assert set(retry.status_forcelist) == {429, 500, 502, 503, 504}


def test_insert_weather_request_executes_parameterized_insert():
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (7,)
    mock_connection = MagicMock()
    mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

    payload = {"hourly": {}}
    config = _config()

    request_id = ingest.insert_weather_request(mock_connection, payload, config)

    assert request_id == 7
    sql, params = mock_cursor.execute.call_args[0]
    assert "INSERT INTO raw.weather_requests" in sql
    assert "RETURNING request_id" in sql
    assert params == (
        config["latitude"],
        config["longitude"],
        config["timezone"],
        json.dumps(payload),
    )


def test_upsert_weather_uses_on_conflict_upsert():
    mock_cursor = MagicMock()
    mock_connection = MagicMock()
    mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

    records = [(1, "2026-01-01T00:00", 52.0, 13.0, 5.0, 3.0, 0.0, 10.0, 1)]
    ingest.upsert_weather(mock_connection, records)

    sql, params = mock_cursor.executemany.call_args[0]
    assert "ON CONFLICT" in sql
    assert "observation_time" in sql
    assert "DO UPDATE SET" in sql
    assert params == records


def test_log_pipeline_run_success_writes_all_columns():
    mock_cursor = MagicMock()
    mock_connection = MagicMock()
    mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

    started = datetime(2026, 1, 1, tzinfo=timezone.utc)
    completed = datetime(2026, 1, 1, 0, 5, tzinfo=timezone.utc)

    ingest.log_pipeline_run(
        mock_connection, "SUCCESS", started, completed, rows_loaded=168
    )

    sql, params = mock_cursor.execute.call_args[0]
    assert "error_message" in sql
    assert params == ("weather_ingestion", "SUCCESS", started, completed, 168, None)


def test_log_pipeline_run_failure_records_error_message():
    mock_cursor = MagicMock()
    mock_connection = MagicMock()
    mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

    started = datetime(2026, 1, 1, tzinfo=timezone.utc)
    completed = datetime(2026, 1, 1, 0, 1, tzinfo=timezone.utc)

    ingest.log_pipeline_run(
        mock_connection, "FAILED", started, completed, error_message="boom"
    )

    sql, params = mock_cursor.execute.call_args[0]
    assert params == ("weather_ingestion", "FAILED", started, completed, None, "boom")


def test_main_logs_failure_to_metadata_on_exception(monkeypatch):
    mock_cursor = MagicMock()
    mock_connection = MagicMock()
    mock_connection.cursor.return_value.__enter__.return_value = mock_cursor
    mock_connection.__enter__.return_value = mock_connection

    def _raise(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(ingest, "get_config", _raise)
    monkeypatch.setattr(ingest, "get_database_connection", lambda: mock_connection)

    with pytest.raises(RuntimeError, match="boom"):
        ingest.main()

    sql, params = mock_cursor.execute.call_args[0]
    assert params[0] == "weather_ingestion"
    assert params[1] == "FAILED"
    assert params[5] == "boom"
    mock_connection.commit.assert_called()
