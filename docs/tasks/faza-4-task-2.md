# Faza 4 / Task 2: Pub/Sub consumer — batched streaming inserts

Status: planned
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
- [ ] Intent-sync with the producer agent (see Coordination) BEFORE any code
- [ ] Failing tests (`tests/test_stream_consumer.py`)
- [ ] Implement `ingestion/stream_consumer.py` (plan has the full code)
- [ ] Tests green + full suite green
- [ ] Polish learning note + feature record
- [ ] Update this story (Status, checkboxes, record) + commit

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
### Completion Notes
### File List
