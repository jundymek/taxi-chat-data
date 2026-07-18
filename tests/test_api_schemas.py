import json

from api.schemas import (
    STAGE_DONE, STAGE_VALIDATE, Frame, Result, sse,
)


def test_sse_frames_are_valid_sse_events_without_null_fields():
    raw = sse(Frame(stage=STAGE_VALIDATE, ok=False, reason="Tylko SELECT."))
    text = raw.decode("utf-8")
    assert text.startswith("event: stage\ndata: ")
    assert text.endswith("\n\n")
    data = json.loads(text.split("data: ", 1)[1])
    assert data == {"stage": "validate", "ok": False, "reason": "Tylko SELECT."}


def test_done_frame_carries_full_result():
    result = Result(answer="4,16 USD", sql="SELECT 1", rows=[{"avg_tip": 4.16}],
                    scanned_gb=0.048, attempts=2, refused=False, model="gemma4:latest")
    data = json.loads(sse(Frame(stage=STAGE_DONE, result=result)).decode().split("data: ", 1)[1])
    assert data["result"]["attempts"] == 2
    assert data["result"]["rows"] == [{"avg_tip": 4.16}]
    assert "reason" not in data["result"]  # nulls excluded


def test_frame_json_is_single_line():
    raw = sse(Frame(stage=STAGE_DONE, result=Result(
        answer="a\nb", sql="s", rows=[], scanned_gb=0.0, attempts=1,
        refused=True, reason="r", model="m")))
    body = raw.decode().split("data: ", 1)[1]
    assert "\n" not in body.rstrip("\n")  # newlines inside JSON are escaped
