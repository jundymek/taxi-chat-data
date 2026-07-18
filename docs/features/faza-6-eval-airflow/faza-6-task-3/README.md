# Faza 6 / Task 3: Airflow DAG orchestrating the dbt transform (local Docker)

## What was built
A local, manually-triggered Airflow DAG that orchestrates the existing dbt
project. `dags/dbt_transform_dag.py` defines `dag_id="dbt_transform"` with two
`BashOperator` tasks — `dbt_run` then `dbt_test` (`dbt_run >> dbt_test`),
`schedule=None`, `catchup=False`. `docker-compose.airflow.yml` runs Airflow
2.10.4 (LocalExecutor) + a Postgres metadata DB, mounts `dags/` and `dbt/`,
binds ADC read-only, and installs `dbt-bigquery` in-container. The DAG is
validated by an import-only structure test — no live scheduler needed.

## Files touched
- `dags/dbt_transform_dag.py` (NEW) — the DAG (Airflow 2.x API, matches the container).
- `docker-compose.airflow.yml` (NEW) — Airflow LocalExecutor + Postgres + ADC bind; `dbt-bigquery>=1.8,<2.0`.
- `tests/test_dbt_transform_dag.py` (NEW) — two layers: AST checks (run without airflow) + import checks (`skipif(not HAS_AIRFLOW)`).
- `.gitignore` (UPDATE) — ignore the isolated `.venv-airflow/`.
- `docs/learn/faza-6-airflow.md` (NEW) — Polish learning note.
- `docs/tasks/faza-6-task-3.md` (UPDATE) — story close-out.

## Key decisions
- **`apache-airflow` is NOT installed into the shared mainline `.venv`.** That
  venv is Python 3.14 (airflow 2.10 requires <3.13), and an airflow that does
  support 3.14 would downgrade the shared `fastapi` and pull ~70 heavy deps —
  breaking cohort peer bob's API work. Instead the import test runs against an
  isolated `.venv-airflow` (python3.11, `apache-airflow==2.10.4`, matching the
  container image exactly), and the test uses `pytest.importorskip("airflow")`
  so the full mainline suite stays green (the DAG test skips there). Details in
  `DECISIONS.md` D1/D2 and the learn note. Airflow stays out of
  `requirements.txt` (dev-only import).
- **`BashOperator` + dbt (not a dbt-airflow plugin).** Single-purpose, manually
  triggered — demonstrates orchestration over the existing dbt project without
  extra abstraction (YAGNI, per spec). No Cloud Composer.
- **ADC via a read-only bind of `application_default_credentials.json`** — the
  proven Faza 2 pattern; the container authenticates as the operator, no
  service-account key files created.
- **Each task copies the mounted dbt project into a writable temp dir**
  (`mktemp -d`) before running `dbt deps && dbt <run|test>`. The bind-mounted
  `dbt/` is host-owned and not writable by the in-container `airflow` user on
  Linux; `dbt deps` must write `dbt_packages/`. Copying makes the DAG portable
  across macOS and Linux hosts (Codex P1).

## Verification
- Structure tests: mainline `.venv` → **3 passed, 3 skipped** (AST layer runs;
  airflow-import layer skips), so the default suite now guards syntax/symbol
  regressions (Codex P2). Isolated `.venv-airflow` → **6 passed**
  (`.venv-airflow/bin/python -m pytest tests/test_dbt_transform_dag.py -v`).
- Full mainline suite: `.venv/bin/pytest -q` → **88 passed, 3 skipped,
  5 deselected** (integration).
- Live docker-compose run (`-p taxi_pamela_airflow`, run
  `manual__2026-07-18T21:17:32+00:00`, after merging faza-6-task-1's
  `stg_trips`): DAG **success**, both tasks green:
  - `dbt_run` (42s) — installs `dbt_utils` 1.4.1 into the temp copy, then
    `Done. PASS=6 WARN=0 ERROR=0` (5 tables + `stg_trips` view), via mounted ADC.
  - `dbt_test` (50s) — `Done. PASS=25 WARN=0 ERROR=0`, including
    `unique_stg_trips_trip_key` (proves the raw+stream dedup from task-1).
