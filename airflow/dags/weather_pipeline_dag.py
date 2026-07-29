from datetime import datetime, timezone

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator

from ingestion.ingest import get_database_connection, log_pipeline_run
from ingestion.ingest import main as run_ingestion


def log_task_status(context) -> None:
    """on_success_callback/on_failure_callback for dbt_build/dbt_test.

    Reuses ingest.py's log_pipeline_run so these tasks land in the same
    metadata.pipeline_runs audit trail as Streamlit- and CLI-triggered
    pipeline runs, recording the actual outcome -- not applied to
    ingest_weather, since that task's PythonOperator already calls
    ingest.main(), which logs its own SUCCESS/FAILED row.
    """
    exception = context.get("exception")
    status = "FAILED" if exception else "SUCCESS"
    task_instance = context["task_instance"]
    started = task_instance.start_date or datetime.now(timezone.utc)
    completed = task_instance.end_date or datetime.now(timezone.utc)

    with get_database_connection() as connection:
        log_pipeline_run(
            connection,
            status,
            started,
            completed,
            error_message=str(exception) if exception else None,
            pipeline_name=task_instance.task_id,
        )
        connection.commit()


with DAG(
    dag_id="weather_pipeline",
    start_date=datetime(2025, 1, 1),
    schedule="@hourly",
    catchup=False,
) as dag:
    ingest = PythonOperator(
        task_id="ingest_weather",
        python_callable=run_ingestion,
        retries=1,
    )

    dbt_build = BashOperator(
        task_id="dbt_build",
        bash_command="cd /opt/airflow/dbt && dbt build --profiles-dir=/opt/airflow/dbt",
        retries=1,
        on_success_callback=log_task_status,
        on_failure_callback=log_task_status,
    )

    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command="cd /opt/airflow/dbt && dbt test --profiles-dir=/opt/airflow/dbt",
        retries=1,
        on_success_callback=log_task_status,
        on_failure_callback=log_task_status,
    )

    ingest >> dbt_build >> dbt_test
