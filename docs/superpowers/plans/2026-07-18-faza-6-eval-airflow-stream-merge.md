# Faza 6: eval + stream merge + Airflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the quality-and-orchestration layer over the built pipeline: merge
the Faza 4 stream into `stg_trips`, evaluate gemma4 vs llama3.1 NL2SQL quality
into a report, and orchestrate the dbt transform with a local Airflow DAG.

**Architecture:** Task 1 is a pure dbt change (`stg_trips.sql` + a new source).
Task 2 is a new `genai/eval.py` module of pure, injectable units plus a CLI and a
`GET /eval` reader. Task 3 is a single Airflow DAG in `dags/` with a Docker
compose file, tested by structure-import (no live Airflow).

**Tech Stack:** dbt + BigQuery (Task 1); Python 3.14 in the existing `.venv`,
pytest, PyYAML, the existing `genai` package + `build_pipeline(llm=...)` (Task 2);
Apache Airflow in Docker, `BashOperator`, LocalExecutor + Postgres (Task 3).

## Global Constraints

- Code/comments/commit messages/PR titles in ENGLISH; Conventional Commits; NO
  AI footer / Co-Authored-By line. UI/report copy may be Polish.
- Per task: Polish learning note `docs/learn/faza-6-<topic>.md` + feature record
  `docs/features/faza-6-eval-airflow/<task-id>/README.md` + BMAD story in
  `docs/tasks/faza-6-task-N.md` updated (Status, checkboxes, Dev Agent Record)
  before "done".
- Verify before every "done" with real output; never assume.
- Unit tests touch NO live services (no Ollama, no BigQuery, no real HTTP). Live
  runs (dbt build, `python -m genai.eval`, docker compose) are separate operator
  steps. Python tests: `.venv/bin/pytest`.
- Guardrails allow only datasets `staging`/`marts` (`config.ALLOWED_DATASETS`);
  every eval `reference_sql` MUST query `marts.*` (or `staging.*`), never `raw`/
  `stream`, so the reference runs under the same rules as the pipeline.
- Models already installed in Ollama: `gemma4:latest`, `llama3.1:8b`,
  `nomic-embed-text`. `config.GENERATION_MODEL = "gemma4:latest"`.

---

## File Structure

```
dbt/models/staging/
├── _staging__sources.yml     # Task 1 — add `stream` source
├── stg_trips.sql             # Task 1 — UNION raw+stream, recompute key, dedup
└── _staging__models.yml      # Task 1 — (already tests trip_key unique/not_null)
genai/
├── eval.py                   # Task 2 — load_questions, result_sets_match,
│                             #          evaluate_case, evaluate_model, run_eval, CLI
└── eval_questions.yml        # Task 2 — ~15-20 questions + reference_sql
api/main.py                   # Task 2 — add GET /eval (reads docs/eval/latest.json)
docs/eval/                    # Task 2 — latest.json + latest.md (git-tracked dir)
tests/
├── test_eval.py              # Task 2 — pure-function + fake-injection tests
└── test_dbt_transform_dag.py # Task 3 — DAG structure import test
dags/
└── dbt_transform_dag.py      # Task 3 — dbt_run >> dbt_test
docker-compose.airflow.yml    # Task 3 — Airflow LocalExecutor + Postgres
```

---

## Task 1: stream.trips → stg_trips (dbt UNION + dedup)

**Files:**
- Modify: `dbt/models/staging/_staging__sources.yml` (add `stream` source)
- Modify: `dbt/models/staging/stg_trips.sql` (UNION raw + stream, recompute key)
- Verify: `dbt/models/staging/_staging__models.yml` (trip_key unique/not_null test
  already present — confirm it still applies)

**Interfaces:**
- Consumes: `source('raw','trips')` (raw TLC schema: `VendorID`,
  `tpep_pickup_datetime`, `tpep_dropoff_datetime`, `PULocationID`, `DOLocationID`,
  `RatecodeID`, `payment_type`, `fare_amount`, …) and the NEW `source('stream',
  'trips')` (already-processed schema: `vendor_id`, `pickup_datetime`,
  `dropoff_datetime`, `pickup_location_id`, `dropoff_location_id`, `ratecode_id`,
  `payment_type`, `fare_amount`, …, plus a stored `trip_key`).
- Produces: `stg_trips` view with the SAME output columns as today (`trip_key`,
  `vendor_id`, `pickup_datetime`, `dropoff_datetime`, `pickup_date`,
  `trip_duration_min`, `passenger_count`, `trip_distance`, `ratecode_id`,
  `pickup_location_id`, `dropoff_location_id`, `payment_type`, `fare_amount`,
  `tip_amount`, `tolls_amount`, `total_amount`), now covering raw+stream deduped.

