# Faza 6 / Task 1: merge stream.trips into stg_trips (UNION + trip_key dedup)

Status: done
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
- [x] Add `stream` source to `_staging__sources.yml`
- [x] Rewrite `stg_trips.sql` (UNION raw+stream, recompute key, dedup) per plan
- [x] Confirm `trip_key` unique/not_null tests still bind
- [x] `dbt build --select stg_trips` green + row-count sanity
- [x] Polish note + feature record + this story close-out
- [ ] PR

## Notes
- trip_key consistency is VERIFIED: the Faza 4 consumer
  (`ingestion/stream_common.py`) computes it from the same 6 fields/order as the
  macro. We still recompute in staging (one source of truth). No `genai/` or
  `api/` changes. No `requirements.txt` changes.

## Dev Agent Record
### Agent Model Used
claude-opus-4-8[1m] (Claude Opus 4.8, 1M context)

### Debug Log References
- `docker-compose.yml` dbt service ENTRYPOINT is already `dbt`; invoke as
  `docker compose -p taxi_alice run --rm dbt build --select stg_trips` (the stack
  note's `dbt dbt build` double-invokes and errors with "No such command 'dbt'").
- `dbt deps` must run once in a fresh worktree to install `dbt_utils` before build.

### Completion Notes List
- Added `stream` source and rewrote `stg_trips.sql` per plan (technical source of
  truth): `raw_cleaned` (pre-Faza-6 logic verbatim) + `stream_cleaned` (stream's
  renamed cols → same stg schema, `trip_key` recomputed from the same 6 fields)
  → `union all` → dedup by `trip_key` via `qualify row_number()`.
- `trip_key` consistency verified against `ingestion/stream_common.py:29-32`
  (same 6 fields/order as the macro). Key is still recomputed in staging for a
  single source of truth (design-locked).
- `_staging__models.yml` already carries `trip_key` unique/not_null — no edit.
- Verification: `dbt build --select stg_trips` → PASS=6/0 errors; unique+not_null
  on `trip_key` PASS. Row-count sanity: n = uniq = 2,998,748 (== pre-Faza-6
  baseline; stream's 99,998 rows all deduped onto raw twins → cross-path dedup
  proven live).
- Dedup tie-break hardened after Codex review (P2): `order by pickup_datetime`
  alone was nondeterministic (pickup_datetime is part of trip_key, so duplicate
  pairs tie). Now `order by source_rank, to_json_string(unioned)` — raw wins over
  the simulated stream, with a content-deterministic final tie-break;
  `source_rank` is dropped via `select * except (source_rank)` so output columns
  are unchanged. Verified: n == uniq == 2,998,748, 16 output columns (no leak).
- Pre-existing dbt 1.12 deprecation warning (`MissingArgumentsPropertyInGeneric
  TestDeprecation`) on the `_staging__models.yml` inline `tests:` shorthand is
  unrelated to this change and out of scope — not addressed.
- No `genai/`, `api/`, or `requirements.txt` changes; no new models.

### File List
- `dbt/models/staging/_staging__sources.yml` (UPDATE)
- `dbt/models/staging/stg_trips.sql` (UPDATE)
- `docs/learn/faza-6-stream-merge.md` (NEW)
- `docs/features/faza-6-eval-airflow/faza-6-task-1/README.md` (NEW)
- `docs/tasks/faza-6-task-1.md` (UPDATE, this file)
