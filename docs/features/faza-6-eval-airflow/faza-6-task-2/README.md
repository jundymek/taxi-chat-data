# Faza 6 / Task 2: NL2SQL evaluation (gemma4 vs llama3.1) + /eval reader

## What was built
An offline evaluation harness (`genai/eval.py`) that scores our NL2SQL pipeline
per Ollama model over a golden-truth question set. For each question it runs the
existing pipeline to completion, executes a hand-verified reference SQL on
BigQuery, and compares the two result-sets — order-insensitive with numeric
tolerance — so equivalent SQL is scored on correctness, not on text. Produces a
per-model report (Trafność / Wykonane / Śr. próby / Odmowy) as Markdown + JSON.
A read-only `GET /eval` endpoint serves the last written report without ever
running the heavy eval.

Model comparison uses dependency injection over the existing factory
(`build_pipeline(llm=LLMClient(model=...))`) — no changes to the pipeline itself.
Pure logic and evaluation flow are fully unit-tested with fakes; the live run
(Ollama + BigQuery) is a separate operator step (`python -m genai.eval`).

## Files touched
- `genai/eval.py` (NEW) — dataclasses (`EvalCase`, `CaseResult`, `ModelReport`,
  `EvalReport`), pure `result_sets_match`, `load_questions`, `run_reference`,
  `evaluate_case`/`evaluate_model`/`run_eval`, `render_markdown`, CLI `main`.
- `genai/eval_questions.yml` (NEW) — 18 golden-truth questions (16 answerable +
  2 `expects_refusal`); every `reference_sql` queries `marts.*` only
  (guardrail-safe). Columns/joins verified against dbt marts models.
- `tests/test_eval.py` (NEW, 12 tests) — pure `result_sets_match` cases +
  fake-pipeline / fake-BQ injection for `evaluate_case`, refusal semantics,
  `render_markdown`, and the shipped question-set loader.
- `api/main.py` (UPDATE) — added `GET /eval` reader (reads
  `docs/eval/latest.json`; clear Polish empty-state when absent).
- `tests/test_api_chat.py` (UPDATE, +2 tests) — `/eval` absent + present states.
- `docs/eval/.gitkeep` (NEW) — tracks the report directory; the live run writes
  `latest.json` + `latest.md` here.
- `docs/learn/faza-6-eval.md` (NEW) — Polish learning note.

## Key decisions
- **Score result-sets, not SQL text** — equivalent queries (`COUNT(*)` vs
  `COUNT(1) AS n`) must both count as correct. Comparison is a multiset of rows
  (`collections.Counter`) with numeric tolerance; strings/bools compared exactly.
- **A refusal is correct iff `expects_refusal`** — declining "delete all data"
  is a pass (guardrails working); declining a legitimate question is a fail.
- **Reference SQL restricted to `marts.*`** — same datasets the guardrails allow
  (`config.ALLOWED_DATASETS`), so the golden truth runs under the pipeline's own
  rules and the eval is fair. Reference execution caps cost via
  `maximum_bytes_billed=config.MAX_SCAN_BYTES`.
- **`/eval` reads, never computes** — a full eval is minutes of two LLMs + BQ;
  HTTP must stay fast, so the heavy run is offline and the endpoint serves the
  cached report.

## Verification
- `.venv/bin/pytest tests/test_eval.py -v` — 12 passed (TDD: failed first with
  `ModuleNotFoundError: genai.eval`).
- `.venv/bin/pytest tests/test_api_chat.py -v` — 10 passed (incl. 2 new `/eval`).
- Full suite: 99 passed, 5 integration deselected.
- Live run (`python -m genai.eval`, after task-1 rebuilt `marts.*`): see
  `docs/eval/latest.md` and the PR body for the real gemma4-vs-llama3.1 table.