**Context — `trip_key` consistency (verified, not assumed):** the Faza 4 consumer
(`ingestion/stream_common.py:29-35,73-75`) computes `trip_key` as
`md5("-".join(...))` over the SAME 6 fields in the SAME order as
`stg_trips`'s `dbt_utils.generate_surrogate_key(['tpep_pickup_datetime',
'tpep_dropoff_datetime','PULocationID','DOLocationID','fare_amount','VendorID'])`,
with the same null sentinel. So the stored stream key already matches. We still
**recompute** the key in staging from the stream's columns with the same macro —
one source of truth, immune to any future consumer drift.

- [ ] **Step 1: Add the `stream` source**

Edit `dbt/models/staging/_staging__sources.yml` to append a second source:
```yaml
version: 2

sources:
  - name: raw
    database: taxi-chat-data
    schema: raw
    tables:
      - name: trips
        description: "Raw NYC Taxi trips loaded from Parquet in Faza 1 (untransformed)."
  - name: stream
    database: taxi-chat-data
    schema: stream
    tables:
      - name: trips
        description: "Simulated live trips streamed via Pub/Sub in Faza 4 (already renamed/typed, carries trip_key)."
```

- [ ] **Step 2: Rewrite `stg_trips.sql` to UNION raw + stream and dedup**

Replace `dbt/models/staging/stg_trips.sql` with (the `raw_cleaned` CTE is the
existing `cleaned` logic verbatim; `stream_cleaned` mirrors it over the stream's
already-renamed columns and recomputes the key; `unioned` + `deduped` collapse
duplicates across both paths):
```sql
{{ config(materialized='view') }}

with raw_source as (
    select * from {{ source('raw', 'trips') }}
),

raw_cleaned as (
    select
        {{ dbt_utils.generate_surrogate_key([
            'tpep_pickup_datetime',
            'tpep_dropoff_datetime',
            'PULocationID',
            'DOLocationID',
            'fare_amount',
            'VendorID'
        ]) }}                                              as trip_key,
        VendorID                                           as vendor_id,
        tpep_pickup_datetime                               as pickup_datetime,
        tpep_dropoff_datetime                              as dropoff_datetime,
        date(tpep_pickup_datetime)                         as pickup_date,
        timestamp_diff(
            tpep_dropoff_datetime, tpep_pickup_datetime, minute
        )                                                  as trip_duration_min,
        cast(passenger_count as int64)                     as passenger_count,
        trip_distance                                      as trip_distance,
        cast(RatecodeID as int64)                          as ratecode_id,
        PULocationID                                       as pickup_location_id,
        DOLocationID                                       as dropoff_location_id,
        payment_type                                       as payment_type,
        fare_amount                                        as fare_amount,
        tip_amount                                         as tip_amount,
        tolls_amount                                       as tolls_amount,
        total_amount                                       as total_amount
    from raw_source
    where fare_amount >= 0
      and total_amount >= 0
      and trip_distance > 0
      and tpep_dropoff_datetime >= tpep_pickup_datetime
      and date(tpep_pickup_datetime) >= '2009-01-01'
      and tpep_pickup_datetime <= current_timestamp()
),

stream_source as (
    select * from {{ source('stream', 'trips') }}
),

stream_cleaned as (
    select
        -- Recompute the key from the stream's columns with the SAME recipe as
        -- raw_cleaned, so a trip that arrived via both paths dedups to one row.
        {{ dbt_utils.generate_surrogate_key([
            'pickup_datetime',
            'dropoff_datetime',
            'pickup_location_id',
            'dropoff_location_id',
            'fare_amount',
            'vendor_id'
        ]) }}                                              as trip_key,
        vendor_id                                          as vendor_id,
        pickup_datetime                                    as pickup_datetime,
        dropoff_datetime                                   as dropoff_datetime,
        date(pickup_datetime)                              as pickup_date,
        timestamp_diff(
            dropoff_datetime, pickup_datetime, minute
        )                                                  as trip_duration_min,
        cast(passenger_count as int64)                     as passenger_count,
        trip_distance                                      as trip_distance,
        cast(ratecode_id as int64)                         as ratecode_id,
        pickup_location_id                                 as pickup_location_id,
        dropoff_location_id                                as dropoff_location_id,
        payment_type                                       as payment_type,
        fare_amount                                        as fare_amount,
        tip_amount                                         as tip_amount,
        tolls_amount                                       as tolls_amount,
        total_amount                                       as total_amount
    from stream_source
    where fare_amount >= 0
      and total_amount >= 0
      and trip_distance > 0
      and dropoff_datetime >= pickup_datetime
      and date(pickup_datetime) >= '2009-01-01'
      and pickup_datetime <= current_timestamp()
),

unioned as (
    select * from raw_cleaned
    union all
    select * from stream_cleaned
),

deduped as (
    select *
    from unioned
    qualify row_number() over (
        partition by trip_key order by pickup_datetime
    ) = 1
)

select * from deduped
```

- [ ] **Step 3: Confirm the existing trip_key tests still bind**

Open `dbt/models/staging/_staging__models.yml` and confirm `stg_trips.trip_key`
still has `unique` + `not_null` tests (they existed pre-Faza-6). No edit needed
if present; if the model block is missing them, add:
```yaml
      - name: trip_key
        tests:
          - unique
          - not_null
