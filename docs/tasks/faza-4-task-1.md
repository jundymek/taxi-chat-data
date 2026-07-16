# Faza 4 / Task 1: Pub/Sub producer — throttled Parquet replay

Status: planned
Executor: agent (wave 1, cohort with faza-4-task-2)
Plan: `docs/superpowers/plans/2026-07-16-faza-4-streaming-pubsub.md` → section
"Task 1" (technical source of truth — complete code + TDD steps; read it AND
the plan's "Global Constraints" before anything else)

## Acceptance Criteria
1. `.venv/bin/pytest tests/test_stream_producer.py -v` → 3 passed (fake
   publisher — no live GCP), full suite stays green.
2. `replay(cfg, publisher, limit, rate, dup_rate, rng)` returns
   `{"published": int, "duplicates": int}`; duplicates are IDENTICAL bytes
   published twice; every message carries `trip_key` + `source="replay"` attributes.
3. Missing Parquet → `FileNotFoundError` hinting `python -m ingestion.download`.
4. `docs/learn/faza-4-pubsub-producer.md` (Polish learning note) written.
5. `docs/features/faza-4-streaming-pubsub/faza-4-task-1/README.md` written.
6. Update THIS file: Status → done, subtasks checked, Dev Agent Record filled.

## Tasks / Subtasks
- [ ] Intent-sync with the consumer agent (see Coordination) BEFORE any code
- [ ] Failing tests (`tests/test_stream_producer.py`)
- [ ] Implement `ingestion/stream_producer.py` (plan has the full code)
- [ ] Tests green + full suite green
- [ ] Polish learning note + feature record
- [ ] Update this story (Status, checkboxes, record) + commit

## Coordination
- **Cohort with the faza-4-task-2 (consumer) agent — REQUIRED:** configure the
  cohort, write `intent.md` declaring your reading of the shared contract
  (NULL serialization, timestamp format, what a duplicate IS: same bytes, same
  trip_key, published twice), run intent-sync (`intent-ready.sh`, mutual acks).
- Contract doubts later → `agent-msg.sh send <peer> ...`, never guess.
- Task 0 (`ingestion/stream_common.py`) is on your base branch — verify before
  starting. Do NOT touch files outside your task's Files list (no
  `stream_common.py`, no `requirements.txt`).

## Dev Agent Record
### Agent Model Used
### Completion Notes
### File List
