FROM apache/airflow:2.10.4

ENV PYTHONPATH="/opt/airflow"

# Install ingestion + dbt's own dependencies into the Airflow image itself,
# rather than spinning up sibling containers via DockerOperator. This keeps
# the DAG self-contained (no Docker-socket mount, no cross-repo image
# dependency) at the cost of installing dbt-core into the same Python
# environment as Airflow -- verify with `docker compose build airflow-init`
# that this doesn't hit a real dependency conflict between Airflow's and
# dbt's pinned packages.
COPY --chown=airflow:root ingestion/requirements.txt /opt/airflow/ingestion-requirements.txt
COPY --chown=airflow:root dbt/requirements.txt /opt/airflow/dbt-requirements.txt

RUN pip install --no-cache-dir \
    -r /opt/airflow/ingestion-requirements.txt \
    -r /opt/airflow/dbt-requirements.txt

COPY --chown=airflow:root ingestion /opt/airflow/ingestion
COPY --chown=airflow:root dbt /opt/airflow/dbt
