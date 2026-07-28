import os
import subprocess
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

import psycopg
import streamlit as st
from dotenv import load_dotenv
from datetime import datetime, timezone


load_dotenv()


st.set_page_config(
    page_title="Weather Data Pipeline",
    page_icon="🌦️",
    layout="wide",
)


DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "postgres"),
    "port": os.getenv("POSTGRES_PORT", "5432"),
    "dbname": os.getenv("POSTGRES_DB"),
    "user": os.getenv("POSTGRES_USER"),
    "password": os.getenv("POSTGRES_PASSWORD"),
}

def get_connection():

    return psycopg.connect(
        host=os.environ["POSTGRES_HOST"],
        port=os.environ["POSTGRES_PORT"],
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )

@st.cache_data(ttl=60)
def get_pipeline_history():

    sql = """
    SELECT
        pipeline_name,
        status,
        started_at,
        completed_at,
        rows_loaded
    FROM metadata.pipeline_runs
    ORDER BY completed_at DESC
    LIMIT 20;
    """

    with get_connection() as conn:
        return pd.read_sql(sql, conn)


@st.cache_data(ttl=60)
def get_pipeline_metrics():

    with get_connection() as conn:

        with conn.cursor() as cur:

            cur.execute(
                """
                select count(*)
                from analytics.fact_weather_observation
                """
            )

            observations = cur.fetchone()[0]


            cur.execute(
                """
                select max(observation_time)
                from analytics.fact_weather_observation
                """
            )

            latest_observation = cur.fetchone()[0]


            cur.execute(
                """
                select max(completed_at)
                from metadata.pipeline_runs
                where pipeline_name='weather_ingestion'
                """
            )

            last_ingestion = cur.fetchone()[0]


    return (
        observations,
        latest_observation,
        last_ingestion,
    )


def run_query(query):
    with psycopg.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            return cur.fetchone()


def run_command(command, cwd=None):

    env = os.environ.copy()

    result = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env,
        timeout=300,
    )

    return (
        result.returncode,
        result.stdout,
        result.stderr,
    )



def log_test_results(test_results_list):
    """Write test results to database"""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                for test_name, status in test_results_list:
                    cur.execute(
                        """
                        INSERT INTO metadata.test_results
                        (test_name, status)
                        VALUES (%s, %s)
                        """,
                        (test_name, status),
                    )
            conn.commit()
    except Exception as e:
        pass


@st.cache_data(ttl=60)
def get_test_results():
    """Read test results from database"""
    try:
        # Check if database has data
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM analytics.fact_weather_observation")
                if cur.fetchone()[0] == 0:
                    return None

        # Get latest test results
        sql = """
        SELECT
            test_name,
            status,
            run_timestamp
        FROM metadata.test_results
        WHERE run_timestamp = (SELECT MAX(run_timestamp) FROM metadata.test_results)
        ORDER BY test_name
        """

        with get_connection() as conn:
            results = pd.read_sql(sql, conn)

        if results.empty:
            return None

        results.columns = ["Test", "Status", "Timestamp"]
        return results

    except Exception as e:
        return None


def log_pipeline_run(pipeline_name, status):

    with get_connection() as conn:

        with conn.cursor() as cur:

            cur.execute(
                """
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
                    %s,
                    NOW(),
                    NOW(),
                    NULL
                )
                """,
                (
                    pipeline_name,
                    status,
                ),
            )

        conn.commit()


@st.cache_data(ttl=60)
def get_weather_history():

    sql = """
    SELECT
        observation_time,
        temperature_c,
        apparent_temperature_c,
        precipitation_mm,
        wind_speed_kmh
    FROM analytics.fact_weather_observation
    ORDER BY observation_time;
    """

    with get_connection() as conn:
        return pd.read_sql(sql, conn)


