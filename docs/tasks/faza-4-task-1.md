# Faza 4 / Task 1: Pub/Sub producer — throttled Parquet replay (wave 1, COHORT)

Implement **"Task 1: `stream_producer.py`"** from
`docs/superpowers/plans/2026-07-16-faza-4-streaming-pubsub.md`. Read the full
task section AND the plan's "Global Constraints" — both binding. The plan
contains complete code and TDD steps.

## Cohort — REQUIRED
You are **cohort with the faza-4-task-2 (consumer) agent**. Before any code:
1. Configure the cohort so the intent-gate hook enforces the sync.
2. Write `intent.md` declaring your reading of the shared contract: NULL
   serialization, timestamp format, and what a duplicate IS (same bytes, same
   trip_key, published twice).
3. Run intent-sync (`intent-ready.sh`, ack the peer, get their ack).
4. Any contract doubt later → `agent-msg.sh send <peer> ...`, never guess.

## Dependencies
- Task 0 (`ingestion/stream_common.py` — contract + golden trip_key) is on
  your base branch; verify it exists before starting.
- Do NOT touch files outside your task's **Files** list (no
  `stream_common.py`, no `requirements.txt`). Unit tests use a fake
  publisher — no live GCP.

## Done when
- `.venv/bin/pytest tests/test_stream_producer.py -v` green (3 tests) and the
  full suite stays green.
- `docs/learn/faza-4-pubsub-producer.md` (Polish learning note) written.
- `docs/features/faza-4-streaming-pubsub/faza-4-task-1/README.md` written.
