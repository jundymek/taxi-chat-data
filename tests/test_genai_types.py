from genai.types import LLMError, SchemaContext, ValidationResult


def test_schema_context_holds_prompt_ready_strings():
    ctx = SchemaContext(tables=["Table marts.fct_trips: trips"], examples=["QUESTION: x\nSQL: y"])
    assert ctx.tables[0].startswith("Table ")
    assert len(ctx.examples) == 1


def test_validation_result_defaults():
    ok = ValidationResult(ok=True, sql="SELECT 1", reason=None, estimated_bytes=123)
    bad = ValidationResult(
        ok=False, sql="DROP TABLE x", reason="Tylko SELECT jest dozwolony.", estimated_bytes=None
    )
    assert ok.ok and not bad.ok
    assert isinstance(bad.reason, str)


def test_llm_error_is_exception():
    assert issubclass(LLMError, Exception)
