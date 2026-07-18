"""Tests for the dbt_transform Airflow DAG.

Two layers, so the DAG is guarded in BOTH environments:

1. AST-based structural checks that parse `dags/dbt_transform_dag.py` WITHOUT
   importing Airflow. These run in the shared mainline `.venv` (which
   deliberately has no `apache-airflow` — see docs/learn/faza-6-airflow.md) and
   catch syntax errors, a renamed `dag`/task symbol, a dropped dependency, or a
   changed schedule — the regressions a skipped test would miss.
2. Import-based checks that build the real DAG object. These need Airflow and so
   are skipped unless it is importable; they run for real under the isolated
   `.venv-airflow` (Airflow 2.10.4 / py3.11, matching the container) and via the
   live docker-compose run.
"""
import ast
import importlib.util
from pathlib import Path

import pytest

DAG_FILE = Path(__file__).resolve().parent.parent / "dags" / "dbt_transform_dag.py"
SOURCE = DAG_FILE.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)  # raises SyntaxError on a broken DAG file

HAS_AIRFLOW = importlib.util.find_spec("airflow") is not None
requires_airflow = pytest.mark.skipif(
    not HAS_AIRFLOW, reason="apache-airflow not installed (run under .venv-airflow)"
)


# ---- Layer 1: AST checks (no Airflow needed) --------------------------------

def _calls_named(name: str):
    """All Call nodes whose callee is `name` (bare or attribute access)."""
    out = []
    for node in ast.walk(TREE):
        if isinstance(node, ast.Call):
            func = node.func
            if (isinstance(func, ast.Name) and func.id == name) or (
                isinstance(func, ast.Attribute) and func.attr == name
            ):
                out.append(node)
    return out


def _kwarg(call: ast.Call, key: str):
    for kw in call.keywords:
        if kw.arg == key:
            return kw.value
    return None


def test_dag_file_declares_the_dbt_transform_dag():
    dag_calls = _calls_named("DAG")
    assert len(dag_calls) == 1
    dag_id = _kwarg(dag_calls[0], "dag_id")
    assert isinstance(dag_id, ast.Constant) and dag_id.value == "dbt_transform"
    # The DAG is bound to a module-level `dag` symbol via `with DAG(...) as dag`.
    assert any(
        isinstance(item.optional_vars, ast.Name) and item.optional_vars.id == "dag"
        for node in ast.walk(TREE)
        if isinstance(node, ast.With)
        for item in node.items
    )


def test_dag_declares_exactly_dbt_run_then_dbt_test():
    task_ids = {
        _kwarg(c, "task_id").value
        for c in _calls_named("BashOperator")
        if isinstance(_kwarg(c, "task_id"), ast.Constant)
    }
    assert task_ids == {"dbt_run", "dbt_test"}
    # Dependency `dbt_run >> dbt_test` is present.
    assert any(
        isinstance(node, ast.BinOp)
        and isinstance(node.op, ast.RShift)
        and isinstance(node.left, ast.Name)
        and node.left.id == "dbt_run"
        and isinstance(node.right, ast.Name)
        and node.right.id == "dbt_test"
        for node in ast.walk(TREE)
    )


def test_dag_is_manually_triggered_not_scheduled():
    dag_call = _calls_named("DAG")[0]
    schedule = _kwarg(dag_call, "schedule")
    catchup = _kwarg(dag_call, "catchup")
    assert isinstance(schedule, ast.Constant) and schedule.value is None
    assert isinstance(catchup, ast.Constant) and catchup.value is False


# ---- Layer 2: import checks (need Airflow) ----------------------------------

def _load_dag_module():
    spec = importlib.util.spec_from_file_location("dbt_transform_dag", DAG_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@requires_airflow
def test_dag_imports_and_has_the_expected_id():
    module = _load_dag_module()
    assert hasattr(module, "dag")
    assert module.dag.dag_id == "dbt_transform"


@requires_airflow
def test_dag_task_graph_is_run_then_test():
    dag = _load_dag_module().dag
    assert set(dag.task_ids) == {"dbt_run", "dbt_test"}
    run = dag.get_task("dbt_run")
    test = dag.get_task("dbt_test")
    assert "dbt_test" in {t.task_id for t in run.downstream_list}
    assert "dbt_run" in {t.task_id for t in test.upstream_list}


@requires_airflow
def test_dag_schedule_and_catchup_on_the_built_object():
    dag = _load_dag_module().dag
    assert dag.schedule_interval is None
    assert dag.catchup is False
