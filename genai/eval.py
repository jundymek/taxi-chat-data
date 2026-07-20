"""NL2SQL quality evaluation: run the pipeline per model over golden-truth
questions and score result-set correctness. Pure units are unit-tested; the
live run (Ollama + BigQuery) is an operator step via `python -m genai.eval`.
"""
from __future__ import annotations

import json
import os
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


def load_questions(path: str | Path | None = None) -> list[EvalCase]:
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


def _cells_match(a, b, tol: float) -> bool:
    # bool is an int subclass — a boolean matches only another boolean, never a
    # number (so True never equals 1).
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return isclose(float(a), float(b), rel_tol=0.0, abs_tol=tol)
    return a == b


def _rows_match(a_row: dict, b_row: dict, tol: float) -> bool:
    # Column NAMES are ignored — SQL aliases are arbitrary (a model's bare
    # `COUNT(*)` becomes BigQuery's `f0_`, the reference's `COUNT(*) AS n`
    # becomes `n`; same answer). Compare values in column order.
    return all(_cells_match(a, b, tol) for a, b in zip(a_row.values(), b_row.values()))


def result_sets_match(actual: list[dict], expected: list[dict], *, tol: float = 1e-6) -> bool:
    if len(actual) != len(expected):
        return False
    if not actual:
        return True
    # Same column COUNT required (names ignored — see _rows_match). Result rows
    # are uniform, so the first row is representative.
    if len(actual[0]) != len(expected[0]):
        return False
    # Order-insensitive multiset match with real numeric tolerance: greedily pair
    # each actual row to an as-yet-unmatched expected row it matches within `tol`.
    # (True `abs_tol` matching, not tolerance buckets — values differing by ~tol
    # near a bucket edge would otherwise be mis-split.)
    remaining = list(expected)
    for a_row in actual:
        for i, b_row in enumerate(remaining):
            if _rows_match(a_row, b_row, tol):
                remaining.pop(i)
                break
        else:
            return False
    return True


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


def _write_atomic(path: Path, text: str) -> None:
    # Write to a temp sibling then os.replace — an atomic rename on POSIX — so a
    # concurrent `GET /eval` reader never sees a half-written file.
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def main() -> None:
    report = run_eval()
    md = render_markdown(report)
    print(md)
    out_dir = config.REPO_ROOT / "docs" / "eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_atomic(out_dir / "latest.json",
                  json.dumps(_report_to_dict(report), indent=2, ensure_ascii=False))
    _write_atomic(out_dir / "latest.md", md)
    print(f"Zapisano raport do {out_dir}/latest.json + latest.md")


if __name__ == "__main__":
    main()