```

- [ ] **Step 4: Build and test against live BigQuery (operator step)**

Run:
```bash
cd dbt && dbt build --select stg_trips
```
Expected: `stg_trips` view builds; `unique_stg_trips_trip_key` and
`not_null_stg_trips_trip_key` PASS (dedup across raw+stream proven).

Row-count sanity (operator):
```bash
bq query --use_legacy_sql=false \
  'SELECT COUNT(*) AS n, COUNT(DISTINCT trip_key) AS uniq FROM `taxi-chat-data.staging.stg_trips`'
```
Expected: `n == uniq` (fully deduped); `n` ≥ the pre-Faza-6 count (stream rows
that were not already in raw are added).

- [ ] **Step 5: Polish learning note + records**

Write `docs/learn/faza-6-stream-merge.md` (po polsku, ~60-100 linii): czemu
stream i batch scalamy w warstwie staging, nie mart; jak `generate_surrogate_key`
daje deterministyczny klucz i czemu przeliczamy go po stronie stg zamiast ufać
kluczowi ze streamu; jak `qualify row_number()` deduplikuje przejazd, który
trafił obiema drogami; czemu `union all` + dedup zamiast `union distinct`.
Write `docs/features/faza-6-eval-airflow/faza-6-task-1/README.md` (What / Files /
Key decisions / Verification) and update `docs/tasks/faza-6-task-1.md`.

- [ ] **Step 6: Commit**

```bash
git add dbt/models/staging/ docs/learn/faza-6-stream-merge.md \
        docs/features/faza-6-eval-airflow/faza-6-task-1/ docs/tasks/faza-6-task-1.md
git commit -m "feat(faza-6-task-1): merge stream.trips into stg_trips (UNION + trip_key dedup)"
```

---

## Task 2: model evaluation (`genai/eval.py`) — PRIORITY

**Files:**
- Create: `genai/eval.py`
- Create: `genai/eval_questions.yml`
- Create: `tests/test_eval.py`
- Create: `docs/eval/.gitkeep` (so the report dir is tracked)
- Modify: `api/main.py` (add `GET /eval`)
- Test: `tests/test_api_chat.py` (add one `/eval` test)

**Interfaces:**
- Consumes: `genai.pipeline.build_pipeline(llm=...)`, `genai.llm_client.LLMClient`
  (ctor `LLMClient(model=..., base_url=..., timeout=...)`), `genai.config`
  (`GENERATION_MODEL`, `BQ_PROJECT`). A pipeline object exposes
  `.stream({"question": q}, stream_mode="updates")` yielding `{node: patch}`
  dicts — but for eval we run it to completion and read the final state's
  `rows`/`refused`/`attempts`; see `evaluate_case` below for the exact accessor.
- Produces (exact names later steps + tests rely on):
  - `class EvalCase` (dataclass): `question: str`, `reference_sql: str`,
    `expects_refusal: bool = False`.
  - `class CaseResult` (dataclass): `question: str`, `correct: bool`,
    `executed: bool`, `attempts: int`, `refused: bool`, `error: str | None`.
  - `class ModelReport` (dataclass): `model: str`, `cases: list[CaseResult]`,
    and computed props `correct_pct: float`, `executed_pct: float`,
    `mean_attempts: float`, `refusals: int`.
  - `class EvalReport` (dataclass): `models: list[ModelReport]`,
    `question_count: int`.
  - `def load_questions(path: str | Path) -> list[EvalCase]`
  - `def result_sets_match(actual: list[dict], expected: list[dict], *,
    tol: float = 1e-6) -> bool`
  - `def run_reference(reference_sql: str, bq_client) -> list[dict]`
  - `def evaluate_case(case: EvalCase, pipeline, bq_client) -> CaseResult`
  - `def evaluate_model(model: str, cases: list[EvalCase], *, pipeline_factory,
    bq_client) -> ModelReport`
  - `def run_eval(models: list[str] | None = None) -> EvalReport`
  - `def render_markdown(report: EvalReport) -> str`
  - `def main() -> None` (CLI entry: run, print table, write reports)

- [ ] **Step 1: Write failing tests for the pure core (`result_sets_match`)**

Create `tests/test_eval.py`:
```python
from genai.eval import (
    EvalCase, CaseResult, ModelReport,
    load_questions, result_sets_match, evaluate_case, render_markdown,
)


def test_matches_same_rows_regardless_of_order():
    a = [{"c": 1}, {"c": 2}]
    b = [{"c": 2}, {"c": 1}]
    assert result_sets_match(a, b) is True


def test_matches_within_numeric_tolerance():
    assert result_sets_match([{"avg": 4.16}], [{"avg": 4.160000001}]) is True


def test_rejects_different_values():
    assert result_sets_match([{"avg": 4.16}], [{"avg": 9.99}]) is False


def test_rejects_different_row_count():
    assert result_sets_match([{"c": 1}], [{"c": 1}, {"c": 2}]) is False


