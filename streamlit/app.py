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
    initial_sidebar_state="collapsed",
)

# Custom CSS for dark mode design
st.markdown("""
    <style>
        :root {
            --bg-primary: #0f0f0f;
            --bg-secondary: #1a1a1a;
            --bg-tertiary: #242424;
            --text-primary: #f5f5f5;
            --text-secondary: #a0a8b8;
            --text-muted: #6a7280;
            --border: #2a3038;
            --accent: #4da6ff;
            --success: #34d399;
            --warning: #fbbf24;
            --error: #f87171;
        }

        body {
            background-color: var(--bg-primary) !important;
        }

        .main {
            background-color: var(--bg-primary) !important;
        }

        [data-testid="stAppViewContainer"] {
            background-color: var(--bg-primary);
        }

        [data-testid="stHeader"] {
            background-color: var(--bg-secondary);
            border-bottom: 1px solid var(--border);
        }

        .stMarkdown {
            color: var(--text-primary);
        }

        .custom-header {
            background-color: var(--bg-secondary);
            border-bottom: 1px solid var(--border);
            padding: 16px 20px;
            margin: -20px -20px 20px -20px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 40px;
            flex-wrap: wrap;
        }

        .logo {
            font-size: 20px;
            font-weight: 600;
            color: var(--text-primary);
        }

        .status-indicators {
            display: flex;
            gap: 24px;
            flex: 1;
        }

        .status-item {
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 13px;
        }

        .status-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background-color: var(--success);
        }

        .status-label {
            color: var(--text-secondary);
        }

        .status-value {
            color: var(--text-muted);
            font-size: 12px;
        }

        .section-title {
            font-size: 12px;
            font-weight: 600;
            margin: 20px 0 16px 0;
            color: var(--text-primary);
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .info-box {
            background-color: rgba(77, 166, 255, 0.1);
            border: 1px solid var(--accent);
            border-radius: 6px;
            padding: 12px;
            color: var(--text-primary);
        }

        [data-testid="stMetricValue"] {
            color: var(--text-primary);
        }

        [data-testid="stMetricLabel"] {
            color: var(--text-muted);
        }

        table {
            color: var(--text-primary) !important;
        }

        thead {
            background-color: var(--bg-tertiary) !important;
            color: var(--text-secondary) !important;
        }

        tbody tr {
            background-color: var(--bg-secondary) !important;
            border-color: var(--border) !important;
        }

        .stButton > button {
            width: 100%;
            background-color: var(--accent) !important;
            color: white !important;
            border: none !important;
            border-radius: 6px !important;
            padding: 10px 14px !important;
            font-weight: 500 !important;
            font-size: 13px !important;
        }

        .stButton > button:hover {
            background-color: #3d96ff !important;
        }

        .stInfo, [data-testid="stAlert"] {
            background-color: rgba(77, 166, 255, 0.1) !important;
            border: 1px solid var(--accent) !important;
            color: var(--text-primary) !important;
        }

        [data-testid="stPlotlyChart"] {
            background-color: transparent;
        }
    </style>
""", unsafe_allow_html=True)

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
            cur.execute("select count(*) from analytics.fact_weather_observation")
            observations = cur.fetchone()[0]
            cur.execute("select max(observation_time) from analytics.fact_weather_observation")
            latest_observation = cur.fetchone()[0]
            cur.execute("select max(completed_at) from metadata.pipeline_runs where pipeline_name='weather_ingestion'")
            last_ingestion = cur.fetchone()[0]
    return (observations, latest_observation, last_ingestion)

def run_query(query: str) -> tuple | None:
    with psycopg.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            return cur.fetchone()

def run_command(command: list[str], cwd: str | None = None) -> tuple[int, str, str]:
    env = os.environ.copy()
    result = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env,
        timeout=300,
    )
    return (result.returncode, result.stdout, result.stderr)

def show_command_output(stdout: str, stderr: str) -> None:
    """Surface a command's full stdout/stderr, so successful runs are
    inspectable too rather than only showing stderr on failure."""
    if stdout or stderr:
        with st.expander("Output"):
            if stdout:
                st.code(stdout, language="text")
            if stderr:
                st.code(stderr, language="text")

