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
- `tests/test_dbt_transform_dag.py` (NEW) — import-only structure test; `importorskip("airflow")`.
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
- **`DBT_LOG_PATH` / `DBT_TARGET_PATH` → `/tmp`** so dbt can write its artifacts
  even though the mounted `dbt/` dir is owned by the host user, not the
  in-container airflow user.

## Verification
- Structure test (isolated `.venv-airflow`): `3 passed` —
  `.venv-airflow/bin/python -m pytest tests/test_dbt_transform_dag.py -v`.
- Full mainline suite: `85 passed, 1 skipped, 5 deselected` —
  `.venv/bin/pytest -q` (the DAG test skips because airflow is absent there).
- Live docker-compose run (`-p taxi_pamela_airflow`, run
  `manual__2026-07-18T21:05:44+00:00`, after merging faza-6-task-1's
  `stg_trips`): DAG **success**, both tasks green:
  - `dbt_run` (46s) — `Done. PASS=6 WARN=0 ERROR=0` (5 tables + `stg_trips`
    view; `fct_trips` = 3.0m rows), reaching BigQuery via the mounted ADC.
  - `dbt_test` (52s) — `Done. PASS=25 WARN=0 ERROR=0`, including
    `unique_stg_trips_trip_key` (proves the raw+stream dedup from task-1).

## Notes
- The `dbt_run` task runs `dbt deps && dbt run`: the project depends on
  `dbt_utils` (via `packages.yml`), but `dbt_packages/` is gitignored and empty
  in a fresh container, so `dbt deps` must run first. Folded into `dbt_run` to
  keep the DAG at exactly two tasks (per AC #1). `DBT_LOG_PATH`/`DBT_TARGET_PATH`
  point at `/tmp` so dbt artifacts write to a container-writable path.