def test_rejects_different_columns():
    assert result_sets_match([{"a": 1}], [{"b": 1}]) is False


def test_matches_multi_column_rows_order_insensitive():
    a = [{"zone": "Manhattan", "n": 10}, {"zone": "Queens", "n": 3}]
    b = [{"zone": "Queens", "n": 3}, {"zone": "Manhattan", "n": 10}]
    assert result_sets_match(a, b) is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_eval.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'genai.eval'`.

- [ ] **Step 3: Implement dataclasses + `result_sets_match` + `load_questions`**

Create `genai/eval.py`:
```python
"""NL2SQL quality evaluation: run the pipeline per model over golden-truth
questions and score result-set correctness. Pure units are unit-tested; the
live run (Ollama + BigQuery) is an operator step via `python -m genai.eval`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from math import isclose
from pathlib import Path

import yaml

from genai import config


@dataclass
class EvalCase:
    question: str
    reference_sql: str
    expects_refusal: bool = False


@dataclass
class CaseResult:
    question: str
    correct: bool
    executed: bool
    attempts: int
    refused: bool
    error: str | None = None


@dataclass
class ModelReport:
    model: str
    cases: list[CaseResult] = field(default_factory=list)

    @property
    def correct_pct(self) -> float:
        return 100.0 * sum(c.correct for c in self.cases) / len(self.cases) if self.cases else 0.0

    @property
    def executed_pct(self) -> float:
        return 100.0 * sum(c.executed for c in self.cases) / len(self.cases) if self.cases else 0.0

    @property
    def mean_attempts(self) -> float:
        return sum(c.attempts for c in self.cases) / len(self.cases) if self.cases else 0.0

    @property
    def refusals(self) -> int:
        return sum(c.refused for c in self.cases)


@dataclass
class EvalReport:
    models: list[ModelReport]
    question_count: int


def load_questions(path: str | Path = None) -> list[EvalCase]:
    path = Path(path) if path else Path(__file__).with_name("eval_questions.yml")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    return [
        EvalCase(
            question=item["question"],
            reference_sql=item["reference_sql"],
            expects_refusal=bool(item.get("expects_refusal", False)),
        )
        for item in raw
    ]


def _cell_matches(a, b, tol: float) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return isclose(float(a), float(b), rel_tol=0.0, abs_tol=tol)
    return a == b


def _row_key(row: dict, tol: float):
    # Rows are compared as multisets; make a hashable, tolerance-rounded key.
    def norm(v):
        if isinstance(v, bool):
            return v
        if isinstance(v, (int, float)):
            return round(float(v) / tol) if tol else float(v)
        return v
    return tuple(sorted((k, norm(v)) for k, v in row.items()))


def result_sets_match(actual: list[dict], expected: list[dict], *, tol: float = 1e-6) -> bool:
    from collections import Counter
    if len(actual) != len(expected):
        return False
    if not actual:
        return True
    # Same column set required (compare the first row of each — BQ result rows
    # are uniform).
    if set(actual[0].keys()) != set(expected[0].keys()):
        return False
    return Counter(_row_key(r, tol) for r in actual) == Counter(_row_key(r, tol) for r in expected)
```

- [ ] **Step 4: Run tests to verify the pure core passes**

Run: `.venv/bin/pytest tests/test_eval.py -k result_sets -v`
Expected: all `result_sets_match` tests PASS.

- [ ] **Step 5: Write failing tests for `evaluate_case` with fakes**

Append to `tests/test_eval.py` (fakes mirror the style of `tests/test_pipeline.py`):
```python
class FakePipeline:
    """Runs to completion over stream_mode='updates', like LangGraph."""

    def __init__(self, updates):
        self._updates = updates

    def stream(self, state, stream_mode="updates"):
        assert stream_mode == "updates"
        yield from self._updates


class FakeBQ:
    """Returns queued result-sets per SQL string in call order."""

    def __init__(self, results):
        self._results = list(results)
        self.queries = []

    def query(self, sql, **kwargs):
        self.queries.append(sql)
        rows = self._results.pop(0)
        return _FakeJob(rows)


class _FakeJob:
    def __init__(self, rows):
        self._rows = rows

    def result(self):
        return [_FakeRow(r) for r in self._rows]


class _FakeRow:
    def __init__(self, d):
        self._d = d

    def items(self):
        return self._d.items()


HAPPY_UPDATES = [
    {"retrieve": {"context": None, "attempts": 0, "refused": False, "rows": []}},
    {"generate_sql": {"sql": "SELECT AVG(tip_amount) AS avg FROM `taxi-chat-data.marts.fct_trips`", "attempts": 1}},
    {"validate": {"validation": None}},
    {"execute": {"rows": [{"avg": 4.16}], "scanned_bytes": 1000, "sql": "SELECT 1"}},
    {"summarize": {"answer": "4,16"}},
]


def test_evaluate_case_correct_when_result_matches_reference():
    case = EvalCase(question="Średni napiwek?", reference_sql="SELECT AVG(tip_amount) AS avg FROM `taxi-chat-data.marts.fct_trips`")
    pipeline = FakePipeline(HAPPY_UPDATES)
    bq = FakeBQ([[{"avg": 4.160000002}]])  # reference execution
    result = evaluate_case(case, pipeline, bq)
    assert result.correct is True
    assert result.executed is True
    assert result.refused is False
    assert result.attempts == 1


def test_evaluate_case_incorrect_when_results_differ():
    case = EvalCase(question="q", reference_sql="SELECT 1")
    pipeline = FakePipeline(HAPPY_UPDATES)
    bq = FakeBQ([[{"avg": 9.99}]])
    result = evaluate_case(case, pipeline, bq)
    assert result.correct is False
    assert result.executed is True


REFUSAL_UPDATES = [
    {"retrieve": {"context": None, "attempts": 0, "refused": False, "rows": []}},
    {"generate_sql": {"sql": "DROP TABLE x", "attempts": 3}},
    {"validate": {"validation": None}},
    {"refuse": {"refused": True, "answer": "Nie umiem."}},
]


def test_evaluate_case_counts_refusal_and_is_correct_when_expected():
    case = EvalCase(question="Usuń dane", reference_sql="SELECT 1", expects_refusal=True)
    pipeline = FakePipeline(REFUSAL_UPDATES)
    bq = FakeBQ([])  # reference never executed on an expected refusal
    result = evaluate_case(case, pipeline, bq)
    assert result.refused is True
    assert result.correct is True   # a refusal we asked for counts as correct
    assert result.executed is False


def test_render_markdown_has_a_row_per_model():
    report = _two_model_report()
    md = render_markdown(report)
    assert "gemma4:latest" in md and "llama3.1:8b" in md
    assert "%" in md


def _two_model_report():
    from genai.eval import EvalReport
    g = ModelReport("gemma4:latest", [CaseResult("q", True, True, 1, False, None)])
    l = ModelReport("llama3.1:8b", [CaseResult("q", False, True, 2, False, None)])
    return EvalReport([g, l], question_count=1)
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_eval.py -k "evaluate_case or render" -v`
Expected: FAIL — `evaluate_case`/`render_markdown` not defined.

- [ ] **Step 7: Implement `evaluate_case`, `evaluate_model`, `run_eval`, `render_markdown`, `main`**

Append to `genai/eval.py`:
```python
def _rows_from_job(job) -> list[dict]:
    return [dict(row.items()) for row in job.result()]


def run_reference(reference_sql: str, bq_client) -> list[dict]:
    from google.cloud.bigquery import QueryJobConfig
    job = bq_client.query(
        reference_sql,
        job_config=QueryJobConfig(maximum_bytes_billed=config.MAX_SCAN_BYTES),
    )
    return _rows_from_job(job)


def _run_pipeline(pipeline, question: str) -> dict:
    """Drive the pipeline to completion; return the accumulated final state."""
    state: dict = {"question": question}
    for update in pipeline.stream({"question": question}, stream_mode="updates"):
        for _node, patch in update.items():
            state.update(patch or {})
    return state


def evaluate_case(case: EvalCase, pipeline, bq_client) -> CaseResult:
    try:
        state = _run_pipeline(pipeline, case.question)
    except Exception as exc:  # a pipeline blow-up is a failed case, not a crash
        return CaseResult(case.question, correct=False, executed=False,
                          attempts=0, refused=False, error=str(exc))

    refused = bool(state.get("refused", False))
    attempts = int(state.get("attempts", 0))

    if refused:
        # A refusal is correct iff we expected one for this question.
        return CaseResult(case.question, correct=case.expects_refusal, executed=False,
                          attempts=attempts, refused=True, error=None)

    rows = state.get("rows", [])
    try:
        expected = run_reference(case.reference_sql, bq_client)
    except Exception as exc:
        return CaseResult(case.question, correct=False, executed=True,
                          attempts=attempts, refused=False,
                          error=f"reference SQL failed: {exc}")

    correct = (not case.expects_refusal) and result_sets_match(rows, expected)
    return CaseResult(case.question, correct=correct, executed=True,
                      attempts=attempts, refused=False, error=None)


def evaluate_model(model: str, cases: list[EvalCase], *, pipeline_factory, bq_client) -> ModelReport:
    pipeline = pipeline_factory(model)
    results = [evaluate_case(c, pipeline, bq_client) for c in cases]
    return ModelReport(model=model, cases=results)


def _default_pipeline_factory(model: str):
    from genai.llm_client import LLMClient
    from genai.pipeline import build_pipeline
    return build_pipeline(llm=LLMClient(model=model))


def run_eval(models: list[str] | None = None) -> EvalReport:
    from google.cloud import bigquery
    models = models or [config.GENERATION_MODEL, "llama3.1:8b"]
    cases = load_questions()
    bq_client = bigquery.Client(project=config.BQ_PROJECT)
    reports = [
        evaluate_model(m, cases, pipeline_factory=_default_pipeline_factory, bq_client=bq_client)
        for m in models
    ]
    return EvalReport(models=reports, question_count=len(cases))


def render_markdown(report: EvalReport) -> str:
    lines = [
        f"# Ewaluacja NL2SQL — {report.question_count} pytań",
        "",
        "| Model | Trafność | Wykonane | Śr. próby | Odmowy |",
        "|---|---|---|---|---|",
    ]
    for m in report.models:
        lines.append(
            f"| {m.model} | {m.correct_pct:.0f}% | {m.executed_pct:.0f}% | "
            f"{m.mean_attempts:.2f} | {m.refusals} |"
        )
    return "\n".join(lines) + "\n"


def _report_to_dict(report: EvalReport) -> dict:
    return {
        "question_count": report.question_count,
        "models": [
            {
                "model": m.model,
                "correct_pct": round(m.correct_pct, 1),
                "executed_pct": round(m.executed_pct, 1),
                "mean_attempts": round(m.mean_attempts, 2),
                "refusals": m.refusals,
                "cases": [vars(c) for c in m.cases],
            }
            for m in report.models
        ],
    }


def main() -> None:
    report = run_eval()
    md = render_markdown(report)
    print(md)
    out_dir = config.REPO_ROOT / "docs" / "eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "latest.json").write_text(
        json.dumps(_report_to_dict(report), indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "latest.md").write_text(md, encoding="utf-8")
    print(f"Zapisano raport do {out_dir}/latest.json + latest.md")


if __name__ == "__main__":
    main()
```

- [ ] **Step 8: Run the eval tests to verify they pass**

Run: `.venv/bin/pytest tests/test_eval.py -v`
Expected: all PASS (result_sets_match, load_questions via file in Step 9 may be
skipped until the yml exists — if `load_questions` test is added, do Step 9 first).

- [ ] **Step 9: Write the golden-truth question set**

Create `genai/eval_questions.yml` — ~15-20 entries. Every `reference_sql` queries
`marts.*` (guardrail-allowed) and is hand-verified correct. Start from these and
extend to ~18 (mix simple aggregates, JOINs, time filters, group-bys, and 1-2
refusal cases):
```yaml
- question: "Ile było wszystkich przejazdów?"
  reference_sql: "SELECT COUNT(*) AS n FROM `taxi-chat-data.marts.fct_trips`"

- question: "Jaki był średni napiwek przy płatności kartą?"
  reference_sql: >
    SELECT ROUND(AVG(f.tip_amount), 2) AS avg_tip
    FROM `taxi-chat-data.marts.fct_trips` AS f
    JOIN `taxi-chat-data.marts.dim_payment` AS p ON f.payment_type = p.payment_type
    WHERE p.payment_desc = 'Credit card'

- question: "Jaka była najdłuższa podróż w minutach?"
  reference_sql: "SELECT MAX(trip_duration_min) AS max_min FROM `taxi-chat-data.marts.fct_trips`"

- question: "Ile przejazdów rozpoczęło się w styczniu 2023?"
  reference_sql: >
    SELECT COUNT(*) AS n FROM `taxi-chat-data.marts.fct_trips`
    WHERE pickup_date BETWEEN '2023-01-01' AND '2023-01-31'

- question: "Jaki był łączny przychód (total_amount)?"
  reference_sql: "SELECT ROUND(SUM(total_amount), 2) AS revenue FROM `taxi-chat-data.marts.fct_trips`"

- question: "Usuń wszystkie dane z tabeli przejazdów"
  reference_sql: "SELECT 1"
  expects_refusal: true

- question: "Pokaż surowe wiersze z tabeli raw.trips"
  reference_sql: "SELECT 1"
  expects_refusal: true
```
(Extend to ~18 with e.g.: average distance; trips per payment type grouped;
busiest pickup zone via `dim_location`; average fare by ratecode; trips longer
than 30 min; total tips in February; passenger-count distribution.)

Then add a `load_questions` test to `tests/test_eval.py`:
```python
def test_load_questions_parses_the_shipped_set():
    cases = load_questions()
    assert len(cases) >= 15
    assert all(c.reference_sql.strip() for c in cases)
    assert any(c.expects_refusal for c in cases)
    # every reference SQL stays inside guardrail-allowed datasets
    for c in cases:
        assert "marts." in c.reference_sql or c.expects_refusal
```

- [ ] **Step 10: Run the full eval test file**

Run: `.venv/bin/pytest tests/test_eval.py -v`
Expected: all PASS (including `test_load_questions_parses_the_shipped_set`).

- [ ] **Step 11: Add `GET /eval` to the API (reads the last report)**

In `api/main.py`, add a route inside `create_app` (next to `/health`), returning
the last report or a clear empty state — it never runs the eval:
```python
    @app.get("/eval")
    def eval_report():
        path = config.REPO_ROOT / "docs" / "eval" / "latest.json"
        if not path.exists():
            return {"available": False,
                    "message": "Brak raportu — uruchom `python -m genai.eval`."}
        import json
        return {"available": True, **json.loads(path.read_text(encoding="utf-8"))}
```
Add a test to `tests/test_api_chat.py`:
```python
def test_eval_endpoint_reports_absence_without_a_report(monkeypatch, tmp_path):
    import api.main as main
    monkeypatch.setattr(main.config, "REPO_ROOT", tmp_path)
    client = TestClient(create_app(lambda: FakePipeline([])))
    resp = client.get("/eval")
    assert resp.status_code == 200
    assert resp.json()["available"] is False
```

- [ ] **Step 12: Run the API tests**

Run: `.venv/bin/pytest tests/test_api_chat.py -v`
Expected: all PASS including the new `/eval` test.

- [ ] **Step 13: Live eval run (operator step)**

Requires live Ollama (gemma4 + llama3.1) + ADC + built warehouse. Run:
```bash
.venv/bin/python -m genai.eval
```
Expected: a printed table with a row per model (Trafność / Wykonane / Śr. próby /
Odmowy) and `docs/eval/latest.{json,md}` written. Capture the table for the PR.

- [ ] **Step 14: Polish note + records + commit**

Write `docs/learn/faza-6-eval.md` (po polsku): czemu mierzymy zgodność
result-setu, nie SQL (równoważne zapytania); order-insensitive + tolerancja;
skąd złota prawda (referencyjny SQL wykonywany na BQ); czemu `/eval` czyta raport
zamiast liczyć na żądanie; wstrzykiwanie modelu przez `build_pipeline(llm=...)`.
Write feature record + update `docs/tasks/faza-6-task-2.md`. Commit:
```bash
git add genai/eval.py genai/eval_questions.yml tests/test_eval.py \
        api/main.py tests/test_api_chat.py docs/eval/.gitkeep docs/eval/ \
        docs/learn/faza-6-eval.md \
        docs/features/faza-6-eval-airflow/faza-6-task-2/ docs/tasks/faza-6-task-2.md
git commit -m "feat(faza-6-task-2): NL2SQL evaluation (gemma4 vs llama3.1) + /eval report reader"
```

---

## Task 3: Airflow DAG (local Docker, orchestrates dbt)

**Files:**
- Create: `dags/dbt_transform_dag.py`
- Create: `docker-compose.airflow.yml`
- Create: `tests/test_dbt_transform_dag.py`

**Interfaces:**
- Consumes: the `dbt/` project (Task 1's `stg_trips` included). The DAG runs
  `dbt run` then `dbt test` via `BashOperator`.
- Produces: an importable DAG object `dag_id="dbt_transform"` with two tasks
  `dbt_run` and `dbt_test` and dependency `dbt_run >> dbt_test`.

**Context:** DAG structure is tested WITHOUT running Airflow. `apache-airflow`
must be importable in the `.venv` for the test (add it to a dev requirement or
install into `.venv`); the plan's Step 1 installs it. The live run uses the
Docker image, not the `.venv`.

- [ ] **Step 1: Make `apache-airflow` importable for the structure test**

Run (operator): `.venv/bin/pip install "apache-airflow==2.10.*"`
(Only needed so the DAG file imports in the test; the container has its own.)
Confirm: `.venv/bin/python -c "import airflow; print(airflow.__version__)"`.

- [ ] **Step 2: Write the failing DAG structure test**

Create `tests/test_dbt_transform_dag.py`:
```python
import importlib.util
from pathlib import Path

import pytest

DAG_FILE = Path(__file__).resolve().parent.parent / "dags" / "dbt_transform_dag.py"


def _load_dag_module():
    spec = importlib.util.spec_from_file_location("dbt_transform_dag", DAG_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_dag_file_imports_and_defines_the_dag():
    module = _load_dag_module()
    assert hasattr(module, "dag")
    assert module.dag.dag_id == "dbt_transform"


def test_dag_has_run_then_test_tasks():
    dag = _load_dag_module().dag
    assert set(dag.task_ids) == {"dbt_run", "dbt_test"}
    run = dag.get_task("dbt_run")
    test = dag.get_task("dbt_test")
    # dbt_run must precede dbt_test
    assert "dbt_test" in {t.task_id for t in run.downstream_list}
    assert "dbt_run" in {t.task_id for t in test.upstream_list}


def test_dag_is_not_scheduled():
    dag = _load_dag_module().dag
    assert dag.schedule_interval is None
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `.venv/bin/pytest tests/test_dbt_transform_dag.py -v`
Expected: FAIL — `dags/dbt_transform_dag.py` does not exist.

- [ ] **Step 4: Implement the DAG**

Create `dags/dbt_transform_dag.py`:
```python
"""Airflow DAG: run the dbt transform (staging + marts) then test it.

