# Faza 4 / Task 0: streaming contract — codec, dbt-compatible trip_key, resources

## What was built
The shared contract both wave-1 agents (producer, consumer) build against,
executed in the operator session BEFORE spawning. `ingestion/stream_common.py`
fixes the message field set (19 parquet columns), the JSON codec
(`row_to_message`/`message_to_bq_row` with stg_trips-style column renames),
the `trip_key` recipe (MD5, dbt_utils-compatible), idempotent GCP resource
creation (topic/subscription/dataset/table), and `StreamConfig`.

## Files touched
- `ingestion/stream_common.py` (NEW) — the contract module.
- `tests/test_stream_common.py` (NEW, 7 tests) — incl. the golden trip_key test.
- `requirements.txt` (UPDATE) — `google-cloud-pubsub>=2.21`.
- `.env.example` (UPDATE) — `PUBSUB_TOPIC`, `PUBSUB_SUBSCRIPTION`, `BQ_DATASET_STREAM`.

## Key decisions
- **trip_key calibrated against live BigQuery, not guessed.** `_bq_string`
  mimics BigQuery `CAST(x AS STRING)` semantics (timestamps as
  `YYYY-MM-DD HH:MM:SS+00`, integral floats without `.0`). Verified two ways:
  a live SQL expression reproducing `dbt_utils.generate_surrogate_key`
  returned the identical hash (`4c4bf4d2…`), and a REAL `stg_trips` row's
  trip_key (`00009633…`) was reproduced from its source columns in Python.
  This key is the BigQuery insertId AND the future merge key with the
  warehouse (Faza 6).
- **All shared concerns land here** (dependency, env vars, renames), so the
  cohort agents share semantics but zero files.

## Verification
- `.venv/bin/pytest tests/test_stream_common.py -v` — 7 passed.
- Live calibration queries documented above (expression + real-row check).
