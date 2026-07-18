# Faza 6 / Task 3: Airflow DAG orchestrating the dbt transform (local Docker)

Status: planned
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
- [ ] Ensure `apache-airflow` importable in `.venv` for the structure test
- [ ] Failing DAG structure test (`tests/test_dbt_transform_dag.py`)
- [ ] Implement `dags/dbt_transform_dag.py` (per plan)
- [ ] `docker-compose.airflow.yml` (LocalExecutor + Postgres + ADC bind)
- [ ] Structure test green
- [ ] Live docker compose run → trigger DAG → both tasks green
- [ ] Polish note + feature record + this story close-out
- [ ] PR

## Notes
- Deliberately single-purpose (dbt run+test), manually triggered — not a
  production cron, no Cloud Composer (YAGNI, per spec). No `genai/`/`api/`
  changes. `apache-airflow` in `.venv` is only for the import test; the
  container has its own runtime. Do NOT add airflow to `requirements.txt`
  (it's a heavy dev-only import; note it in the learn doc instead).

## Dev Agent Record
### Agent Model Used
### Completion Notes
### File List
