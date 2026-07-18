# Faza 6 / Task 1: merge stream.trips into stg_trips (UNION + trip_key dedup)

Status: planned
Executor: agent (wave 1, solo — BLOCKS task-2 and task-3)
Plan: `docs/superpowers/plans/2026-07-18-faza-6-eval-airflow-stream-merge.md` →
section "Task 1" (technical source of truth — complete SQL + steps; read it AND
"Global Constraints" first).
Spec: `docs/superpowers/specs/2026-07-18-faza-6-eval-airflow-stream-merge-design.md`.

## Dependencies
- **None upstream.** This task runs FIRST and alone.
- **Downstream:** task-2 (eval queries `marts.*`, which rebuilds from this
  `stg_trips`) and task-3 (Airflow runs `dbt run/test` on this model) both
  depend on this being merged. Do NOT start them before this lands.

## Acceptance Criteria
1. `dbt/models/staging/_staging__sources.yml` declares a new `stream` source
   (schema `stream`, table `trips`) alongside the existing `raw` source.
2. `stg_trips.sql` UNIONs raw + stream: `raw_cleaned` (unchanged raw logic) +
   `stream_cleaned` (stream's already-renamed columns mapped to the SAME stg
   schema, `trip_key` RECOMPUTED with `dbt_utils.generate_surrogate_key` over
   the same 6 fields), then `union all` → dedup by `trip_key` via
   `qualify row_number() over (partition by trip_key order by pickup_datetime)`.
3. Output columns of `stg_trips` are UNCHANGED (same as pre-Faza-6).
4. `cd dbt && dbt build --select stg_trips` green; `unique` + `not_null` on
   `trip_key` PASS (dedup across raw+stream proven).
5. Row-count sanity: `SELECT COUNT(*) n, COUNT(DISTINCT trip_key) uniq FROM
   staging.stg_trips` → `n == uniq`; `n` ≥ pre-Faza-6 count.
6. `docs/learn/faza-6-stream-merge.md` (Polish) + feature record written.
7. THIS story updated before PR (Status: done, checkboxes, Dev Agent Record).

## Tasks / Subtasks
- [ ] Add `stream` source to `_staging__sources.yml`
- [ ] Rewrite `stg_trips.sql` (UNION raw+stream, recompute key, dedup) per plan
- [ ] Confirm `trip_key` unique/not_null tests still bind
- [ ] `dbt build --select stg_trips` green + row-count sanity
- [ ] Polish note + feature record + this story close-out
- [ ] PR

## Notes
- trip_key consistency is VERIFIED: the Faza 4 consumer
  (`ingestion/stream_common.py`) computes it from the same 6 fields/order as the
  macro. We still recompute in staging (one source of truth). No `genai/` or
  `api/` changes. No `requirements.txt` changes.

## Dev Agent Record
### Agent Model Used
### Completion Notes
### File List
