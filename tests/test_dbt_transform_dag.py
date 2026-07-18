"""Structure test for the dbt_transform Airflow DAG.

Validates the DAG by IMPORT only — no live Airflow scheduler, no BigQuery. The
DAG is exercised for real by the docker-compose live run (an operator step).

`apache-airflow` is a heavy, dev-only import that is deliberately NOT in the
shared mainline `.venv` (Python 3.14, and installing it would clash with the
API stack — see docs/learn/faza-6-airflow.md). We `importorskip` so the full
mainline suite stays green; the assertions run for real under the isolated
`.venv-airflow` (Airflow 2.10.4 / py3.11, matching the container).
"""
import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("airflow")

DAG_FILE = Path(__file__).resolve().parent.parent / "dags" / "dbt_transform_dag.py"


def _load_dag_module():
    spec = importlib.util.spec_from_file_location("dbt_transform_dag", DAG_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_dag_file_imports_and_defines_the_dag():
    module = _load_dag_module()
    assert hasattr(module, "dag")
    assert module.dag.dag_id == "dbt_transform"


def test_dag_has_exactly_run_then_test_tasks():
    dag = _load_dag_module().dag
    assert set(dag.task_ids) == {"dbt_run", "dbt_test"}
    run = dag.get_task("dbt_run")
    test = dag.get_task("dbt_test")
    # dbt_run must precede dbt_test.
    assert "dbt_test" in {t.task_id for t in run.downstream_list}
    assert "dbt_run" in {t.task_id for t in test.upstream_list}


def test_dag_is_manually_triggered_not_scheduled():
    dag = _load_dag_module().dag
    assert dag.schedule_interval is None
    assert dag.catchup is False
