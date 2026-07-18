# Faza 4 / Task 3: live run, dedup verification, docs, PR

Status: done
Executor: operator-session (after tasks 1–2 merge into the phase branch)
Plan: `docs/superpowers/plans/2026-07-16-faza-4-streaming-pubsub.md` → section "Task 3"

## Acceptance Criteria
1. `ensure_stream_resources` creates topic `trips-stream`, sub
   `trips-stream-sub`, dataset `stream`, table `stream.trips` (idempotent).
2. Live replay: producer `--limit 100000 --rate 500 --dup-rate 0.02` with the
   consumer running; consumer drains and idles out.
3. Dedup verified in BigQuery: `COUNT(*) == COUNT(DISTINCT trip_key)` (or the
   discrepancy recorded against the producer's injected-duplicate count).
4. README: Faza 4 checkbox + streaming section (commands, cost note, dedup query).
5. Full suite green; PR to master with live evidence in the body.

## Tasks / Subtasks
- [x] Ensure GCP resources (required one-time `gcloud services enable pubsub.googleapis.com`)
- [x] Replay 100k with consumer running; capture both summaries
- [x] Dedup verification queries; record numbers
- [x] README section + feature record `faza-4-task-3/README.md`
- [x] Push + PR to master

## Dev Agent Record
### Agent Model Used
Claude Fable 5 (claude-fable-5), operator session.
### Completion Notes
- Producer: `published=100000 duplicates=2008 elapsed=200.2s rate=500 msg/s`.
- Consumer: `seen=102008 inserted=102008 rejected=0` — full drain, zero
  redeliveries, clean idle shutdown.
- BigQuery: `total=99998, uniq=99995`. insertId caught 2010 of 2013 redundant
  rows (best-effort: 3 duplicate rows landed — recorded, not hidden). The 5
  sub-100k unique keys are REAL source-data collisions (two physically
  identical trips across the 6 key columns) — the very reason stg_trips
  dedups by trip_key in Faza 2; `stream.trips` meets the warehouse's dedup
  assumptions when merged in Faza 6.
### File List
`README.md` (UPDATE), `docs/tasks/faza-4-task-3.md` (UPDATE),
`docs/features/faza-4-streaming-pubsub/faza-4-task-3/README.md` (NEW)
