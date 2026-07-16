# Faza 4: Simulated streaming with real Pub/Sub — Design

**Goal:** A working streaming path next to the batch path: a producer replays
the local Parquet file into a real Pub/Sub topic with throttling (simulating a
live feed), a consumer subscribes and writes rows into BigQuery
`stream.trips` via streaming inserts, and at-least-once semantics +
deduplication are demonstrated, not just described. Deliverables are two CLIs:
`python -m ingestion.stream_producer` and `python -m ingestion.stream_consumer`.

**Out of scope (deferred deliberately):** merging `stream.trips` into dbt
`stg_trips` (lands in Faza 6 together with Airflow orchestration), dead-letter
queue for malformed messages (logged + counted instead — conscious simplicity),
partitioning of `stream.trips` (sample is small; physical optimization was
Faza 2's lesson).

**Approach (decided):** two thin CLI modules mirroring the existing
`ingestion/` patterns (env-driven `Config`, idempotent `ensure_*`), sharing a
message contract module. Rejected: single asyncio process (artificially couples
two independently-living components, spoils the 2-agent split); Dataflow/Beam
(outside free tier and this phase's learning goal — raw Pub/Sub mechanics).

**Decisions from brainstorming:**
- Volume: sample replay, default `--limit 100000` rows at `--rate 500` msg/s
  (~3–4 min demo); full-month replay possible by flag.
- Consumer write path: classic **streaming inserts** (`insert_rows_json` with
  `row_ids=trip_key`) — matches DESIGN.md's stated learning goal. Cost note:
  streaming inserts are NOT free-tier (~$0.05/GB); the 100k sample costs
  cents, documented in the runbook.
- Message format: JSON (UTF-8), schema fixed in the contract module.

## Architecture

```
data/yellow_tripdata_2023-01.parquet
        │  pyarrow batches
        ▼
ingestion/stream_producer.py ──JSON──▶ Pub/Sub topic `trips-stream`
   (--limit, --rate, --dup-rate)              │ pull, flow control
                                              ▼
                              subscription `trips-stream-sub` (ack 30s)
                                              │
                          ingestion/stream_consumer.py
                     buffer ≤500 rows / 2s → insert_rows_json(row_ids)
                                              │ ack on success / nack on failure
                                              ▼
                                 BigQuery `stream.trips`
```

Shared contract: `ingestion/stream_common.py`. GCP resources are created
idempotently by `ensure_stream_resources()`: topic `trips-stream`, pull
subscription `trips-stream-sub`, dataset `stream` (US), table `stream.trips`
(schema of `raw.trips` + `trip_key STRING NOT NULL` + `ingested_at TIMESTAMP`).

## Message contract (`stream_common.py`, fixed in Task 0)

- Payload: JSON object with the trip columns in simple types
  (`pickup_datetime`/`dropoff_datetime` ISO-8601 strings, amounts as floats,
  ids as ints, missing values as explicit `null`) + `trip_key`.
- `trip_key`: deterministic MD5 over the same identifying columns and recipe
  as dbt's `dbt_utils.generate_surrogate_key` in `stg_trips` — computed by the
  producer. Triple duty: BigQuery `insertId` (best-effort dedup), duplicate
  verification key, and the future merge key with `stg_trips` (Faza 6).
  A **golden test** pins the Python hash to a known dbt-produced value.
- Pub/Sub attributes: `trip_key`, `source="replay"`.

Interfaces (later tasks build against exactly these):

```python
MESSAGE_FIELDS: tuple[str, ...]                    # payload columns, fixed order
def compute_trip_key(row: dict) -> str
def row_to_message(row: dict) -> bytes             # raises KeyError on missing fields
def message_to_bq_row(data: bytes) -> dict         # raises ValueError on bad schema
def ensure_stream_resources(cfg: "StreamConfig") -> None
class StreamConfig                                  # extends ingestion.config.Config:
                                                    # topic, subscription, stream dataset/table
```

## Producer (`stream_producer.py`)

Reads the Parquet in pyarrow batches, converts rows via `row_to_message`,
publishes with client-side throttling (`--rate` msg/s), stops at `--limit`.
With probability `--dup-rate` (default 0.01) a message is published twice —
deliberate duplicate injection so at-least-once handling is demonstrable.
Prints a final summary: published, duplicates injected, elapsed, effective
rate. Ctrl-C flushes pending publishes and prints the summary. Missing Parquet
→ readable hint to run `python -m ingestion.download`.

## Consumer (`stream_consumer.py`)

`streaming_pull` with flow control (max 1000 outstanding). Buffers decoded
rows up to 500 or 2 s, then `insert_rows_json(table, rows, row_ids=[trip_key...])`.
Ack only after a successful insert; on insert error the whole batch is nacked
→ redelivery (at-least-once in practice). Malformed message: log + ack +
`rejected` counter (no dead-letter, documented). SIGINT: stop pulling, flush
buffer, print summary (received / inserted / rejected / duplicates seen).
Logs in English (the Polish-strings rule applies to the chat UX, not infra).

## Verification of dedup (Task 3, live)

After a replay with `--dup-rate 0.02`:
```sql
SELECT trip_key, COUNT(*) c FROM `taxi-chat-data.stream.trips`
GROUP BY trip_key HAVING c > 1
```
Expectation: ~0 rows (insertId best-effort window catches replay-scale dups);
producer's injected-duplicate count on record for comparison. Total row count
== producer's published-unique count.

## Testing

- Unit (CI, mocked): producer against a fake publisher (message count, shape,
  dup injection accounting); consumer against fabricated messages (row
  mapping, `row_ids`, ack/nack decisions, buffer flush on size); contract
  round-trip `row_to_message` → `message_to_bq_row`; **golden trip_key test**
  against a dbt-computed value.
- `@pytest.mark.integration`: live smoke (small `--limit`) — run in Task 3.

## Task split (for the ~/.terminal-agents harness)

| Task | Executor | Coordination |
|---|---|---|
| 0 | in-session | `stream_common.py` + unit tests + `google-cloud-pubsub` dep, committed to the phase branch before spawning |
| 1: producer | agent, wave 1 | **cohort with task-2 agent** — intent-sync on contract interpretation (NULL serialization, timestamp format, dup-inject semantics) before coding; `agent-msg.sh` for contract questions instead of guessing |
| 2: consumer | agent, wave 1 | same cohort; may `agent-wait.sh --background` on peer's `pr-opened` to react (e.g. add an edge-case test) |
| 3 | in-session | live GCP: ensure resources, 100k replay, dedup verification query, runbook/README, PR |

The agents share message **semantics**, not files — the cohort/intent-sync
machinery is used for exactly that: both declare their reading of the contract
and ack each other's intents before the edit gate opens. Zero shared files
remains true (`requirements.txt` changes land in Task 0).

## Conventions (binding, as in previous phases)

- ALL code/comments/commits in English; per task a Polish learning note under
  `docs/learn/faza-4-<topic>.md` AND a feature record under
  `docs/features/faza-4-streaming-pubsub/<task-id>/README.md`
  (What was built / Files touched / Key decisions / Verification).
- No AI-attribution footers. Secrets stay out of the repo (ADC only).
- Unit tests never touch live GCP; live runs only in Task 3.
- Cost discipline: replay sample by default; streaming-insert cost note in the
  runbook; no other billable surfaces.
