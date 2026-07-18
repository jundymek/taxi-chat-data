# Faza 6: model evaluation + stream merge + Airflow — design

> Quality-and-orchestration layer over the built pipeline. Three independent
> tasks in one phase. Evaluation is the priority (the "GenAI quality
> evaluation" highlight); the other two are done solidly without inflation.

## Goal

Close the quality and orchestration layer over the existing pipeline:
1. **Model evaluation** — NL2SQL quality of `gemma4:latest` vs `llama3.1:8b` on a
   golden-truth question set → an accuracy table (interview material).
2. **stream.trips → stg_trips** — merge the Faza 4 stream into the dbt staging
   layer (UNION + dedup), closing the Faza 4 debt.
3. **Airflow DAG** — local-in-Docker Airflow orchestrating the dbt transform
   (`dbt run` → `dbt test`).

## Architecture & order

Three isolated units, each with a clear interface; ordered by dependency and
priority:

1. **Task 1 — stream merge (dbt).** First: Airflow (Task 3) runs this model, and
   evaluation (Task 2) queries marts that depend on `stg_trips`.
2. **Task 2 — evaluation (`genai/eval.py`, PRIORITY — most depth).** Independent
   of Airflow; uses the existing injectable `build_pipeline(llm=...)`.
3. **Task 3 — Airflow DAG.** Last: it orchestrates what is already built.

No changes to the merged API/frontend except one small addition in Task 2:
`GET /eval` reads the last evaluation report.

## Global constraints (project-wide)

- Code/comments/commit messages/PR titles in ENGLISH; Conventional Commits; NO
  AI footer / Co-Authored-By line.
- Polish learning note per task in `docs/learn/faza-6-<topic>.md`; BMAD story in
  `docs/tasks/` updated (Status, checkboxes, Dev Agent Record) before "done";
  feature record in `docs/features/faza-6-.../<task-id>/README.md`.
- Verify before every "done" (real output shown), never assume.
- Unit tests touch NO live services (no Ollama, no BigQuery, no real HTTP); live
  runs are separate operator steps. Python tests: `.venv/bin/pytest`.
- Models are already installed in Ollama (confirmed): `gemma4:latest` (9.6 GB),
  `llama3.1:8b` (4.9 GB), `nomic-embed-text` (0.3 GB).

---

## Task 1: stream.trips → stg_trips (dbt merge + dedup)

**Problem (verified against live BQ schemas):**
- `raw.trips` — raw NYC TLC names (`VendorID`, `tpep_pickup_datetime`,
  `PULocationID`, `DOLocationID`, `RatecodeID`), no `trip_key`.
- `stream.trips` — ALREADY processed (`vendor_id`, `pickup_datetime`,
  `pickup_location_id`, `ratecode_id`) and ALREADY has a `trip_key` (the Faza 4
  consumer computed it as the insertId for dedup).

**Critical `trip_key` consistency:** batch↔stream dedup works ONLY if both keys
are computed by the identical formula. `stg_trips` uses
`dbt_utils.generate_surrogate_key(['tpep_pickup_datetime','tpep_dropoff_datetime',
'PULocationID','DOLocationID','fare_amount','VendorID'])`. **The plan MUST verify
against the Faza 4 consumer code** that its `trip_key` used the same 6 fields by
the same method. Decision (design-locked): **recompute `trip_key` in staging
with the same macro** for the stream rows too, rather than trusting the stored
stream key — this guarantees dedup regardless of how the consumer computed it.

**Solution — `dbt/models/staging/stg_trips.sql`:**
- `raw_cleaned` CTE — current logic (rename raw TLC cols → common stg schema,
  quality filters, surrogate `trip_key`).
- `stream_cleaned` CTE — reads `source('stream','trips')`, maps its
  already-processed names onto the SAME common stg schema, recomputes `trip_key`
  with the same `generate_surrogate_key` macro, applies the same quality filters.
  Stream-only columns absent from the stg schema (`store_and_fwd_flag`, `extra`,
  `mta_tax`, …) are simply not selected; each CTE ends with an explicit SELECT of
  the shared column list so the UNION is schema-compatible.
- `unioned` — `UNION ALL` of both, then dedup by `trip_key` with a deterministic
  tie-break (`qualify row_number() over (partition by trip_key order by <stable
  cols>) = 1`), removing a trip that arrived via both paths.
- New `source('stream','trips')` declared in `sources.yml`.

**Tests (dbt):** `unique` + `not_null` on `trip_key` (proves dedup); row-count
sanity (stg count ≥ deduped-raw count, ≤ raw+stream count). Full `dbt build`
green.

---

## Task 2: model evaluation (`genai/eval.py`) — PRIORITY

**Test set (`genai/eval_questions.yml`):** ~15–20 entries, each `question` (PL) +
`reference_sql` (hand-written, reviewed correct SQL). Golden truth = the result
of executing `reference_sql` on BQ at eval time (always matches current data).
Coverage spans difficulty: simple aggregates, star-schema JOINs, time filters,
group-bys, plus 1–2 questions that SHOULD trip a guardrail (so the eval sees it).

**Module `genai/eval.py` — pure, testable units:**
- `load_questions(path) -> list[EvalCase]` — parse YAML.
- `result_sets_match(actual, expected, *, tol=1e-6) -> bool` — **the metric core,
  a pure function**: order-insensitive comparison (multiset of rows) with numeric
  tolerance (4.16 == 4.160001). Unit-tested without BQ.
- `evaluate_case(case, pipeline, bq_client) -> CaseResult` — runs `pipeline` (with
  the injected model) on the question, executes `reference_sql` for golden truth,
  compares. Returns `correct: bool`, `executed: bool`, `attempts: int`,
  `refused: bool`, `error: str | None`.
- `evaluate_model(model, cases, ...) -> ModelReport` — builds
  `build_pipeline(llm=LLMClient(model=model))`, runs all questions, aggregates.
- `run_eval(models=['gemma4:latest','llama3.1:8b']) -> EvalReport` — loop over
  models, assemble the report.

**Metric:** primary verdict = **result-set correctness %** per model; auxiliary
columns = executed %, mean attempts, guardrail-refusal count (DESIGN.md lists
these). Result-set comparison is order-insensitive with numeric tolerance.

**CLI + report:** `python -m genai.eval` → prints the table (model × correctness%
/ executed% / mean attempts / refusals) AND writes `docs/eval/latest.json` +
readable `docs/eval/latest.md`. `GET /eval` in the API reads
`docs/eval/latest.json` (small addition; it does NOT run the heavy eval on
request — 15–20 questions × 2 models = minutes + BQ scan + Ollama load).

**Unit tests (no live services):** `result_sets_match` (order, tolerance, mixed
types, non-match), `load_questions`, `evaluate_case` with a fake pipeline + fake
bq_client (same style as the API tests). Live run = separate operator step (like
the Faza 5 demo). Requires live Ollama + ADC + built warehouse.

---

## Task 3: Airflow DAG (local, orchestrates the dbt transform)

**Architecture:**
- `docker-compose.airflow.yml` (separate from any main compose) — Airflow in
  local mode: `LocalExecutor` + Postgres metadata DB (minimal standard Docker
  setup). Mounts `dags/` and `dbt/` into the container; passes ADC (read-only
  bind, the proven Faza 2 pattern) and `.env` vars.
- `dags/dbt_transform_dag.py` — one DAG `dbt_transform`:
  - `dbt_run` (`BashOperator`: `dbt run` on staging+marts, incl. the new
    stg_trips), `dbt_test` (`BashOperator`: `dbt test`), with `dbt_run >>
    dbt_test`.
  - `schedule=None` (manual/trigger — this demos orchestration, not a production
    cron); `default_args` retries=0, no email.

**ADC/BigQuery in the container:** dbt in the container needs the same
credentials as locally. Reuse the proven Faza 2 pattern (ADC bound read-only to
`/root/.config/gcloud/`); the plan verifies the in-container dbt profile targets
the right project/dataset.

**Tests:** import + structure validation WITHOUT running Airflow — the DAG file
imports without error, has the expected `dag_id`, exactly 2 tasks with the right
names, and the correct `dbt_run >> dbt_test` dependency (catches typos/cycles
without standing up a container). Live run (docker compose up → trigger →
green) = operator verification step.

**Out of scope (YAGNI):** no Cloud Composer, no production scheduling, no
ingestion/eval orchestration in this task (DESIGN.md allows extending later) —
the DAG is deliberately single-purpose: dbt run + test.

---

## Verification (per task, before "done")

- **Task 1:** `dbt build --select stg_trips+` green; `trip_key` unique/not_null
  pass (dedup proven); row counts sane vs raw/stream; a spot-check that a known
  stream trip and its batch twin collapse to one row.
- **Task 2:** `pytest` green (pure-function + fake-injection tests); one live
  `python -m genai.eval` run producing `docs/eval/latest.{json,md}` with a real
  gemma4-vs-llama3.1 table.
- **Task 3:** DAG structure test green; one live `docker compose -f
  docker-compose.airflow.yml up` → trigger `dbt_transform` → both tasks succeed.