def log_pipeline_run(pipeline_name, status):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO metadata.pipeline_runs
                (pipeline_name, status, started_at, completed_at, rows_loaded)
                VALUES (%s, %s, NOW(), NOW(), NULL)
                """,
                (pipeline_name, status),
            )
        conn.commit()

def log_test_results(test_results_list: list[tuple[str, str]]) -> None:
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
        st.warning(f"Failed to log test results: {e}")

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

@st.cache_data(ttl=60)
def get_test_status() -> tuple[str, str]:
    """Get test status: (label, css_class for dot color)"""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM metadata.test_results")
                count = cur.fetchone()[0]

                if count == 0:
                    return ("No tests run", "error")

                cur.execute(
                    "SELECT COUNT(*) FROM metadata.test_results "
                    "WHERE status = 'pass' AND run_timestamp = "
                    "(SELECT MAX(run_timestamp) FROM metadata.test_results)"
                )
                passed = cur.fetchone()[0]

                cur.execute(
                    "SELECT COUNT(*) FROM metadata.test_results "
                    "WHERE status = 'fail' AND run_timestamp = "
                    "(SELECT MAX(run_timestamp) FROM metadata.test_results)"
                )
                failed = cur.fetchone()[0]

                if failed > 0:
                    return (f"{passed} passed, {failed} failed", "error")
                else:
                    return (f"{passed} passed", "success")
    except Exception:
        return ("No tests run", "error")

@st.cache_data(ttl=60)
def get_last_run_status() -> tuple[str, str]:
    """Get last pipeline run status: (label, dot_color)"""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM metadata.pipeline_runs")
                count = cur.fetchone()[0]

                if count == 0:
                    return ("Not run yet", "#f87171")

                cur.execute(
                    "SELECT completed_at FROM metadata.pipeline_runs "
                    "ORDER BY completed_at DESC LIMIT 1"
                )
                result = cur.fetchone()
                if result and result[0]:
                    last_time = result[0]
                    now = datetime.now(timezone.utc)
                    diff = now - last_time

                    if diff.total_seconds() < 60:
                        label = "Just now"
                    elif diff.total_seconds() < 3600:
                        minutes = int(diff.total_seconds() / 60)
                        label = f"{minutes}m ago"
                    elif diff.total_seconds() < 86400:
                        hours = int(diff.total_seconds() / 3600)
                        label = f"{hours}h ago"
                    else:
                        label = "Recent"

                    return (label, "#34d399")
                else:
                    return ("Not run yet", "#f87171")
    except Exception:
        return ("Not run yet", "#f87171")

# Title
st.markdown("# 🌦️ Weather Pipeline")

# Get dynamic status
test_status, test_status_class = get_test_status()
test_dot_color = "#34d399" if test_status_class == "success" else "#f87171"
last_run_label, last_run_color = get_last_run_status()

# Header with status and tools
st.markdown(f"""
    <div class="custom-header" style="margin-top: 0 !important; margin-bottom: 20px !important;">
        <div class="status-indicators" style="flex: 1;">
            <div class="status-item">
                <div class="status-dot"></div>
                <div>
                    <div class="status-label">Database</div>
                    <div class="status-value">Connected</div>
                </div>
            </div>
            <div class="status-item">
                <div class="status-dot" style="background-color: {last_run_color};"></div>
                <div>
                    <div class="status-label">Last Run</div>
                    <div class="status-value">{last_run_label}</div>
                </div>
            </div>
            <div class="status-item">
                <div class="status-dot" style="background-color: {test_dot_color};"></div>
                <div>
                    <div class="status-label">Tests</div>
                    <div class="status-value">{test_status}</div>
                </div>
            </div>
        </div>
        <div style="display: flex; gap: 20px; font-size: 13px; color: #4da6ff;">
            <a href="http://localhost:8978" target="_blank" style="color: #4da6ff; text-decoration: none;">→ CloudBeaver</a>
            <a href="http://localhost:8082" target="_blank" style="color: #4da6ff; text-decoration: none;">→ dbt Docs</a>
        </div>
    </div>
