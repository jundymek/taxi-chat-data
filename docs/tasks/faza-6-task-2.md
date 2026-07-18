# Faza 6 / Task 2: NL2SQL evaluation (gemma4 vs llama3.1) + /eval reader

Status: done
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
- [x] Failing tests for `result_sets_match` (pure core)
- [x] Implement dataclasses + `result_sets_match` + `load_questions`
- [x] Failing tests for `evaluate_case` with fakes → implement eval functions
- [x] Write `eval_questions.yml` (18, marts-only, incl. 2 refusals)
- [x] `GET /eval` reader + API test
- [x] Live `python -m genai.eval` → report artifacts
- [x] Polish note + feature record + this story close-out
- [x] PR

## Notes
- Model injection uses the existing `build_pipeline(llm=LLMClient(model=...))`.
- No changes to `genai/pipeline.py`/`guardrails.py`/`nl2sql.py`. Do NOT edit
  `requirements.txt` (PyYAML already present). Live run needs Ollama (gemma4 +
  llama3.1) + ADC + the warehouse rebuilt from task-1.

## Dev Agent Record
### Agent Model Used
Claude Opus 4.8 (1M context) — autonomous mode.

### Debug Log References
- Live-run prerequisite: the pipeline's retriever needs the Chroma index, which
  is per-worktree and gitignored. Built it in-worktree with
  `python -m genai.indexer` (schema_docs: 6, few_shot_examples: 10) before the
  eval run. Ollama 0.20.7 up with `gemma4:latest` + `llama3.1:8b`; BigQuery via
  ADC (dry-run OK). Live eval produced 0 reference-SQL errors across all 18
  questions × 2 models.
- Cohort intent-sync with pamela (task-3) completed before any code; upstream
  `alice:done` (task-1 PR #14 merged) gated only the live run, then merged into
  this branch.

### Completion Notes
- Implemented `genai/eval.py` with all required public names (AC #1), pure
  `result_sets_match` (order-insensitive + numeric tolerance, AC #2), 18-question
  `eval_questions.yml` (marts-only, 2 refusals, AC #3), read-only `GET /eval`
  (AC #5). Full suite green: 100 passed, 5 integration deselected (AC #4).
- **Deviation from plan (Codex review P1, DECISIONS D6):** `result_sets_match`
  compares result values in column order and IGNORES column names/aliases
  (requires equal column count), instead of the plan's column-name-set matching.
  A model's bare `COUNT(*)` (BigQuery `f0_`) would otherwise falsely score wrong
  vs the reference's `... AS n`. This matches the task's stated goal ("score
  results, not SQL text") and standard execution-accuracy semantics; AC #2 is
  silent on column names. The plan's `test_rejects_different_columns` was
  replaced with `test_ignores_column_aliases_when_values_match` +
  `test_rejects_different_column_count`.
- **Codex review P2:** report files are written atomically (temp + `os.replace`)
  so a concurrent `GET /eval` never reads a half-written `latest.json`.
- Live run (AC #6): gemma4:latest 67% correct / 94% executed / 1.44 attempts /
  1 refusal; llama3.1:8b 61% / 78% / 1.50 / 4 refusals. Honest finding: the two
  `expects_refusal` cases were NOT refused — both models reformulate destructive
  prompts into benign marts SELECTs rather than refusing, so they scored
  incorrect. The eval correctly reflects this (no code defect).
- No changes to `genai/pipeline.py`/`guardrails.py`/`nl2sql.py`/`config.py`;
  `requirements.txt` untouched (PyYAML already present). Zero file overlap with
  cohort peer pamela.

### File List
- `genai/eval.py` (NEW)
- `genai/eval_questions.yml` (NEW)
- `tests/test_eval.py` (NEW)
- `api/main.py` (UPDATE — added `GET /eval` reader)
- `tests/test_api_chat.py` (UPDATE — +2 `/eval` tests)
- `docs/eval/.gitkeep` (NEW) + `docs/eval/latest.json` + `docs/eval/latest.md` (NEW, from live run)
- `docs/learn/faza-6-eval.md` (NEW)
- `docs/features/faza-6-eval-airflow/faza-6-task-2/README.md` (NEW)
- `docs/tasks/faza-6-task-2.md` (UPDATE — this close-out)
