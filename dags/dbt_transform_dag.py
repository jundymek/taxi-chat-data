"""Airflow DAG: run the dbt transform (staging + marts) then test it.

Deliberately single-purpose and manually triggered (schedule=None) — it
demonstrates orchestration over the existing dbt project, not a production
cron. The dbt project is mounted read-only-ish at /opt/airflow/dbt in the
container (see docker-compose.airflow.yml).

Each task copies the mounted project into a fresh, container-writable temp dir
before running dbt. That makes the DAG portable across hosts: the bind-mounted
`dbt/` is owned by the host user, and on Linux the in-container `airflow` user
cannot write into it — yet `dbt deps` must write `dbt_packages/` (and possibly
`package-lock.yml`), and dbt writes `target/`/`logs/`. Copying to a writable
dir avoids every one of those write failures. `dbt deps` installs dbt_utils
(the project's only dependency) before run/test.
"""
from datetime import datetime

from airflow import DAG
from airflow.operators.bash import BashOperator

DBT_DIR = "/opt/airflow/dbt"

default_args = {"retries": 0, "email_on_failure": False, "email_on_retry": False}


def _dbt_command(*dbt_subcommands: str) -> str:
    """Copy the mounted project into a writable temp dir, install deps, then run
    the given dbt subcommands there, in order. Self-contained so each task works
    independently and on any host OS. `dbt_run` runs `seed` before `run` because
    the marts dims ref() the seed lookup tables — so the DAG succeeds even on a
    fresh `marts` dataset, not only when someone has seeded out-of-band."""
    steps = " && ".join(
        f"dbt {cmd} --profiles-dir \"$WORK\"" for cmd in dbt_subcommands
    )
    # `trap ... EXIT` removes the temp copy whether the task succeeds or fails,
    # so repeated runs in the long-lived container don't leak /tmp. It fires on
    # EXIT without changing the script's exit code, so Airflow still sees the
    # real dbt result.
    return (
        f"set -e && WORK=$(mktemp -d) && trap 'rm -rf \"$WORK\"' EXIT "
        f"&& cp -a {DBT_DIR}/. \"$WORK\"/ && cd \"$WORK\" && dbt deps && {steps}"
    )


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
        bash_command=_dbt_command("seed", "run"),
    )
    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command=_dbt_command("test"),
    )
    dbt_run >> dbt_test
