# Faza 4 / Task 0: streaming contract — codec, dbt-compatible trip_key, resources

Status: done
Executor: operator-session
Plan: `docs/superpowers/plans/2026-07-16-faza-4-streaming-pubsub.md` → section "Task 0"

## Acceptance Criteria
1. `.venv/bin/pytest tests/test_stream_common.py -v` → 7 passed, including the
   golden trip_key test pinned against live BigQuery.
2. `compute_trip_key` reproduces a REAL `stg_trips` trip_key from source columns.
3. `google-cloud-pubsub` installed via `requirements.txt`; stream env vars in
   `.env.example`.
4. Committed to the phase branch BEFORE any agent spawn.

## Tasks / Subtasks
- [x] Failing contract tests (7)
- [x] Implement `ingestion/stream_common.py` (fields, codec, trip_key, ensure_*, StreamConfig)
- [x] Dependency + `.env.example`
- [x] Calibrate golden trip_key vs live BQ (expression `4c4bf4d2…` + real row `00009633…`)
- [x] Full suite green (64 passed), commit `698ab97`

## Dev Agent Record
### Agent Model Used
Claude Fable 5 (claude-fable-5), operator session.
### Completion Notes
- `_bq_string` matched BigQuery CAST semantics on first calibration
  (timestamps `%Y-%m-%d %H:%M:%S+00`, integral floats without `.0`).
- Details: `docs/features/faza-4-streaming-pubsub/faza-4-task-0/README.md`.
### File List
`ingestion/stream_common.py`, `tests/test_stream_common.py`,
`requirements.txt`, `.env.example`,
`docs/features/faza-4-streaming-pubsub/faza-4-task-0/README.md`
