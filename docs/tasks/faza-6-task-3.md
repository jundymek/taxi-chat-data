# Faza 6 / Task 3: Airflow DAG orchestrating the dbt transform (local Docker)

Status: done
Executor: agent (wave 2, cohort with faza-6-task-2 — parallel, no file overlap)
Plan: `docs/superpowers/plans/2026-07-18-faza-6-eval-airflow-stream-merge.md` →
section "Task 3" (technical source of truth — complete code + steps; read it AND
"Global Constraints" first).
Spec: `docs/superpowers/specs/2026-07-18-faza-6-eval-airflow-stream-merge-design.md`.

## Dependencies
- **Upstream: faza-6-task-1 MUST be merged first** — the DAG runs `dbt run` +
  `dbt test`, which includes the merged `stg_trips`. Configure with
  `set-depends-on.sh`; the live DAG run must exercise task-1's model.
- **Cohort peer: faza-6-task-2** (eval). No file overlap: this task owns
  `dags/`, `docker-compose.airflow.yml`, `tests/test_dbt_transform_dag.py`;
  task-2 owns `genai/`, `tests/test_eval.py`, `api/main.py`, `docs/eval/`.
  Run `set-cohort.sh faza-6-task-2`.

## Acceptance Criteria
1. `dags/dbt_transform_dag.py` defines an importable DAG `dag_id="dbt_transform"`
   with exactly two `BashOperator` tasks `dbt_run` and `dbt_test`, dependency
   `dbt_run >> dbt_test`, `schedule=None`, `catchup=False`.
2. `docker-compose.airflow.yml` — Airflow LocalExecutor + Postgres metadata DB,
   mounts `dags/` and `dbt/`, binds ADC read-only into the container (the proven
   Faza 2 pattern), installs `dbt-bigquery` in-container.
3. `tests/test_dbt_transform_dag.py` validates DAG structure by IMPORT (no live
   Airflow): dag_id, exactly the two task ids, the `dbt_run >> dbt_test`
   dependency, and `schedule=None`. `.venv/bin/pytest
   tests/test_dbt_transform_dag.py -v` → all PASS. Full suite stays green.
4. One live run: `docker compose -f docker-compose.airflow.yml up` → trigger
   `dbt_transform` → both tasks succeed (green), reaching BigQuery via the
   mounted ADC (capture for the PR).
5. `docs/learn/faza-6-airflow.md` (Polish) + feature record written.
6. THIS story updated before PR (Status: done, checkboxes, Dev Agent Record).

## Tasks / Subtasks
- [x] Ensure `apache-airflow` importable for the structure test — provisioned an
      isolated `.venv-airflow` (py3.11, airflow 2.10.4) instead of the shared
      `.venv` (see Completion Notes for why).
- [x] Failing DAG structure test (`tests/test_dbt_transform_dag.py`)
- [x] Implement `dags/dbt_transform_dag.py` (per plan)
- [x] `docker-compose.airflow.yml` (LocalExecutor + Postgres + ADC bind)
- [x] Structure test green
- [x] Live docker compose run → trigger DAG → both tasks green
- [x] Polish note + feature record + this story close-out
- [ ] PR (in progress — pre-PR checkpoint)

## Notes
- Deliberately single-purpose (dbt run+test), manually triggered — not a
  production cron, no Cloud Composer (YAGNI, per spec). No `genai/`/`api/`
  changes. `apache-airflow` in `.venv` is only for the import test; the
  container has its own runtime. Do NOT add airflow to `requirements.txt`
  (it's a heavy dev-only import; note it in the learn doc instead).

## Dev Agent Record
### Agent Model Used
claude-opus-4-8 (1M context), autonomous mode.

### Debug Log References
- First live DAG run failed: `dbt_run` exit code 2 —
  `Compilation Error: dbt expects 1 package(s) ... dbt_utils ... Run "dbt deps"`.
  Root cause: `dbt_packages/` is gitignored and empty in a fresh container.
  Fix: `dbt_run` bash command now runs `dbt deps && dbt run` (kept at two tasks).
- Second live run `manual__2026-07-18T21:05:44+00:00`: DAG success — `dbt_run`
  PASS=6, `dbt_test` PASS=25 (incl. `unique_stg_trips_trip_key`).

### Completion Notes
- DAG `dbt_transform`: two `BashOperator` tasks `dbt_run >> dbt_test`,
  `schedule=None`, `catchup=False`. `dbt_run` runs `dbt deps && dbt run` so the
  dbt_utils dependency installs in a fresh container (still exactly two tasks).
- `docker-compose.airflow.yml`: Airflow 2.10.4 LocalExecutor + Postgres, mounts
  `dags/`+`dbt/`, read-only ADC bind (Faza 2 pattern), `dbt-bigquery>=1.8,<2.0`
  in-container, `DBT_LOG_PATH`/`DBT_TARGET_PATH` → `/tmp` for writable artifacts.
- **Deviation from plan Step 1 (deliberate, documented in DECISIONS.md D1):** did
  NOT install `apache-airflow` into the shared mainline `.venv`. That venv is
  Python 3.14 (airflow 2.10 requires <3.13), and a 3.14-compatible airflow would
  downgrade the shared `fastapi` and break cohort peer bob's `api/main.py` work.
  Used an isolated `.venv-airflow` (py3.11, airflow 2.10.4 — matches the
  container) for the structure test, and `pytest.importorskip("airflow")` so the
  full mainline suite stays green (the DAG test skips under `.venv`). Airflow is
  NOT added to `requirements.txt` (per Notes).
- Verification: structure test 3 passed (`.venv-airflow`); full mainline suite
  85 passed, 1 skipped, 5 deselected; live DAG run both tasks green.

### File List
- `dags/dbt_transform_dag.py` (NEW)
- `docker-compose.airflow.yml` (NEW)
- `tests/test_dbt_transform_dag.py` (NEW)
- `.gitignore` (UPDATE — ignore `.venv-airflow/`)
- `docs/learn/faza-6-airflow.md` (NEW)
- `docs/features/faza-6-eval-airflow/faza-6-task-3/README.md` (NEW)
- `docs/tasks/faza-6-task-3.md` (UPDATE — this story close-out)
