from genai.pipeline import build_pipeline
from genai.types import SchemaContext, ValidationResult

SELECT_ONLY = "Only SELECT queries (read-only) are allowed."

CTX = SchemaContext(tables=["Table marts.fct_trips: trips"], examples=["QUESTION: q\nSQL: s"])
GOOD_SQL = "SELECT COUNT(*) AS c FROM `taxi-chat-data.marts.fct_trips` LIMIT 100"


class FakeRetriever:
    def retrieve(self, question, k_schema=4, k_examples=3):
        return CTX


class FakeLLM:
    """Returns queued generate() responses, then keeps repeating the last one."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []

    def generate(self, prompt, system=None):
        self.prompts.append(prompt)
        return self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]


class FakeRow:
    def __init__(self, data):
        self._data = data

    def items(self):
        return self._data.items()

    def __iter__(self):
        return iter(self._data)

    def keys(self):
        return self._data.keys()

    def values(self):
        return self._data.values()


class FakeQueryJob:
    def __init__(self, rows):
        self._rows = rows
        self.total_bytes_processed = 512

    def result(self):
        return self._rows


class FakeBQClient:
    def __init__(self):
        self.executed = []

    def query(self, sql, job_config=None):
        assert job_config.maximum_bytes_billed is not None
        self.executed.append(sql)
        return FakeQueryJob([FakeRow({"c": 3066766})])


def _validate_ok(sql, **kwargs):
    return ValidationResult(ok=True, sql=sql, reason=None, estimated_bytes=512)


def test_happy_path_retrieve_generate_validate_execute_summarize():
    llm = FakeLLM([f"```sql\n{GOOD_SQL}\n```", "There are 3,066,766 trips in the warehouse."])
    bq = FakeBQClient()
    app = build_pipeline(llm=llm, retriever=FakeRetriever(), validate_fn=_validate_ok, bq_client=bq)
    state = app.invoke({"question": "How many trips were there?"})
    assert state["refused"] is False
    assert state["rows"] == [{"c": 3066766}]
    assert state["answer"] == "There are 3,066,766 trips in the warehouse."
    assert bq.executed == [GOOD_SQL]


def test_validation_failure_retries_with_feedback_then_succeeds():
    calls = {"n": 0}

    def flaky_validate(sql, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return ValidationResult(ok=False, sql=sql, reason="Missing LIMIT", estimated_bytes=None)
        return ValidationResult(ok=True, sql=sql, reason=None, estimated_bytes=1)

    llm = FakeLLM([f"```sql\n{GOOD_SQL}\n```", f"```sql\n{GOOD_SQL}\n```", "Answer."])
    app = build_pipeline(
        llm=llm, retriever=FakeRetriever(), validate_fn=flaky_validate, bq_client=FakeBQClient()
    )
    state = app.invoke({"question": "How many?"})
    assert state["refused"] is False
    assert calls["n"] == 2
    assert any("Missing LIMIT" in p for p in llm.prompts)  # feedback reached the model


def test_default_validate_uses_injected_bq_client():
    """With validate_fn omitted, the guardrail dry-run must run on the SAME
    injected BigQuery client as execution (not a fresh internal one)."""

    class DryRunAwareBQClient(FakeBQClient):
        def __init__(self):
            super().__init__()
            self.dry_runs = []

        def query(self, sql, job_config=None):
            if getattr(job_config, "dry_run", False):
                self.dry_runs.append(sql)
                return FakeQueryJob([])
            return super().query(sql, job_config=job_config)

    llm = FakeLLM([f"```sql\n{GOOD_SQL}\n```", "Answer."])
    bq = DryRunAwareBQClient()
    app = build_pipeline(llm=llm, retriever=FakeRetriever(), bq_client=bq)
    state = app.invoke({"question": "How many?"})
    assert state["refused"] is False
    assert bq.dry_runs, "guardrail dry-run must go through the injected client"
    assert bq.executed == [GOOD_SQL]


def test_default_retriever_survives_generation_only_llm(monkeypatch):
    """Injecting an LLM without .embed() must not be handed to the default
    retriever as embedder — the retriever falls back to its own."""
    import genai.retriever

    captured = {}

    class RecordingRetriever:
        def __init__(self, chroma_dir=None, embedder=None):
            captured["embedder"] = embedder

        def retrieve(self, question, k_schema=4, k_examples=3):
            return CTX

    monkeypatch.setattr(genai.retriever, "Retriever", RecordingRetriever)

    class GenerationOnlyLLM:
        def generate(self, prompt, system=None):
            return f"```sql\n{GOOD_SQL}\n```"

    app = build_pipeline(
        llm=GenerationOnlyLLM(), validate_fn=_validate_ok, bq_client=FakeBQClient()
    )
    state = app.invoke({"question": "How many?"})
    assert captured["embedder"] is None
    assert state["refused"] is False


def test_refuses_after_exhausting_attempts():
    def always_reject(sql, **kwargs):
        return ValidationResult(
            ok=False, sql=sql, reason=SELECT_ONLY, estimated_bytes=None
        )

    llm = FakeLLM(["```sql\nDROP TABLE x\n```"])
    app = build_pipeline(
        llm=llm, retriever=FakeRetriever(), validate_fn=always_reject, bq_client=FakeBQClient()
    )
    state = app.invoke({"question": "Delete the data"})
    assert state["refused"] is True
    assert SELECT_ONLY in state["answer"]
    assert state["rows"] == []
