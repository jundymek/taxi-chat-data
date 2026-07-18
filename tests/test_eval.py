from genai.eval import (
    CaseResult,
    EvalCase,
    ModelReport,
    evaluate_case,
    load_questions,
    render_markdown,
    result_sets_match,
)


def test_matches_same_rows_regardless_of_order():
    a = [{"c": 1}, {"c": 2}]
    b = [{"c": 2}, {"c": 1}]
    assert result_sets_match(a, b) is True


def test_matches_within_numeric_tolerance():
    assert result_sets_match([{"avg": 4.16}], [{"avg": 4.160000001}]) is True


def test_tolerance_uses_abs_tol_not_rounding_buckets():
    # Values within tol must match regardless of where they fall relative to a
    # rounding-bucket edge; values beyond tol must not.
    assert result_sets_match([{"x": 1.49e-6}], [{"x": 2.0e-6}], tol=1e-6) is True
    assert result_sets_match([{"x": 1.0}], [{"x": 1.0 + 2e-6}], tol=1e-6) is False


def test_boolean_never_matches_number():
    assert result_sets_match([{"f": True}], [{"f": 1}]) is False
    assert result_sets_match([{"f": True}], [{"f": True}]) is True


def test_rejects_different_values():
    assert result_sets_match([{"avg": 4.16}], [{"avg": 9.99}]) is False


def test_rejects_different_row_count():
    assert result_sets_match([{"c": 1}], [{"c": 1}, {"c": 2}]) is False


def test_ignores_column_aliases_when_values_match():
    # SQL aliases are arbitrary: a bare COUNT(*) (BigQuery `f0_`) must match a
    # reference `COUNT(*) AS n` — same answer, different column name.
    assert result_sets_match([{"f0_": 1}], [{"n": 1}]) is True


def test_rejects_different_column_count():
    assert result_sets_match([{"a": 1}], [{"a": 1, "b": 2}]) is False


def test_matches_multi_column_rows_order_insensitive():
    a = [{"zone": "Manhattan", "n": 10}, {"zone": "Queens", "n": 3}]
    b = [{"zone": "Queens", "n": 3}, {"zone": "Manhattan", "n": 10}]
    assert result_sets_match(a, b) is True


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


def test_evaluate_case_unexpected_refusal_is_incorrect():
    case = EvalCase(question="Ile kursów?", reference_sql="SELECT 1")
    pipeline = FakePipeline(REFUSAL_UPDATES)
    bq = FakeBQ([])
    result = evaluate_case(case, pipeline, bq)
    assert result.refused is True
    assert result.correct is False  # we did NOT expect a refusal here


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


def test_load_questions_parses_the_shipped_set():
    cases = load_questions()
    assert len(cases) >= 15
    assert all(c.reference_sql.strip() for c in cases)
    assert any(c.expects_refusal for c in cases)
    # every reference SQL stays inside guardrail-allowed datasets
    for c in cases:
        assert "marts." in c.reference_sql or c.expects_refusal
