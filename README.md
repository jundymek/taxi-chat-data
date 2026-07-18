# taxi-chat-data

A data-engineering + GenAI project: "chat with data" on NYC Taxi data.
Full design: `docs/DESIGN.md`. Current phase plan: `docs/superpowers/plans/`.

## Status
- [x] Faza 0: setup
- [x] Faza 1: batch ingestion (Parquet → GCS → BigQuery raw)
- [x] Faza 2: data warehouse (dbt, star schema)
- [x] Faza 3: GenAI (RAG + NL2SQL + guardrails)
- [x] Faza 4: streaming (Pub/Sub)
- [x] Faza 5: FastAPI + frontend
- [ ] Faza 6: evaluation + Airflow
- [ ] Faza 7: DevSecOps

## Running (Faza 1)
1. GCP prerequisites — see the plan in `docs/superpowers/plans/`.
2. `python3 -m venv .venv && source .venv/bin/activate`
3. `pip install -r requirements.txt`
4. `cp .env.example .env` and fill in `GCP_PROJECT_ID`, `GCS_BUCKET`.
5. `python -m ingestion.download`
6. `python -m ingestion.batch_load`

## Streaming (Faza 4)

Simulated live feed over real Pub/Sub: the producer replays the local Parquet
into topic `trips-stream` (throttled, with deliberate duplicate injection),
the consumer streams rows into BigQuery `stream.trips`.

1. One-time: enable the API and create resources (idempotent):
   `gcloud services enable pubsub.googleapis.com` and
   `.venv/bin/python -c "from ingestion.stream_common import *; ensure_stream_resources(load_stream_config())"`
2. Terminal A: `.venv/bin/python -m ingestion.stream_consumer`
3. Terminal B: `.venv/bin/python -m ingestion.stream_producer --limit 100000 --rate 500 --dup-rate 0.02`

At-least-once semantics: ack only after a successful insert, nack → Pub/Sub
redelivery, and BigQuery `insertId` (= dbt-compatible `trip_key`) deduplicates.
Verify:

```sql
SELECT COUNT(*) total, COUNT(DISTINCT trip_key) uniq
FROM `taxi-chat-data.stream.trips`
```

Cost note: streaming inserts are billable (~$0.05/GB) — the default 100k
sample costs under a cent; Pub/Sub itself stays within the free tier.
`stream.trips` merges into the dbt staging layer in Faza 6.

## Chat with data (Faza 3)

Ask the warehouse questions in Polish, answered by a local LLM (zero API cost):

1. Prerequisites: Ollama running (`gemma4:latest`, `nomic-embed-text:latest`),
   ADC configured, Faza 2 warehouse built.
2. Build the schema index (re-run after dbt schema changes):
   `.venv/bin/python -m genai.indexer`
3. Ask: `.venv/bin/python -m genai.ask "Jaki był średni napiwek przy płatności kartą?"`
   — prints the Polish answer, the SQL used, and gigabytes scanned.

Flow: RAG over dbt model descriptions + curated few-shots (Chroma) → gemma4
generates BigQuery SQL → **guardrails validate before execution** (sqlglot AST
parse, SELECT-only, dataset allowlist `staging`/`marts`, enforced `LIMIT`,
BigQuery dry-run scan gate 1 GB) → execution capped by `maximum_bytes_billed`
→ gemma4 summarizes in Polish. Orchestrated as a LangGraph state graph with a
validate→regenerate retry cycle (max 3 attempts, then graceful refusal).

Tests: `pytest` (unit, mocked); `pytest -m integration` (live Ollama + BigQuery).

## Chat UI (Faza 5)

A single-screen web app over the Faza 3 pipeline: `POST /chat` streams each
pipeline stage over **SSE** (a FastAPI adapter around LangGraph `stream()` — no
`genai/` changes), `GET /health` reports Ollama/BigQuery/Chroma status, and a
Vite + React + TypeScript SPA (owner-approved mockup C1, "Linia M") renders the
live stage timeline — including red **ODRZUCONE** guardrail rejections — then
the answer, SQL, rows and GB scanned. The SSE frame contract is
`api/schemas.py` (mirrored 1:1 in `frontend/src/types.ts`).

1. Prerequisites: the Faza 3 stack (Ollama, ADC, `.venv/bin/python -m
   genai.indexer` if `data/chroma/` is missing).
2. Build the frontend and serve everything on one port:
   ```bash
   cd frontend && pnpm install && pnpm run build && cd ..
   .venv/bin/uvicorn api.main:app --port 8000
   ```
3. Open `http://localhost:8000` — the API serves `frontend/dist` statically, so
   the whole app lives on `:8000`. Ask a question and watch the stages stream.

Dev mode (hot reload, Vite proxies `/chat` + `/health` to `:8000`):
`cd frontend && pnpm dev` alongside the uvicorn process.

Tests: `.venv/bin/pytest` (API SSE frame sequences incl. retry/refusal/error,
no live services); `cd frontend && pnpm test` (parser chunking, hook stream
lifecycle, C1 components).

## Mapping to job requirements
See section 10 in `docs/DESIGN.md`. Faza 3 highlights: NL2SQL + risk mitigation
→ `genai/guardrails.py` + pipeline retry; RAG + vector DB → `genai/indexer.py`,
`genai/retriever.py` + Chroma; GenAI quality evaluation → Faza 6.
