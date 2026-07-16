# Faza 4 / Task 2: Pub/Sub consumer — batched streaming inserts (wave 1, COHORT)

Implement **"Task 2: `stream_consumer.py`"** from
`docs/superpowers/plans/2026-07-16-faza-4-streaming-pubsub.md`. Read the full
task section AND the plan's "Global Constraints" — both binding. The plan
contains complete code and TDD steps.

## Cohort — REQUIRED
You are **cohort with the faza-4-task-1 (producer) agent**. Before any code:
1. Configure the cohort so the intent-gate hook enforces the sync.
2. Write `intent.md` declaring your reading of the shared contract: what you
   ack vs nack (ack ONLY after successful insert; insert error → nack whole
   batch; malformed → log+ack+count), and trip_key as BigQuery insertId.
3. Run intent-sync (`intent-ready.sh`, ack the peer, get their ack).
4. Any contract doubt later → `agent-msg.sh send <peer> ...`, never guess.
5. If you finish first, you may `agent-wait.sh --background <peer>:pr-opened`
   and react to their PR (e.g. an edge-case test) instead of idling.

## Dependencies
- Task 0 (`ingestion/stream_common.py` — contract, `message_to_bq_row`) is on
  your base branch; verify it exists before starting.
- Do NOT touch files outside your task's **Files** list. Unit tests use fake
  messages and a fake BQ client — no live GCP, no live Pub/Sub.

## Done when
- `.venv/bin/pytest tests/test_stream_consumer.py -v` green (4 tests) and the
  full suite stays green.
- `docs/learn/faza-4-pubsub-consumer.md` (Polish learning note) written.
- `docs/features/faza-4-streaming-pubsub/faza-4-task-2/README.md` written.
