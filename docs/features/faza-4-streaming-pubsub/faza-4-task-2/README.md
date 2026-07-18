# Faza 4 / Task 2: Pub/Sub consumer — batched streaming inserts

## What was built
The consumer side of the wave-1 cohort. `ingestion/stream_consumer.py` reads
trip messages from the Pub/Sub subscription and streams them into BigQuery
`stream.trips` with at-least-once semantics and `insertId` (trip_key) dedup.

- `BatchWriter(bq_client, table_id, batch_size=500)` — buffers decoded rows +
  their Pub/Sub messages; `add(message)` decodes via the Task 0 contract
  (`message_to_bq_row`), stamps `ingested_at`, and flushes on size; `flush()`
  drains a partial buffer. Counters `seen / inserted / rejected`.
- Ack policy (at-least-once): ack ONLY after a successful whole-batch
  `insert_rows_json`; any insert error → nack the WHOLE batch (Pub/Sub
  redelivers, BigQuery insertId de-dups what already landed); malformed payload
  → log + ack + `rejected` (conscious simplicity — no dead-letter topic yet).
- CLI `python -m ingestion.stream_consumer [--batch-size N] [--max-seconds S]
  [--idle-timeout S]` — periodic partial flush on `--max-seconds`, self-exit
  after `--idle-timeout` idle, final flush + `seen/inserted/rejected` summary
  line (read by Task 3's runbook).

## Files touched
- `ingestion/stream_consumer.py` (NEW) — `BatchWriter` + streaming-pull CLI.
- `tests/test_stream_consumer.py` (NEW, 4 tests) — fake message + fake BQ, no
  live GCP: size-trigger flush + ack + trip_key insertId, insert-error nack,
  malformed ack+rejected, explicit partial flush.
- `docs/learn/faza-4-pubsub-consumer.md` (NEW) — Polish learning note.
- `docs/implementation-artifacts/faza-4-task-2.md` (UPDATE) — story close-out.

## Key decisions
- **trip_key as the only dedup mechanism.** `row_ids=[trip_key, ...]` feeds
  BigQuery's insertId best-effort dedup. Locked with the producer agent (alice)
  via intent-sync: duplicates are byte-identical re-publishes of a message
  built by `row_to_message`, so the same trip_key is emitted and BQ collapses
  them. Documented window/limitations in the learning note.
- **nack the WHOLE batch on any insert error, not per-row.** Simpler and safe
  precisely because insertId dedups the rows that already landed on redelivery.
- **nack on a *raised* insert too, not only a returned error list** (codex P1).
  `insert_rows_json` can raise on transient RPC/auth/network failures; caught
  and nacked so the consumer stays alive and keeps at-least-once. Covered by a
  5th regression test beyond the plan's 4.
- **malformed → ack + `rejected`, no dead-letter topic.** Prevents a poison
  message from looping forever; a DLT is the production-correct choice and is
  intentionally deferred (see learning note §6). Visible via the `rejected`
  counter in the summary line.
- **`threading.Lock` around the buffer.** The streaming pull invokes the
  callback on a thread pool; `add`/`flush` mutate shared state.
- Followed the plan's Task 2 code as the technical source of truth; the 4 tests
  are pinned to that exact `BatchWriter` API.

## Verification
- `.venv/bin/pytest tests/test_stream_consumer.py -v` → **5 passed** (the 4
  plan tests + 1 codex-driven regression test for a raised insert).
- Full suite `.venv/bin/pytest` → **69 passed, 5 deselected** (integration
  tests deselected — no live GCP touched by unit tests, per phase constraint).
- Live Pub/Sub→BigQuery smoke run + end-to-end dedup verification is Task 3
  (in the operator session, after this and the producer PR merge).
