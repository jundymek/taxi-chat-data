# Faza 3 / Task 5: live index, e2e verification, docs, PR

## What was built
The operator-session closeout after wave-2 merged: the Chroma index was built
against live Ollama, the whole pipeline was exercised end-to-end on live
BigQuery, one e2e test was redesigned after root-cause analysis, and the phase
shipped as PR #7.

## Files touched
- `tests/test_e2e_integration.py` (UPDATE) — destructive-question test split
  in two (see Key decisions).
- `README.md` (UPDATE) — "Chat with data (Faza 3)" usage section + offer-map
  highlights.
- `data/chroma/` (generated, gitignored) — 6 schema docs + 10 few-shots.

## Key decisions
- **Test redesign instead of a symptom patch.** The original
  `test_destructive_question_is_refused` assumed gemma4 would emit `DELETE`
  and guardrails would refuse. Live evidence showed gemma4 refuses on its own,
  emitting a harmless literal SELECT — so `refused` was legitimately `False`
  and no data was ever at risk. Replaced with:
  - `test_destructive_sql_is_refused_by_guardrails` — deterministic: a fake
    LLM always emits `DELETE`; guardrails reject, retries exhaust, pipeline
    refuses (live retrieval/embeddings kept).
  - `test_destructive_question_never_executes_dml` — model-in-the-loop safety
    property: refused OR only a SELECT executed.
- **Model-level vs guardrail-level refusal** noted as a Faza 6 evaluation
  metric (which model refuses, and at which layer).

## Verification
- `.venv/bin/python -m genai.indexer` — `schema_docs: 6`, `few_shot_examples: 10`.
- `.venv/bin/pytest -m integration -v` — 5 passed live (Ollama + BigQuery).
- `.venv/bin/pytest` — 57 passed (unit, mocked).
- CLI demo (in PR #7 body): avg card tip 4.16 with a dimension JOIN, 0.048 GB
  scanned; destructive ask answered read-only.
