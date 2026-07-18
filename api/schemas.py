"""THE SSE protocol contract between the API and the frontend.

One frame per pipeline event: `event: stage` + single-line JSON data.
Exactly one terminal frame per request: `done` (with Result) or `error`.
A guardrail refusal is NOT `error` — it is `done` with `refused: true`.
"""
from pydantic import BaseModel

STAGE_RETRIEVE = "retrieve"
STAGE_GENERATE_SQL = "generate_sql"
STAGE_VALIDATE = "validate"
STAGE_EXECUTE = "execute"
STAGE_SUMMARIZE = "summarize"
STAGE_DONE = "done"
STAGE_ERROR = "error"


class Result(BaseModel):
    answer: str
    sql: str
    rows: list[dict]
    scanned_gb: float
    attempts: int
    refused: bool
    reason: str | None = None
    model: str


class Frame(BaseModel):
    stage: str
    attempt: int | None = None      # generate_sql frames
    ok: bool | None = None          # validate frames
    reason: str | None = None       # validate frames when ok is False (Polish)
    message: str | None = None      # error frames (Polish)
    result: Result | None = None    # done frames


def sse(frame: Frame) -> bytes:
    payload = frame.model_dump_json(exclude_none=True)
    return f"event: stage\ndata: {payload}\n\n".encode("utf-8")
