# Faza 4 / Task 1: Pub/Sub producer — throttled Parquet replay

## What was built
`ingestion/stream_producer.py` — a thin CLI + library that replays the local
`yellow_tripdata_<month>.parquet` into the Pub/Sub topic `cfg.topic`, simulating
a live feed. It throttles to an average `--rate` msg/s and deliberately
re-publishes a `--dup-rate` fraction of messages as byte-identical duplicates so
the at-least-once + BigQuery `insertId` dedup story (consumer, Task 2) is
demonstrable live. Every message is built exclusively via Task 0's
`row_to_message` / `compute_trip_key`, so producer and consumer share semantics
without sharing files.

Public surface:
- `replay(cfg, publisher, limit, rate, dup_rate, rng) -> {"published": int, "duplicates": int}`
- CLI: `python -m ingestion.stream_producer [--limit N] [--rate R] [--dup-rate P] [--month YYYY-MM]`

## Files touched
- `ingestion/stream_producer.py` (NEW) — the producer CLI + `replay()` library fn.
- `tests/test_stream_producer.py` (NEW, 4 tests) — fake publisher, fake future,
  scripted RNG; no live GCP. Includes an interrupt-flush regression test.
- `docs/learn/faza-4-pubsub-producer.md` (NEW, Polish) — study note on Pub/Sub,
  publish futures, throttling, and why duplicates are injected on purpose.
- `docs/implementation-artifacts/faza-4-task-1.md` (UPDATE) — story close-out.

## Key decisions
- **Duplicate = identical bytes + identical attrs, published twice.** `dup_rate`
  re-calls `publisher.publish(topic_path, data, **attrs)` with the same objects,
  so `trip_key` matches and BigQuery's `insertId` collapses them. Confirmed with
  the cohort consumer (bob) during intent-sync — his only dedup mechanism is
  `insertId = trip_key`.
- **`source="replay"` is a Pub/Sub attribute, not a payload key.** Keeps the
  payload to `MESSAGE_FIELDS` + `trip_key` exactly, which the consumer relies on
  (it maps only those). `trip_key` is duplicated into attributes for cheap
  routing/inspection without decoding the body.
- **Average-rate throttling.** `expected_elapsed = published / rate`; sleep the
  delta. Converges the *average* publish rate to `--rate` and self-corrects for
  publish latency, unlike a fixed per-message sleep. `--rate 0` = unthrottled.
- **Futures collected then awaited — even on interrupt.** `publish()` is async;
  we gather futures and await `.result(timeout=60)` in a `try/finally`, so a
  failed publish surfaces as an error and a `KeyboardInterrupt` mid-replay still
  flushes already-accepted messages instead of dropping them (codex P2 fix).
- **Missing Parquet is a helpful failure.** `_parquet_path` raises
  `FileNotFoundError` hinting `python -m ingestion.download` instead of an opaque
  pyarrow error.

## Verification
- `.venv/bin/pytest tests/test_stream_producer.py -v` — **4 passed**.
- Full suite: `.venv/bin/pytest -m "not integration"` — **68 passed, 5 deselected**.
- Manual smoke (no GCP): built a tiny local Parquet, ran
  `replay(cfg, FakePublisher(), limit=2, rate=0, dup_rate=0)` and round-tripped
  every published message back through the consumer's `message_to_bq_row` —
  `trip_key` attribute equalled the payload `trip_key`, `source="replay"`, and a
  NULL `airport_fee` survived as JSON `null`. `python -m ingestion.stream_producer
  --help` renders without touching GCP.
- Live end-to-end against a real topic is Task 3's runbook, not this task.
