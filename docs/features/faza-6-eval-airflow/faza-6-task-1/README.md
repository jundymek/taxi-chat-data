# Faza 6 / Task 1: merge stream.trips into stg_trips (UNION + trip_key dedup)

## What was built
Merged the Faza 4 simulated stream (`stream.trips`) into the dbt staging model
`stg_trips`, closing the Faza 4 debt. `stg_trips` now covers batch (`raw.trips`)
and stream, deduplicated by a `trip_key` that is recomputed on both paths with
the same `dbt_utils.generate_surrogate_key` recipe. Output columns are unchanged,
so every model above (`fct_trips`, dims, the eval/NL2SQL layer) is unaffected.

## Files touched
- `dbt/models/staging/_staging__sources.yml` (UPDATE) — added a second source
  `stream` (schema `stream`, table `trips`) alongside `raw`.
- `dbt/models/staging/stg_trips.sql` (UPDATE) — split into `raw_cleaned` (the
  pre-Faza-6 `cleaned` logic verbatim) + `stream_cleaned` (stream's already-
  renamed columns mapped to the same stg schema, `trip_key` recomputed from the
  same 6 fields), then `union all` → `deduped` via
  `qualify row_number() over (partition by trip_key order by pickup_datetime) = 1`.
- `dbt/models/staging/_staging__models.yml` (VERIFY, no change) — `trip_key`
  `unique` + `not_null` tests already present and still bind.
- `docs/learn/faza-6-stream-merge.md` (NEW) — Polish learning note.
- `docs/tasks/faza-6-task-1.md` (UPDATE) — story close-out.

## Key decisions
- **trip_key recomputed in staging, not trusted from the stream.** The Faza 4
  consumer (`ingestion/stream_common.py:29-32`) already stored a `trip_key` from
  the same 6 fields/order, but staging recomputes it with the dbt macro. One
  source of truth for the key formula — immune to any future consumer drift.
- **`union all` + explicit key-based dedup, not `union distinct`.** We dedup by
  the business key `trip_key`, not by full-row equality (batch/stream rows can
  differ in trivial ways).
- **Deterministic tie-break: `order by source_rank, to_json_string(unioned)`.**
  `pickup_datetime` alone is not a valid tie-break — it is part of `trip_key`, so
  every duplicate pair ties and BigQuery would pick a winner arbitrarily (the
  view could flap across builds). `source_rank` (0=raw, 1=stream) makes the
  authoritative batch win; `to_json_string` gives a content-deterministic final
  order. `source_rank` is a throwaway column removed via `select * except
  (source_rank)`, so output columns are unchanged. (Codex review P2; see
  `DECISIONS.md` D5.)
- **Scope stayed inside dbt.** No `genai/`, `api/`, or `requirements.txt`
  changes; no new models. (See `DECISIONS.md` D1–D4.)

## Verification
- `docker compose -p taxi_alice run --rm dbt build --select stg_trips` →
  `PASS=6 WARN=0 ERROR=0`. `unique_stg_trips_trip_key` and
  `not_null_stg_trips_trip_key` PASS (dedup across raw+stream proven).
- Row-count sanity on the rebuilt view:
  `SELECT COUNT(*) n, COUNT(DISTINCT trip_key) uniq FROM
  taxi-chat-data.staging.stg_trips` → `n = 2,998,748`, `uniq = 2,998,748`
  (`n == uniq`). Equal to the pre-Faza-6 baseline (2,998,748): the stream's
  99,998 rows are a replay of the same parquet already in raw, so all collapsed
  onto their batch twins via the recomputed key — a live proof of cross-path
  dedup. `n ≥ pre-Faza-6 count` holds.
