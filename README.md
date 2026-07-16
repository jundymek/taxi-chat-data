# taxi-chat-data

A data-engineering + GenAI project: "chat with data" on NYC Taxi data.
Full design: `docs/DESIGN.md`. Current phase plan: `docs/superpowers/plans/`.

## Status
- [x] Faza 0: setup
- [x] Faza 1: batch ingestion (Parquet → GCS → BigQuery raw)
- [x] Faza 2: data warehouse (dbt, star schema)
- [x] Faza 3: GenAI (RAG + NL2SQL + guardrails)
- [ ] Faza 4: streaming (Pub/Sub)
- [ ] Faza 5: FastAPI + frontend
- [ ] Faza 6: evaluation + Airflow
- [ ] Faza 7: DevSecOps

## Running (Faza 1)
1. GCP prerequisites — see the plan in `docs/superpowers/plans/`.
2. `python3 -m venv .venv && source .venv/bin/activate`
3. `pip install -r requirements.txt`
4. `cp .env.example .env` and fill in `GCP_PROJECT_ID`, `GCS_BUCKET`.
5. `python -m ingestion.download`
6. `python -m ingestion.batch_load`

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

## Mapping to job requirements
See section 10 in `docs/DESIGN.md`. Faza 3 highlights: NL2SQL + risk mitigation
→ `genai/guardrails.py` + pipeline retry; RAG + vector DB → `genai/indexer.py`,
`genai/retriever.py` + Chroma; GenAI quality evaluation → Faza 6.
