CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS metadata;
CREATE SCHEMA IF NOT EXISTS analytics;

CREATE TABLE raw.weather_requests (
    request_id BIGSERIAL PRIMARY KEY,
    latitude NUMERIC(8,5) NOT NULL,
    longitude NUMERIC(8,5) NOT NULL,
    timezone TEXT NOT NULL,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    raw_payload JSONB NOT NULL
);

CREATE TABLE raw.weather (
    weather_id BIGSERIAL PRIMARY KEY,

    request_id BIGINT NOT NULL
        REFERENCES raw.weather_requests(request_id),

    observation_time TIMESTAMP NOT NULL,

    latitude NUMERIC(8,5) NOT NULL,
    longitude NUMERIC(8,5) NOT NULL,

    temperature NUMERIC(5,2),
    apparent_temperature NUMERIC(5,2),
    precipitation NUMERIC(6,2),
    wind_speed NUMERIC(6,2),
    weather_code INTEGER,

    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_weather UNIQUE (
        observation_time,
        latitude,
        longitude
    )
);

CREATE TABLE metadata.pipeline_runs (
    run_id BIGSERIAL PRIMARY KEY,
    pipeline_name TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    rows_loaded INTEGER
);

