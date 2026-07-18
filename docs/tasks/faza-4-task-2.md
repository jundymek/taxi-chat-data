# Faza 4 / Task 2: Pub/Sub consumer — batched streaming inserts

Status: done
Executor: agent (wave 1, cohort with faza-4-task-1)
Plan: `docs/superpowers/plans/2026-07-16-faza-4-streaming-pubsub.md` → section
"Task 2" (technical source of truth — complete code + TDD steps; read it AND
the plan's "Global Constraints" before anything else)

## Acceptance Criteria
1. `.venv/bin/pytest tests/test_stream_consumer.py -v` → 4 passed (fake
   messages + fake BQ client — no live GCP/Pub/Sub), full suite stays green.
2. `BatchWriter(bq_client, table_id, batch_size)` with `add(message)` /
   `flush()` and counters `seen/inserted/rejected`; ack ONLY after successful
   insert; insert error → nack the WHOLE batch; malformed → log + ack +
   `rejected`; `row_ids` = trip_key (BigQuery insertId dedup).
3. CLI flushes partial buffers on `--max-seconds` and exits after
   `--idle-timeout` without messages.
4. `docs/learn/faza-4-pubsub-consumer.md` (Polish learning note) written.
5. `docs/features/faza-4-streaming-pubsub/faza-4-task-2/README.md` written.
6. Update THIS file: Status → done, subtasks checked, Dev Agent Record filled.

## Tasks / Subtasks
- [x] Intent-sync with the producer agent (see Coordination) BEFORE any code
- [x] Failing tests (`tests/test_stream_consumer.py`)
- [x] Implement `ingestion/stream_consumer.py` (plan has the full code)
- [x] Tests green + full suite green
- [x] Polish learning note + feature record
- [x] Update this story (Status, checkboxes, record) + commit

## Coordination
- **Cohort with the faza-4-task-1 (producer) agent — REQUIRED:** configure the
  cohort, write `intent.md` declaring your reading of the shared contract
  (what you ack vs nack, trip_key as insertId, malformed handling), run
  intent-sync (`intent-ready.sh`, mutual acks).
- Contract doubts later → `agent-msg.sh send <peer> ...`, never guess. If you
  finish first, `agent-wait.sh --background <peer>:pr-opened` and react to
  their PR instead of idling.
- Task 0 (`ingestion/stream_common.py`) is on your base branch — verify before
  starting. Do NOT touch files outside your task's Files list.

## Dev Agent Record
### Agent Model Used
Claude Opus 4.8 (1M context) — agent `bob`, autonomous mode.

### Debug Log References
- Cohort intent-sync with `alice` (faza-4-task-1, producer): set-cohort →
  wrote `intent.md` → `intent-ready.sh` → received `from-alice-001` intent,
  read + ack'd; alice ack'd back → phase `intent-synced`. Alice confirmed all
  three contract questions (byte-identical duplicate re-publish carrying the
  same `trip_key`; explicit JSON `null` for NULLs; only `MESSAGE_FIELDS` +
  `trip_key` as payload keys — `source` lives in Pub/Sub attributes I ignore).
- TDD: 4 tests RED (`ModuleNotFoundError`) → implemented → 4 GREEN, full suite
  68 passed / 5 deselected.
- Spec/artifact note: the pre-PR checklist references
  `docs/implementation-artifacts/faza-4-task-2.md`, but the actual story file
  is `docs/tasks/faza-4-task-2.md` (this file) — updated here.

### Completion Notes
- Implemented `ingestion/stream_consumer.py` per the plan's Task 2 code (the
  declared technical source of truth): `BatchWriter` + streaming-pull CLI.
- Ack policy is at-least-once: ack only after a successful whole-batch insert;
  insert error → nack the whole batch (redelivery + insertId dedup); malformed
  → log + ack + `rejected` (no dead-letter topic this phase — conscious
  simplicity, documented in the learning note).
- `row_ids = [trip_key, ...]` uses BigQuery insertId as the best-effort dedup
  for the producer's deliberate duplicates.
- Two deviations from the plan's verbatim code, both from codex P1 findings:
  (a) also nack the batch when `insert_rows_json` *raises* (transient
  RPC/auth/network), not only when it returns a row-level error list —
  otherwise the popped batch was left neither acked nor nacked and the
  exception could stop the consumer; (b) a nacked batch fires an `on_retry`
  hook that resets the CLI idle timer, so `--idle-timeout` cannot shut down the
  consumer before Pub/Sub redelivers the batch it just nacked. Two regression
  tests added, so this task ships 6 tests vs AC #1's stated 4. See DECISIONS.md
  D5/D6.
- Unit tests use fake message + fake BQ (no live GCP); live smoke + dedup
  verification is Task 3.
- Did not touch `stream_common.py`, `stream_producer.py`, `requirements.txt`,
  `.env.example`, or `dbt/`.

### File List
- `ingestion/stream_consumer.py` (NEW)
- `tests/test_stream_consumer.py` (NEW)
- `docs/learn/faza-4-pubsub-consumer.md` (NEW)
- `docs/features/faza-4-streaming-pubsub/faza-4-task-2/README.md` (NEW)
- `docs/tasks/faza-4-task-2.md` (UPDATE — this story)
