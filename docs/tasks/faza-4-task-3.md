# Faza 4 / Task 3: live run, dedup verification, docs, PR

Status: planned
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
- [ ] Ensure GCP resources
- [ ] Replay 100k with consumer running; capture both summaries
- [ ] Dedup verification queries; record numbers
- [ ] README section + feature record `faza-4-task-3/README.md`
- [ ] Push + PR to master

## Dev Agent Record
### Agent Model Used
### Completion Notes
### File List
