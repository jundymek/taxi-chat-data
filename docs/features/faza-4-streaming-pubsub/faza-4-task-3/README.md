# Faza 4 / Task 3: live run, dedup verification, docs, PR

## What was built
The operator-session closeout: Pub/Sub API enabled (first use in the project),
resources created idempotently, a live 100k replay with 2% duplicate injection
run against the real topic with the consumer draining into BigQuery, and
deduplication verified with queries rather than asserted.

## Files touched
- `README.md` (UPDATE) — Faza 4 checkbox + "Streaming (Faza 4)" runbook
  (commands, at-least-once explanation, dedup query, cost note).
- `docs/tasks/faza-4-task-3.md` (UPDATE) — story close-out with live numbers.
- This feature record.

## Key decisions
- **Record the imperfections, don't round them off.** insertId is best-effort
  by contract: it caught 2010 of 2013 redundant rows; 3 duplicates landed.
  total=99998 vs uniq=99995 also exposed 5 REAL duplicate trips in the source
  data (identical across all 6 key columns) — evidence for why the warehouse
  staging layer dedups by trip_key, and a ready-made interview story.
- One-time `gcloud services enable pubsub.googleapis.com` documented in the
  README (the ensure step fails with SERVICE_DISABLED otherwise).

## Verification
- Producer: `published=100000 duplicates=2008 elapsed=200.2s rate=500 msg/s`.
- Consumer: `seen=102008 inserted=102008 rejected=0`, clean idle shutdown.
- `SELECT COUNT(*), COUNT(DISTINCT trip_key)` → 99998 / 99995;
  `GROUP BY trip_key HAVING c > 1` → 3 rows.
- Full unit suite: 74 passed, 5 integration deselected.