""", unsafe_allow_html=True)

# Main layout
left_col, right_col = st.columns([3, 1], gap="large")

with left_col:

    # Weather Analytics
    try:
        weather = get_weather_history()
        weather["is_forecast"] = weather["observation_time"] > pd.Timestamp.now()

        st.markdown('<p class="section-title">Weather Analytics</p>', unsafe_allow_html=True)

        observed = weather[~weather["is_forecast"]]
        forecast = weather[weather["is_forecast"]]

        # Temperature
        temp_fig = go.Figure()
        temp_fig.add_trace(go.Scatter(x=observed["observation_time"], y=observed["temperature_c"], name="Observed", mode="lines", line=dict(color="#34d399")))
        temp_fig.add_trace(go.Scatter(x=forecast["observation_time"], y=forecast["temperature_c"], name="Forecast", mode="lines", line=dict(dash="dot", color="#4da6ff")))
        temp_fig.update_layout(height=350, hovermode="x unified", template="plotly_dark", margin=dict(l=0, r=0, t=0, b=0), showlegend=True)
        st.plotly_chart(temp_fig, use_container_width=True)

        # Wind & Precipitation
        col1, col2 = st.columns(2)
        with col1:
            wind_fig = go.Figure()
            wind_fig.add_trace(go.Scatter(x=observed["observation_time"], y=observed["wind_speed_kmh"], name="Wind", mode="lines", line=dict(color="#4da6ff")))
            wind_fig.update_layout(height=300, title="Wind Speed (km/h)", template="plotly_dark", margin=dict(l=0, r=0, t=30, b=0), showlegend=False)
            st.plotly_chart(wind_fig, use_container_width=True)

        with col2:
            rain_fig = go.Figure()
            rain_fig.add_trace(go.Bar(x=weather["observation_time"], y=weather["precipitation_mm"], name="Rain", marker=dict(color="#4da6ff")))
            rain_fig.update_layout(height=300, title="Precipitation (mm)", template="plotly_dark", margin=dict(l=0, r=0, t=30, b=0), showlegend=False)
            st.plotly_chart(rain_fig, use_container_width=True)
    except Exception as e:
        st.error(f"Failed to load weather analytics: {e}")

    # Test Results - Organized by source
    st.markdown('<p class="section-title">Test Results</p>', unsafe_allow_html=True)
    try:
        with get_connection() as conn:
            all_tests = pd.read_sql(
                "SELECT test_name, status FROM metadata.test_results WHERE run_timestamp = (SELECT MAX(run_timestamp) FROM metadata.test_results) ORDER BY test_name",
                conn
            )

        if not all_tests.empty:
            # Categorize tests
            source_tests = all_tests[all_tests['test_name'].str.contains('source_', case=False)]
            staging_tests = all_tests[all_tests['test_name'].str.contains('stg_', case=False)]
            custom_tests = all_tests[~all_tests['test_name'].str.contains('source_|stg_', case=False, regex=True)]

            # Show source tests
            if not source_tests.empty:
                passed_count = (source_tests['status'] == 'pass').sum()
                with st.expander(f"📊 Source Tests ({passed_count}/{len(source_tests)})", expanded=False):
                    st.dataframe(source_tests[['test_name', 'status']], use_container_width=True, hide_index=True)

            # Show staging tests
            if not staging_tests.empty:
                passed_count = (staging_tests['status'] == 'pass').sum()
                with st.expander(f"📦 Staging Tests ({passed_count}/{len(staging_tests)})", expanded=False):
                    st.dataframe(staging_tests[['test_name', 'status']], use_container_width=True, hide_index=True)

            # Show custom tests
            if not custom_tests.empty:
                passed_count = (custom_tests['status'] == 'pass').sum()
                with st.expander(f"✓ Custom Tests ({passed_count}/{len(custom_tests)})", expanded=False):
                    st.dataframe(custom_tests[['test_name', 'status']], use_container_width=True, hide_index=True)
        else:
            st.info("No test results yet. Run dbt tests to generate results.")
    except Exception as e:
        st.info("No test results available.")


with right_col:
    # Quick Actions
    st.markdown('<p class="section-title">Actions</p>', unsafe_allow_html=True)

    # Get last run status for each action
    @st.cache_data(ttl=60)
    def get_action_status():
        try:
            with get_connection() as conn:
                result = pd.read_sql(
                    """
                    SELECT DISTINCT ON (pipeline_name)
                        pipeline_name, status, completed_at
                    FROM metadata.pipeline_runs
                    WHERE pipeline_name IN ('weather_ingestion', 'dbt_build', 'dbt_test')
                    ORDER BY pipeline_name, completed_at DESC
                    """,
                    conn
                )
            return {row['pipeline_name']: (row['status'], row['completed_at']) for _, row in result.iterrows()}
        except psycopg.Error:
            return {}

    action_status = get_action_status()

    # Ingest
    ingest_status = action_status.get('weather_ingestion', (None, None))
    ingest_text = f"▶ Ingest\n{ingest_status[1].strftime('%H:%M') if ingest_status[1] else '—'}" if ingest_status[1] else "▶ Ingest"
    if st.button(ingest_text, use_container_width=True, key="btn_ingest"):
        with st.spinner("Running ingestion..."):
            code, stdout, stderr = run_command(["python", "/app/ingestion/ingest.py"])
            if code == 0:
                st.session_state["ingest_output"] = (stdout, stderr)
                st.success("✓ Ingestion completed")
                st.cache_data.clear()
                st.rerun()
            else:
                st.error(stderr)
                show_command_output(stdout, stderr)

    if "ingest_output" in st.session_state:
        show_command_output(*st.session_state["ingest_output"])

    if ingest_status[1]:
        status_color = "🟢" if ingest_status[0] == "SUCCESS" else "🔴"
        st.caption(f"{status_color} {ingest_status[1].strftime('%Y-%m-%d %H:%M')}")

    # Build
    build_status = action_status.get('dbt_build', (None, None))
    build_text = f"▶ Build\n{build_status[1].strftime('%H:%M') if build_status[1] else '—'}" if build_status[1] else "▶ Build"
    if st.button(build_text, use_container_width=True, key="btn_build"):
        with st.spinner("Running dbt build..."):
            code, stdout, stderr = run_command(
                ["dbt", "build", "--project-dir=/app/dbt", "--profiles-dir=/app/dbt"]
            )
            if code == 0:
                log_pipeline_run("dbt_build", "SUCCESS")

                # Parse and log test results from dbt build
                import json
                from pathlib import Path
                try:
                    results_file = Path("/app/dbt/target/run_results.json")
                    if results_file.exists():
                        with open(results_file) as f:
                            data = json.load(f)

                        test_results = []
                        for result in data.get("results", []):
                            unique_id = result.get("unique_id", "")
                            if unique_id.startswith("test."):
                                test_name = unique_id.split(".")[2] if len(unique_id.split(".")) > 2 else unique_id
                                test_results.append((test_name, result.get("status", "unknown")))

                        if test_results:
                            log_test_results(test_results)
                except (OSError, ValueError) as e:
                    st.warning(f"Could not parse test results: {e}")

                st.session_state["build_output"] = (stdout, stderr)
                st.success("✓ Build completed")
                st.cache_data.clear()
                st.rerun()
            else:
                log_pipeline_run("dbt_build", "FAILED")
                st.error(stderr)
                show_command_output(stdout, stderr)

    if "build_output" in st.session_state:
        show_command_output(*st.session_state["build_output"])

    if build_status[1]:
        status_color = "🟢" if build_status[0] == "SUCCESS" else "🔴"
        st.caption(f"{status_color} {build_status[1].strftime('%Y-%m-%d %H:%M')}")

    # Test
    test_status = action_status.get('dbt_test', (None, None))
    test_text = f"▶ Test\n{test_status[1].strftime('%H:%M') if test_status[1] else '—'}" if test_status[1] else "▶ Test"
    if st.button(test_text, use_container_width=True, key="btn_test"):
        with st.spinner("Running dbt tests..."):
            code, stdout, stderr = run_command(
                ["dbt", "test", "--project-dir=/app/dbt", "--profiles-dir=/app/dbt"]
            )
            if code == 0:
                log_pipeline_run("dbt_test", "SUCCESS")

                # Parse and log test results
                import json
                from pathlib import Path
                try:
                    results_file = Path("/app/dbt/target/run_results.json")
                    if results_file.exists():
                        with open(results_file) as f:
                            data = json.load(f)

                        test_results = []
                        for result in data.get("results", []):
                            unique_id = result.get("unique_id", "")
                            if unique_id.startswith("test."):
                                test_name = unique_id.split(".")[2] if len(unique_id.split(".")) > 2 else unique_id
                                test_results.append((test_name, result.get("status", "unknown")))

                        if test_results:
                            log_test_results(test_results)
                except (OSError, ValueError) as e:
                    st.warning(f"Could not parse test results: {e}")

                st.session_state["test_output"] = (stdout, stderr)
                st.success("✓ Tests passed")
                st.cache_data.clear()
                st.rerun()
            else:
                log_pipeline_run("dbt_test", "FAILED")
                st.error(stderr)
                show_command_output(stdout, stderr)

    if "test_output" in st.session_state:
        show_command_output(*st.session_state["test_output"])

    if test_status[1]:
        status_color = "🟢" if test_status[0] == "SUCCESS" else "🔴"
        st.caption(f"{status_color} {test_status[1].strftime('%Y-%m-%d %H:%M')}")

    st.divider()

    # Stats
    try:
        observations, latest, ingestion = get_pipeline_metrics()
        st.markdown('<p class="section-title">Stats</p>', unsafe_allow_html=True)
        st.metric("Observations", observations)
        st.metric("Latest", str(latest).split()[0] if latest else "—")
        st.metric("Last Ingest", str(ingestion).split()[1][:5] if ingestion else "—")
    except psycopg.Error:
        st.info("⚠️ Data not available yet.")

    st.divider()

    # Pipeline History (moved from main content)
    st.markdown('<p class="section-title">History</p>', unsafe_allow_html=True)
    try:
        history = get_pipeline_history()
        history_display = history[['pipeline_name', 'status', 'completed_at']].head(5)
        st.dataframe(history_display, use_container_width=True, hide_index=True)
    except Exception as e:
        st.info("No pipeline history yet.")
