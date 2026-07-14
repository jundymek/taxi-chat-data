# taxi-chat-data

A data-engineering + GenAI project: "chat with data" on NYC Taxi data.
Full design: `docs/DESIGN.md`. Current phase plan: `docs/superpowers/plans/`.

## Status
- [x] Faza 0: setup
- [ ] Faza 1: batch ingestion (Parquet → GCS → BigQuery raw)
- [ ] Faza 2: data warehouse (dbt, star schema)
- [ ] Faza 3: GenAI (RAG + NL2SQL + guardrails)
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

## Mapping to job requirements
See section 10 in `docs/DESIGN.md`.
