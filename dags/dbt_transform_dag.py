"""Airflow DAG: run the dbt transform (staging + marts) then test it.

Deliberately single-purpose and manually triggered (schedule=None) — it
demonstrates orchestration over the existing dbt project, not a production
cron. The dbt project is mounted at /opt/airflow/dbt in the container (see
docker-compose.airflow.yml); `profiles.yml` lives inside that project, so we
point --profiles-dir at it.
"""
from datetime import datetime

from airflow import DAG
from airflow.operators.bash import BashOperator

DBT_DIR = "/opt/airflow/dbt"

default_args = {"retries": 0, "email_on_failure": False, "email_on_retry": False}

with DAG(
    dag_id="dbt_transform",
    description="Run then test the dbt transform (staging + marts).",
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    default_args=default_args,
    tags=["dbt", "faza-6"],
) as dag:
    dbt_run = BashOperator(
        task_id="dbt_run",
        # `dbt deps` first: the project depends on dbt_utils (packages.yml) but
        # dbt_packages/ is gitignored and empty in a fresh container. Folded into
        # this task to keep the DAG at exactly two steps (run, then test).
        bash_command=(
            f"cd {DBT_DIR} && dbt deps && dbt run --profiles-dir {DBT_DIR}"
        ),
    )
    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command=f"cd {DBT_DIR} && dbt test --profiles-dir {DBT_DIR}",
    )
    dbt_run >> dbt_test