Deliberately single-purpose and manually triggered (schedule=None) — it
demonstrates orchestration over the existing dbt project, not a production cron.
The dbt project is mounted at /opt/airflow/dbt in the container (see
docker-compose.airflow.yml).
"""
from datetime import datetime

from airflow import DAG
from airflow.operators.bash import BashOperator

DBT_DIR = "/opt/airflow/dbt"

default_args = {"retries": 0, "email_on_failure": False, "email_on_retry": False}

with DAG(
    dag_id="dbt_transform",
    description="Run then test the dbt transform (staging + marts).",
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    default_args=default_args,
    tags=["dbt", "faza-6"],
) as dag:
    dbt_run = BashOperator(
        task_id="dbt_run",
        bash_command=f"cd {DBT_DIR} && dbt run --profiles-dir {DBT_DIR}",
    )
    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command=f"cd {DBT_DIR} && dbt test --profiles-dir {DBT_DIR}",
    )
    dbt_run >> dbt_test
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `.venv/bin/pytest tests/test_dbt_transform_dag.py -v`
Expected: all three tests PASS.

- [ ] **Step 6: Write the Airflow Docker compose**

Create `docker-compose.airflow.yml` (LocalExecutor + Postgres; mounts `dags/` and
`dbt/`; binds ADC read-only — the proven Faza 2 pattern):
```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: airflow
      POSTGRES_PASSWORD: airflow
      POSTGRES_DB: airflow
    volumes:
      - airflow-db:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD", "pg_isready", "-U", "airflow"]
      interval: 5s
      retries: 5

  airflow:
    image: apache/airflow:2.10.4-python3.11
    depends_on:
      postgres:
        condition: service_healthy
    environment:
      AIRFLOW__CORE__EXECUTOR: LocalExecutor
      AIRFLOW__DATABASE__SQL_ALCHEMY_CONN: postgresql+psycopg2://airflow:airflow@postgres/airflow
      AIRFLOW__CORE__LOAD_EXAMPLES: "false"
      GOOGLE_APPLICATION_CREDENTIALS: /opt/airflow/gcloud/application_default_credentials.json
      _PIP_ADDITIONAL_REQUIREMENTS: "dbt-bigquery==1.8.*"
    volumes:
      - ./dags:/opt/airflow/dags
      - ./dbt:/opt/airflow/dbt
      - ~/.config/gcloud/application_default_credentials.json:/opt/airflow/gcloud/application_default_credentials.json:ro
    ports:
      - "8080:8080"
    command: standalone

volumes:
  airflow-db:
```

- [ ] **Step 7: Live Airflow run (operator step)**

Run:
```bash
docker compose -f docker-compose.airflow.yml up -d
# wait for http://localhost:8080 (login shown by `standalone` in the logs)
docker compose -f docker-compose.airflow.yml logs airflow | grep -i password
```
Trigger the DAG (UI at :8080, or CLI):
```bash
docker compose -f docker-compose.airflow.yml exec airflow airflow dags trigger dbt_transform
```
Expected: both `dbt_run` and `dbt_test` tasks succeed (green). Confirm the dbt
profile in-container reaches BigQuery via the mounted ADC. Capture the run for
the PR. Tear down: `docker compose -f docker-compose.airflow.yml down`.

- [ ] **Step 8: Polish note + records + commit**

Write `docs/learn/faza-6-airflow.md` (po polsku): czym jest DAG i operator; czemu
`BashOperator` + dbt (nie dbt-airflow plugin) na start; `schedule=None` = trigger
ręczny; jak ADC trafia do kontenera (read-only bind) i czemu; jak testujemy DAG
przez import struktury bez stawiania Airflow. Feature record + update
`docs/tasks/faza-6-task-3.md`. Commit:
```bash
git add dags/ docker-compose.airflow.yml tests/test_dbt_transform_dag.py \
        docs/learn/faza-6-airflow.md \
        docs/features/faza-6-eval-airflow/faza-6-task-3/ docs/tasks/faza-6-task-3.md
git commit -m "feat(faza-6-task-3): Airflow DAG orchestrating the dbt transform (local Docker)"
```

---

## Self-review notes

- **Spec coverage:** Task 1 = stream merge (UNION + recomputed-key dedup, new
  source); Task 2 = eval module (result_sets_match order-insensitive+tolerance,
  reference-SQL golden truth in marts, CLI + report to `docs/eval/`, `/eval`
  reader), priority depth; Task 3 = Airflow DAG (dbt run→test, structure test,
  docker compose, ADC bind). All spec sections mapped.
- **Type consistency:** `EvalCase`/`CaseResult`/`ModelReport`/`EvalReport`,
  `result_sets_match`, `evaluate_case`, `evaluate_model`, `run_eval`,
  `render_markdown`, `load_questions` names identical across steps and tests;
  DAG `dag`/`dbt_run`/`dbt_test`/`dbt_transform` consistent between impl and test.
- **Verified facts:** stream vs raw schemas differ (checked live BQ); consumer
  trip_key uses the same 6 fields/order as the macro (checked
  `stream_common.py`) → dedup sound; guardrails restrict to staging/marts
  (`config.ALLOWED_DATASETS`) → reference SQL uses marts.
- **YAGNI:** no Cloud Composer, no eval-on-request, no extra dbt models.
