"""FastAPI adapter over the Faza 3 LangGraph pipeline.

POST /chat streams SSE frames (api/schemas.py is the contract); GET /health
reports dependency status; frontend/dist is served statically when built.

The pipeline is resolved lazily on the first /chat request and memoized on
app.state — never built at import time, so `app = create_app()` stays cheap and
tests can inject a fake factory without booting the app's lifespan.
"""
from collections.abc import Iterator
from pathlib import Path

import requests
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from api.schemas import (
    STAGE_DONE,
    STAGE_ERROR,
    STAGE_EXECUTE,
    STAGE_GENERATE_SQL,
    STAGE_RETRIEVE,
    STAGE_SUMMARIZE,
    STAGE_VALIDATE,
    Frame,
    Result,
    sse,
)
from genai import config
from genai.types import LLMError


class ChatRequest(BaseModel):
    question: str = Field(min_length=1)


def _frames_for(node: str, state: dict) -> list[Frame]:
    if node == "retrieve":
        return [Frame(stage=STAGE_RETRIEVE)]
    if node == "generate_sql":
        return [Frame(stage=STAGE_GENERATE_SQL, attempt=state.get("attempts"))]
    if node == "validate":
        v = state["validation"]
        return [Frame(stage=STAGE_VALIDATE, ok=v.ok,
                      reason=None if v.ok else v.reason)]
    if node == "execute":
        # execute finished; the pipeline is now writing the Polish answer.
        return [Frame(stage=STAGE_EXECUTE), Frame(stage=STAGE_SUMMARIZE)]
    return []  # summarize / refuse completions are represented by `done`


def _done_frame(state: dict) -> Frame:
    refused = bool(state.get("refused", False))
    validation = state.get("validation")
    return Frame(stage=STAGE_DONE, result=Result(
        answer=state.get("answer", ""),
        sql=state.get("sql", ""),
        rows=state.get("rows", []),
        scanned_gb=round(state.get("scanned_bytes", 0) / 1e9, 4),
        attempts=state.get("attempts", 0),
        refused=refused,
        reason=(validation.reason if refused and validation is not None else None),
        model=config.GENERATION_MODEL,
    ))


def stream_chat(get_pipeline, question: str) -> Iterator[bytes]:
    # `get_pipeline` is a zero-arg resolver, called INSIDE the try so a first-
    # request build failure (bad ADC, missing index) ends the protocol with a
    # terminal `error` frame — never a raw 500 that bypasses the SSE contract.
    state: dict = {"question": question}
    try:
        pipeline = get_pipeline()
        for update in pipeline.stream({"question": question}, stream_mode="updates"):
            for node, patch in update.items():
                state.update(patch or {})
                for frame in _frames_for(node, state):
                    yield sse(frame)
    except LLMError as exc:
        yield sse(Frame(stage=STAGE_ERROR, message=str(exc)))
        return
    except Exception as exc:  # infra failure mid-stream — still end the protocol
        yield sse(Frame(stage=STAGE_ERROR, message=f"Unexpected error: {exc}"))
        return
    yield sse(_done_frame(state))


def _check_ollama() -> str:
    try:
        requests.get(f"{config.OLLAMA_BASE_URL}/api/version", timeout=2).raise_for_status()
        return "ok"
    except requests.RequestException:
        return "down"


def _check_bigquery() -> str:
    try:
        from google.cloud import bigquery
        client = bigquery.Client(project=config.BQ_PROJECT)
        client.query("SELECT 1", job_config=bigquery.QueryJobConfig(dry_run=True))
        return "ok"
    except Exception:
        return "down"


def _check_chroma() -> str:
    # Directory-exists is not enough: the retriever needs BOTH collections
    # (schema_docs + few_shot_examples). Open them so a never-built, partial, or
    # corrupted index reports "missing" instead of a false "ok".
    try:
        if not Path(config.CHROMA_DIR).exists():
            return "missing"
        import chromadb

        from genai.indexer import EXAMPLES_COLLECTION, SCHEMA_COLLECTION
        client = chromadb.PersistentClient(path=str(config.CHROMA_DIR))
        for collection in (SCHEMA_COLLECTION, EXAMPLES_COLLECTION):
            client.get_collection(collection)
        return "ok"
    except Exception:
        return "missing"


def create_app(pipeline_factory=None) -> FastAPI:
    app = FastAPI(title="taxi-chat-data API")

    def _default_factory():
        from genai.pipeline import build_pipeline
        return build_pipeline()

    app.state.pipeline = None
    app.state.pipeline_factory = pipeline_factory or _default_factory

    def _get_pipeline():
        # Built once, on the first request — never at import time.
        if app.state.pipeline is None:
            app.state.pipeline = app.state.pipeline_factory()
        return app.state.pipeline

    @app.post("/chat")
    def chat(request: ChatRequest):
        return StreamingResponse(
            stream_chat(_get_pipeline, request.question),
            media_type="text/event-stream",
        )

    @app.get("/health")
    def health():
        return {"ollama": _check_ollama(), "bigquery": _check_bigquery(),
                "chroma_index": _check_chroma()}

    @app.get("/eval")
    def eval_report():
        # Read-only: serves the last written report; never runs the heavy eval
        # (that is the `python -m genai.eval` operator step).
        path = config.REPO_ROOT / "docs" / "eval" / "latest.json"
        if not path.exists():
            return {"available": False,
                    "message": "Brak raportu — uruchom `python -m genai.eval`."}
        import json
        return {"available": True, **json.loads(path.read_text(encoding="utf-8"))}

    dist = config.REPO_ROOT / "frontend" / "dist"
    if dist.exists():
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    return app


app = create_app()
