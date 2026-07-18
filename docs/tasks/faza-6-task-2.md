# Faza 6 / Task 2: NL2SQL evaluation (gemma4 vs llama3.1) + /eval reader

Status: planned
Executor: agent (wave 2, cohort with faza-6-task-3 — parallel, no file overlap)
Plan: `docs/superpowers/plans/2026-07-18-faza-6-eval-airflow-stream-merge.md` →
section "Task 2" (technical source of truth — complete code + TDD steps; read it
AND "Global Constraints" first).
Spec: `docs/superpowers/specs/2026-07-18-faza-6-eval-airflow-stream-merge-design.md`.

## Dependencies
- **Upstream: faza-6-task-1 MUST be merged first** — the eval's `reference_sql`
  queries `marts.*`, which rebuilds from the merged `stg_trips`. Configure with
  `set-depends-on.sh` and do not start coding the live run until task-1 lands.
- **Cohort peer: faza-6-task-3** (Airflow). No file overlap: this task owns
  `genai/`, `tests/test_eval.py`, `api/main.py`, `docs/eval/`; task-3 owns
  `dags/`, `docker-compose.airflow.yml`, `tests/test_dbt_transform_dag.py`.
  Coordinate only if both touch shared docs. Run `set-cohort.sh faza-6-task-3`.

## Acceptance Criteria
1. `genai/eval.py` with the plan's exact public names: `EvalCase`, `CaseResult`,
   `ModelReport`, `EvalReport`, `load_questions`, `result_sets_match`,
   `run_reference`, `evaluate_case`, `evaluate_model`, `run_eval`,
   `render_markdown`, `main`.
2. `result_sets_match` is order-insensitive with numeric tolerance (pure,
   unit-tested without BQ). `evaluate_case` runs the injected pipeline to
   completion, executes `reference_sql` for golden truth, returns
   correct/executed/attempts/refused/error; a refusal is correct iff
   `expects_refusal`.
3. `genai/eval_questions.yml` — ≥15 questions, every `reference_sql` inside
   guardrail-allowed datasets (`marts.*`/`staging.*`, never raw/stream), incl.
   1-2 `expects_refusal: true` cases.
4. `.venv/bin/pytest tests/test_eval.py -v` → all PASS (pure-function +
   fake-pipeline/fake-BQ injection); full suite stays green.
5. `GET /eval` in `api/main.py` reads `docs/eval/latest.json` (never runs the
   heavy eval); one API test added and passing.
6. One live `python -m genai.eval` run producing `docs/eval/latest.{json,md}`
   with a real gemma4-vs-llama3.1 table (capture for the PR).
7. `docs/learn/faza-6-eval.md` (Polish) + feature record written.
8. THIS story updated before PR (Status: done, checkboxes, Dev Agent Record).

## Tasks / Subtasks
- [ ] Failing tests for `result_sets_match` (pure core)
- [ ] Implement dataclasses + `result_sets_match` + `load_questions`
- [ ] Failing tests for `evaluate_case` with fakes → implement eval functions
- [ ] Write `eval_questions.yml` (≥15, marts-only, incl. refusals)
- [ ] `GET /eval` reader + API test
- [ ] Live `python -m genai.eval` → report artifacts
- [ ] Polish note + feature record + this story close-out
- [ ] PR

## Notes
- Model injection uses the existing `build_pipeline(llm=LLMClient(model=...))`.
- No changes to `genai/pipeline.py`/`guardrails.py`/`nl2sql.py`. Do NOT edit
  `requirements.txt` (PyYAML already present). Live run needs Ollama (gemma4 +
  llama3.1) + ADC + the warehouse rebuilt from task-1.

## Dev Agent Record
### Agent Model Used
### Completion Notes
### File List
