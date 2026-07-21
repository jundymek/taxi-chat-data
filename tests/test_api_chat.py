import json

from fastapi.testclient import TestClient

from api.main import create_app
from genai.types import ValidationResult

VAL_OK = ValidationResult(ok=True, sql="SELECT 1 LIMIT 1", reason=None, estimated_bytes=512)
SELECT_ONLY = "Only SELECT queries (read-only) are allowed."
VAL_BAD = ValidationResult(ok=False, sql="DROP x", reason=SELECT_ONLY, estimated_bytes=None)


class FakePipeline:
    """Yields scripted {node: patch} updates like LangGraph stream_mode='updates'."""

    def __init__(self, updates, error=None):
        self.updates = updates
        self.error = error

    def stream(self, state, stream_mode="updates"):
        assert stream_mode == "updates"
        yield from self.updates
        if self.error:
            raise self.error


def _frames(client, question="How many trips?"):
    with client.stream("POST", "/chat", json={"question": question}) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        body = b"".join(resp.iter_bytes()).decode()
    return [json.loads(part.split("data: ", 1)[1])
            for part in body.split("\n\n") if part.startswith("event: stage")]


HAPPY = [
    {"retrieve": {"context": None, "attempts": 0, "refused": False, "rows": []}},
    {"generate_sql": {"sql": "SELECT 1", "attempts": 1}},
    {"validate": {"validation": VAL_OK}},
    {"execute": {"rows": [{"c": 5}], "scanned_bytes": 48_000_000, "sql": VAL_OK.sql}},
    {"summarize": {"answer": "Five trips."}},
]


def test_happy_path_emits_ordered_frames_and_done():
    client = TestClient(create_app(lambda: FakePipeline(HAPPY)))
    frames = _frames(client)
    assert [f["stage"] for f in frames] == [
        "retrieve", "generate_sql", "validate", "execute", "summarize", "done"]
    assert frames[1]["attempt"] == 1
    assert frames[2]["ok"] is True and "reason" not in frames[2]
    done = frames[-1]["result"]
    assert done == {"answer": "Five trips.", "sql": "SELECT 1 LIMIT 1",
                    "rows": [{"c": 5}], "scanned_gb": 0.048, "attempts": 1,
                    "refused": False, "model": done["model"]}


RETRY = [
    {"retrieve": {"context": None, "attempts": 0, "refused": False, "rows": []}},
    {"generate_sql": {"sql": "SELECT * FROM raw.trips", "attempts": 1}},
    {"validate": {"validation": VAL_BAD, "error_feedback": VAL_BAD.reason}},
    {"generate_sql": {"sql": "SELECT 1", "attempts": 2}},
    {"validate": {"validation": VAL_OK}},
    {"execute": {"rows": [], "scanned_bytes": 0, "sql": VAL_OK.sql}},
    {"summarize": {"answer": "Zero."}},
]


def test_retry_emits_two_validate_frames_with_reason_on_failure():
    frames = _frames(TestClient(create_app(lambda: FakePipeline(RETRY))))
    validates = [f for f in frames if f["stage"] == "validate"]
    assert validates[0] == {
        "stage": "validate", "ok": False,
        "reason": SELECT_ONLY}
    assert validates[1]["ok"] is True
    assert frames[-1]["result"]["attempts"] == 2


REFUSAL = [
    {"retrieve": {"context": None, "attempts": 0, "refused": False, "rows": []}},
    {"generate_sql": {"sql": "DROP x", "attempts": 3}},
    {"validate": {"validation": VAL_BAD, "error_feedback": VAL_BAD.reason}},
    {"refuse": {"refused": True, "answer": "I can't answer that safely."}},
]


def test_refusal_is_done_with_refused_true_not_error():
    frames = _frames(TestClient(create_app(lambda: FakePipeline(REFUSAL))))
    done = frames[-1]
    assert done["stage"] == "done"
    assert done["result"]["refused"] is True
    assert done["result"]["reason"] == SELECT_ONLY
    assert done["result"]["rows"] == []
    assert not any(f["stage"] == "error" for f in frames)


def test_midstream_exception_yields_terminal_error_frame():
    from genai.types import LLMError
    client = TestClient(create_app(
        lambda: FakePipeline(HAPPY[:2], error=LLMError("Ollama is not responding"))))
    frames = _frames(client)
    assert frames[-1]["stage"] == "error"
    assert "Ollama" in frames[-1]["message"]
    assert not any(f["stage"] == "done" for f in frames)


def test_pipeline_build_failure_yields_terminal_error_frame():
    # A first-request build failure (e.g. bad ADC / missing index) must end the
    # SSE protocol with a terminal `error` frame, not a raw HTTP 500.
    def boom():
        raise RuntimeError("BigQuery credentials missing")

    frames = _frames(TestClient(create_app(boom)))
    assert frames[-1]["stage"] == "error"
    assert "BigQuery credentials missing" in frames[-1]["message"]
    assert not any(f["stage"] == "done" for f in frames)


def test_empty_question_is_422():
    client = TestClient(create_app(lambda: FakePipeline([])))
    assert client.post("/chat", json={"question": ""}).status_code == 422
    assert client.post("/chat", json={}).status_code == 422


def test_check_chroma_ok_only_when_both_collections_present(tmp_path, monkeypatch):
    import chromadb

    import api.main as main
    from genai import config
    from genai.indexer import EXAMPLES_COLLECTION, SCHEMA_COLLECTION

    # Nonexistent directory -> "missing".
    monkeypatch.setattr(config, "CHROMA_DIR", tmp_path / "nope")
    assert main._check_chroma() == "missing"

    # Directory exists but the collections were never built -> "missing"
    # (this is the false-positive the folder-exists check would have reported ok).
    monkeypatch.setattr(config, "CHROMA_DIR", tmp_path)
    client = chromadb.PersistentClient(path=str(tmp_path))
    assert main._check_chroma() == "missing"

    # Both collections present -> "ok".
    client.create_collection(SCHEMA_COLLECTION)
    client.create_collection(EXAMPLES_COLLECTION)
    assert main._check_chroma() == "ok"


def test_eval_endpoint_reports_absence_without_a_report(monkeypatch, tmp_path):
    import api.main as main
    monkeypatch.setattr(main.config, "REPO_ROOT", tmp_path)
    client = TestClient(create_app(lambda: FakePipeline([])))
    resp = client.get("/eval")
    assert resp.status_code == 200
    assert resp.json()["available"] is False


def test_eval_endpoint_serves_the_last_report(monkeypatch, tmp_path):
    import api.main as main
    report = {"question_count": 2, "models": [{"model": "gemma4:latest", "correct_pct": 50.0}]}
    eval_dir = tmp_path / "docs" / "eval"
    eval_dir.mkdir(parents=True)
    (eval_dir / "latest.json").write_text(json.dumps(report), encoding="utf-8")
    monkeypatch.setattr(main.config, "REPO_ROOT", tmp_path)
    client = TestClient(create_app(lambda: FakePipeline([])))
    resp = client.get("/eval")
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True
    assert body["question_count"] == 2
    assert body["models"][0]["model"] == "gemma4:latest"


def test_health_reports_each_dependency(monkeypatch):
    import api.main as main
    monkeypatch.setattr(main, "_check_ollama", lambda: "ok")
    monkeypatch.setattr(main, "_check_bigquery", lambda: "down")
    monkeypatch.setattr(main, "_check_chroma", lambda: "missing")
    client = TestClient(create_app(lambda: FakePipeline([])))
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"ollama": "ok", "bigquery": "down", "chroma_index": "missing"}