@st.cache_data(ttl=60)
def get_latest_pipeline_runs():

    sql = """
    SELECT DISTINCT ON (pipeline_name)

        pipeline_name,
        status,
        completed_at

    FROM metadata.pipeline_runs

    ORDER BY
        pipeline_name,
        completed_at DESC;
    """

    with get_connection() as conn:

        with conn.cursor() as cur:

            cur.execute(sql)

            return cur.fetchall()

st.title("🌦️ Weather Data Pipeline")

st.divider()

# Top section with status on left and controls on right
left_col, right_col = st.columns([2, 1])

with left_col:
    st.subheader("Pipeline Status")

    runs = get_latest_pipeline_runs()

    for pipeline_name, status, completed_at in runs:
        icon = "🟢" if status == "SUCCESS" else "🔴"
        st.write(
            f"{icon} **{pipeline_name}** — {status} ({completed_at})"
        )

    # Database status
    st.subheader("Database Status")

    try:
        result = run_query("SELECT 1;")

        if result:
            st.success("PostgreSQL connection successful")

    except Exception as exc:
        st.error(f"Database unavailable: {exc}")

with right_col:
    st.subheader("Pipeline Controls")

    if st.button("Run ingestion"):
        with st.spinner("Running ingestion..."):
            code, stdout, stderr = run_command(
                [
                    "python",
                    "/app/ingestion/ingest.py"
                ]
            )

            if code == 0:
                st.success("Ingestion completed")
                st.cache_data.clear()
                st.rerun()
            else:
                st.error(stderr)

    if st.button("Run dbt build"):
        with st.spinner("Running dbt build..."):
            code, stdout, stderr = run_command(
                [
                    "dbt",
                    "build",
                ],
                cwd="/app/dbt",
            )

            if code == 0:
                log_pipeline_run("dbt_build", "SUCCESS")
                st.success("dbt build completed")
                st.cache_data.clear()
                st.rerun()
            else:
                log_pipeline_run("dbt_build", "FAILED")
                st.error(stderr)

    if st.button("Run dbt tests"):
        with st.spinner("Running dbt tests..."):
            code, stdout, stderr = run_command(
                [
                    "dbt",
                    "test",
                ],
                cwd="/app/dbt",
            )

            if code == 0:
                log_pipeline_run("dbt_test", "SUCCESS")

                # Parse dbt output to extract test results
                import re
                test_results = []
                for line in (stdout + stderr).split('\n'):
                    # Match lines like: "1 of 20 PASS test_name"
                    match = re.search(r'\s(PASS|FAIL)\s+(\S+)\s', line)
                    if match:
                        status, test_name = match.groups()
                        test_results.append((test_name, status.lower()))

                if test_results:
                    log_test_results(test_results)

                st.success("dbt tests passed")
                st.cache_data.clear()
                st.rerun()
            else:
                log_pipeline_run("dbt_test", "FAILED")
                st.error(stderr)

    st.divider()
    st.subheader("Tools")
    st.markdown(
        """
        - [CloudBeaver](http://localhost:8978)
        - [dbt Docs](http://localhost:8082)
        """
    )


st.divider()

# Metrics
st.subheader("Metrics")

try:
    weather = get_weather_history()
    weather["is_forecast"] = (
        weather["observation_time"]
        > pd.Timestamp.now()
    )
except Exception as e:
    st.warning("⚠️ Data not available yet. Run `make setup` or `make reset` to initialize the pipeline.")
    weather = None

if weather is not None:
    observed = weather[~weather["is_forecast"]]
    forecast = weather[weather["is_forecast"]]

    try:
        observations, latest, ingestion = get_pipeline_metrics()

        col1, col2, col3 = st.columns(3)

        col1.metric(
            "Weather observations",
            observations
        )

        col2.metric(
            "Latest observation",
            str(latest)
        )

        col3.metric(
            "Last ingestion",
            str(ingestion)
        )
    except Exception as e:
        st.warning("Could not fetch pipeline metrics")

    st.divider()
    st.subheader("Recent Weather")

    st.dataframe(
        weather.sort_values(
            "observation_time",
            ascending=False,
        ).head(10),
        use_container_width=True,
        hide_index=True,
    )
