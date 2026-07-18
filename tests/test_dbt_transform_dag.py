"""Structure test for the dbt_transform Airflow DAG.

Validates the DAG by parsing `dags/dbt_transform_dag.py` with the `ast` module —
no Airflow import, so it runs in the shared mainline `.venv` (which deliberately
has no `apache-airflow`: that venv is Python 3.14, on which airflow 2.10 cannot
install, and a 3.14-compatible airflow would clash with the shared API stack —
see docs/learn/faza-6-airflow.md). Parsing catches the regressions that matter
here — syntax errors, a renamed `dag`/task symbol, a dropped `dbt_run >>
dbt_test` dependency, or a changed schedule.

That the file also imports and runs as a real Airflow DAG is proven end-to-end
by the docker-compose live run (an operator step) — a stronger check than a
venv-level import, so it is not duplicated here.
"""
import ast
from pathlib import Path

DAG_FILE = Path(__file__).resolve().parent.parent / "dags" / "dbt_transform_dag.py"
SOURCE = DAG_FILE.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)  # raises SyntaxError on a broken DAG file


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
