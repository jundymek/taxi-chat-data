# Faza 6 / Task 3: Airflow DAG orchestrating the dbt transform (local Docker)

## What was built
A local, manually-triggered Airflow DAG that orchestrates the existing dbt
project. `dags/dbt_transform_dag.py` defines `dag_id="dbt_transform"` with two
`BashOperator` tasks — `dbt_run` then `dbt_test` (`dbt_run >> dbt_test`),
`schedule=None`, `catchup=False`. `docker-compose.airflow.yml` runs Airflow
2.10.4 (LocalExecutor) + a Postgres metadata DB, mounts `dags/` and `dbt/`,
binds ADC read-only, and installs `dbt-bigquery` in-container. The DAG is
validated by an `ast`-based structure test (no Airflow import needed) plus the
live docker-compose run.

## Files touched
- `dags/dbt_transform_dag.py` (NEW) — the DAG (Airflow 2.x API, matches the container).
- `docker-compose.airflow.yml` (NEW) — Airflow LocalExecutor + Postgres + ADC bind; `dbt-bigquery>=1.8,<2.0`.
- `tests/test_dbt_transform_dag.py` (NEW) — `ast`-based structure test, no airflow import.
- `docs/learn/faza-6-airflow.md` (NEW) — Polish learning note.
- `docs/tasks/faza-6-task-3.md` (UPDATE) — story close-out.

## Key decisions
- **`apache-airflow` is NOT installed into any dev venv.** The shared mainline
  `.venv` is Python 3.14 (airflow 2.10 requires <3.13), and an airflow that does
  support 3.14 would downgrade the shared `fastapi` and pull ~70 heavy deps —
  breaking cohort peer bob's API work. So the structure test parses the DAG file
  with `ast` (no airflow import) and runs in the mainline `.venv` with zero
  skips; that the file really imports/runs as an Airflow DAG is proven by the
  live docker run (stronger than a venv import). Airflow stays out of
  `requirements.txt` (dev-only). Details in `DECISIONS.md` D1.
- **`BashOperator` + dbt (not a dbt-airflow plugin).** Single-purpose, manually
  triggered — demonstrates orchestration over the existing dbt project without
  extra abstraction (YAGNI, per spec). No Cloud Composer.
- **ADC via a read-only bind of `application_default_credentials.json`** — the
  proven Faza 2 pattern; the container authenticates as the operator, no
  service-account key files created.
- **Each task copies the mounted dbt project into a writable temp dir**
  (`mktemp -d`) before running dbt. The bind-mounted `dbt/` is host-owned and
  not writable by the in-container `airflow` user on Linux; `dbt deps` must
  write `dbt_packages/`. Copying makes the DAG portable across macOS and Linux
  hosts (Codex P1).
- **`dbt_run` runs `dbt deps && dbt seed && dbt run`** (still one task). The
  marts dims (`dim_location`/`dim_payment`/`dim_ratecode`) `ref()` the seed
  lookup tables, so seeding first makes the DAG self-contained even on a fresh
  `marts` dataset — not only when someone seeded out-of-band (Codex P2).

## Verification
- Structure test: mainline `.venv/bin/pytest tests/test_dbt_transform_dag.py -v`
  → **3 passed, 0 skipped** (`ast`-based, no airflow needed).
- Full mainline suite: `.venv/bin/pytest -q` → **88 passed, 5 deselected**
  (integration) — fully green, no skips.
- Live docker-compose run (`-p taxi_pamela_airflow`, run
  `manual__2026-07-18T21:26:21+00:00`, after merging faza-6-task-1's
  `stg_trips`): DAG **success**, both tasks green:
  - `dbt_run` (54s) — installs `dbt_utils` 1.4.1, seeds the lookups
    (`Done. PASS=3` — payment_type 7 / ratecode 6 / taxi_zone 265 rows), then
    builds models (`Done. PASS=6`), via mounted ADC.
  - `dbt_test` (45s) — `Done. PASS=25 WARN=0 ERROR=0`, including
    `unique_stg_trips_trip_key` (proves the raw+stream dedup from task-1).
