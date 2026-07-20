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
> **Historical note (Faza 7):** `docker-compose.airflow.yml` no longer exists. It
> was merged into the root `docker-compose.yml` behind a profile — run Airflow with
> `docker compose --profile airflow <cmd>`. The commands below are kept as the
> record of what this task did at the time.

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
- [x] Structure test needs no `apache-airflow` — it parses the DAG file with
      `ast` and runs in the shared `.venv` (see Completion Notes for why airflow
      is kept out of the venv).
- [x] Failing DAG structure test (`tests/test_dbt_transform_dag.py`)
- [x] Implement `dags/dbt_transform_dag.py` (per plan)
- [x] `docker-compose.airflow.yml` (LocalExecutor + Postgres + ADC bind)
- [x] Structure test green
- [x] Live docker compose run → trigger DAG → both tasks green
- [x] Polish note + feature record + this story close-out
- [x] PR — https://github.com/jundymek/taxi-chat-data/pull/16

## Notes
- Deliberately single-purpose (dbt run+test), manually triggered — not a
  production cron, no Cloud Composer (YAGNI, per spec). No `genai/`/`api/`
  changes. The structure test parses the DAG with `ast` — no airflow needed in
  any dev venv; the container has its own runtime. Do NOT add airflow to
  `requirements.txt` (it's a heavy dev-only import; note it in the learn doc).

## Dev Agent Record
### Agent Model Used
claude-opus-4-8 (1M context), autonomous mode.

### Debug Log References
- First live DAG run failed: `dbt_run` exit code 2 —
  `Compilation Error: dbt expects 1 package(s) ... dbt_utils ... Run "dbt deps"`.
  Root cause: `dbt_packages/` is gitignored and empty in a fresh container.
- Codex review returned P1 (dbt package path not writable on the host-owned
  bind mount → not portable to Linux) and P2 (structure test skipped in the
  default suite). Both addressed — see Completion Notes / DECISIONS.md D5, D6.
- Codex round 2 flagged a further P2: `dbt run` skips `dbt seed`, but marts dims
  ref() seed tables → fails on a fresh warehouse. Fixed by folding `dbt seed`
  into `dbt_run` (DECISIONS.md D7).
- Final live run `manual__2026-07-18T21:26:21+00:00` (deps + seed + run): DAG
  success — seeds PASS=3, models PASS=6, `dbt_test` PASS=25 (incl.
  `unique_stg_trips_trip_key`).

### Completion Notes
- DAG `dbt_transform`: two `BashOperator` tasks `dbt_run >> dbt_test`,
  `schedule=None`, `catchup=False`. Each task copies the mounted dbt project
  into a writable `mktemp -d` dir, then runs dbt there — portable across host
  OSes (Codex P1). `dbt_run` = `dbt deps && dbt seed && dbt run` so it is
  self-contained on a fresh warehouse (Codex P2, D7); `dbt_test` = `dbt deps &&
  dbt test`. Still exactly two tasks.
- `docker-compose.airflow.yml`: Airflow 2.10.4 LocalExecutor + Postgres, mounts
  `dags/`+`dbt/`, read-only ADC bind (Faza 2 pattern), `dbt-bigquery>=1.8,<2.0`
  in-container.
- Structure test is `ast`-based: it parses `dags/dbt_transform_dag.py` and
  asserts dag_id / the two task ids / the `dbt_run >> dbt_test` dependency /
  `schedule=None` / `catchup=False` — no airflow import, so it runs in the
  shared `.venv` with no skips (Codex P2; simplified from an earlier
  isolated-venv approach at the operator's request).
- **Deviation from plan Step 1 (deliberate, documented in DECISIONS.md D1):** did
  NOT install `apache-airflow` into the shared mainline `.venv`. That venv is
  Python 3.14 (airflow 2.10 requires <3.13), and a 3.14-compatible airflow would
  downgrade the shared `fastapi` and break cohort peer bob's `api/main.py` work.
  The `ast` test needs no airflow at all; real Airflow import/execution is proven
  by the live docker run. Airflow is NOT added to `requirements.txt` (per Notes).
- Verification: DAG structure test 3 passed (mainline `.venv`, no skips); full
  mainline suite 88 passed, 5 deselected; live DAG run both tasks green.

### File List
- `dags/dbt_transform_dag.py` (NEW)
- `docker-compose.airflow.yml` (NEW)
- `tests/test_dbt_transform_dag.py` (NEW)
- `docs/learn/faza-6-airflow.md` (NEW)
- `docs/features/faza-6-eval-airflow/faza-6-task-3/README.md` (NEW)
- `docs/tasks/faza-6-task-3.md` (UPDATE — this story close-out)