else:
    col1, col2, col3 = st.columns(3)
    col1.metric("Weather observations", "—")
    col2.metric("Latest observation", "—")
    col3.metric("Last ingestion", "—")


st.divider()

if weather is not None:
    st.subheader("Weather Analytics")
    latest = weather.iloc[-1]

    location = pd.DataFrame({
        "latitude": [float(os.environ["OPEN_METEO_LATITUDE"])],
        "longitude": [float(os.environ["OPEN_METEO_LONGITUDE"])],
        "temperature": [latest["temperature_c"]],
    })

    temp_fig = go.Figure()

    temp_fig.add_trace(
        go.Scatter(
            x=observed["observation_time"],
            y=observed["temperature_c"],
            name="Observed",
            mode="lines",
        )
    )

    temp_fig.add_trace(
        go.Scatter(
            x=forecast["observation_time"],
            y=forecast["temperature_c"],
            name="Forecast",
            mode="lines",
            line=dict(
                dash="dot"
            ),
        )
    )

    wind_fig = go.Figure()

    wind_fig.add_trace(
        go.Scatter(
            x=observed["observation_time"],
            y=observed["wind_speed_kmh"],
            name="Observed",
            mode="lines",
        )
    )

    wind_fig.add_trace(
        go.Scatter(
            x=forecast["observation_time"],
            y=forecast["wind_speed_kmh"],
            name="Forecast",
            mode="lines",
            line=dict(
                dash="dot"
            ),
        )
    )

    map_fig = px.scatter_map(
        location,
        lat="latitude",
        lon="longitude",
        hover_data=["temperature"],
    )

    map_fig.update_layout(
        height=350,
        map_zoom=11,
        map_style="carto-darkmatter",
    )
    map_fig.update_traces(
        marker=dict(
            size=18,
            color="red"
        )
    )

    temp_fig.update_layout(
        height=350,
        xaxis_title="Observation Time",
        yaxis_title="°C",
    )

    wind_fig.update_layout(
        height=350,
        xaxis_title="Observation Time",
        yaxis_title="km/h",
    )

    rain_fig = px.bar(
        weather,
        x="observation_time",
        y="precipitation_mm",
        title="Precipitation",
    )

    rain_fig.update_layout(
        height=350,
        xaxis_title="Observation Time",
        yaxis_title="mm",
    )
    left, right = st.columns([2, 1])

    with left:
        st.plotly_chart(
            temp_fig,
            use_container_width=True,
            config={
                "displaylogo": False,
            },
        )

    with right:
        st.subheader("Location")

        st.plotly_chart(
            map_fig,
            use_container_width=True,
            config={
                "displaylogo": False,
            },
        )

    left, right = st.columns(2)

    with left:
        st.plotly_chart(
            wind_fig,
            use_container_width=True,
            config={
                "displaylogo": False,
            },
        )

    with right:
        st.plotly_chart(
            rain_fig,
            use_container_width=True,
            config={
                "displaylogo": False,
            },
        )



st.divider()

# Test Results
st.subheader("Test Results")

test_results = get_test_results()

if test_results is not None and not test_results.empty:
    passed = sum(1 for r in test_results["Status"] if r == "pass")
    failed = sum(1 for r in test_results["Status"] if r == "fail")

    col1, col2 = st.columns(2)
    col1.metric("Passed", passed)
    col2.metric("Failed", failed)

    st.dataframe(
        test_results[["Test", "Status"]],
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("No test results available. Run 'dbt test' to generate results.")

st.divider()

# Pipeline History
st.subheader("Pipeline History")

history = get_pipeline_history()

st.dataframe(
    history,
    use_container_width=True,
    hide_index=True,
)

st.divider()


