# Faza 4 / Task 1: Pub/Sub producer — throttled Parquet replay

Status: done
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
- [x] Intent-sync with the consumer agent (see Coordination) BEFORE any code
- [x] Failing tests (`tests/test_stream_producer.py`)
- [x] Implement `ingestion/stream_producer.py` (plan has the full code)
- [x] Tests green + full suite green
- [x] Polish learning note + feature record
- [x] Update this story (Status, checkboxes, record) + commit

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
claude-opus-4-8[1m] (autonomous mode)

### Debug Log References
- TDD path was clean: tests red (`ModuleNotFoundError`) → implement → 3 passed →
  full suite green.
- Codex review (btynag178) raised one [P2]: `KeyboardInterrupt` mid-replay
  skipped the publish-future flush while `main()` claimed messages were flushed
  (data-loss + misleading log). Fixed via try/finally flush + a regression test.
  Test count is now 4 (AC #1 literally says 3); the extra test is the codex-fix
  regression — AC intent (all pass, no live GCP) preserved. Full suite: 68
  passed, 5 integration deselected.

### Completion Notes
- Implemented `ingestion/stream_producer.py` per the plan's reference code
  (technical source of truth). Public `replay(cfg, publisher, limit, rate,
  dup_rate, rng) -> {"published", "duplicates"}` + `python -m
  ingestion.stream_producer` CLI (`--limit/--rate/--dup-rate/--month`).
- Cohort intent-sync with bob (consumer) completed BEFORE any code: cohort set,
  intent.md broadcast, mutual acks. Contract fully aligned — duplicates =
  byte-identical re-publishes, dedup on `insertId = trip_key`, NULL → JSON
  `null`, no extra top-level payload keys. See DECISIONS.md (all high
  confidence, none flagged).
- All message bytes built via Task 0's `row_to_message`/`compute_trip_key`;
  `stream_common.py` and `requirements.txt` were NOT touched (out of scope).
- Manual smoke (no live GCP): producer output round-tripped through the
  consumer's `message_to_bq_row` — `trip_key` attr == payload `trip_key`,
  `source="replay"` attribute present, NULL `airport_fee` preserved as JSON
  `null`; CLI `--help` renders. Live end-to-end is Task 3's runbook.

### File List
- `ingestion/stream_producer.py` (NEW)
- `tests/test_stream_producer.py` (NEW, 3 tests)
- `docs/learn/faza-4-pubsub-producer.md` (NEW, Polish learning note)
- `docs/features/faza-4-streaming-pubsub/faza-4-task-1/README.md` (NEW)
- `docs/tasks/faza-4-task-1.md` (UPDATE — this story close-out)
