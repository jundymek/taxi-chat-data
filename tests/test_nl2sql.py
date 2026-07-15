from genai.nl2sql import build_prompt, extract_sql, generate_sql
from genai.types import SchemaContext

CTX = SchemaContext(
    tables=["Table marts.fct_trips: trips fact"],
    examples=["QUESTION: Ile było przejazdów?\nSQL: SELECT COUNT(*) FROM `taxi-chat-data.marts.fct_trips`"],
)


def test_build_prompt_contains_question_context_and_examples():
    prompt = build_prompt("Ile było kursów?", CTX)
    assert "Ile było kursów?" in prompt
    assert "Table marts.fct_trips" in prompt
    assert "QUESTION: Ile było przejazdów?" in prompt


def test_build_prompt_includes_error_feedback_on_retry():
    prompt = build_prompt("Ile?", CTX, error_feedback="Tabela raw.trips jest poza allowlistą")
    assert "raw.trips" in prompt
    assert "poprzednia próba" in prompt.lower() or "previous attempt" in prompt.lower()


def test_extract_sql_from_fenced_block():
    text = "Sure!\n```sql\nSELECT 1\n```\nHope it helps."
    assert extract_sql(text) == "SELECT 1"


def test_extract_sql_from_plain_fence_and_strips_semicolon():
    assert extract_sql("```\nSELECT 2;\n```") == "SELECT 2"


def test_extract_sql_falls_back_to_raw_text():
    assert extract_sql("  SELECT 3  ") == "SELECT 3"


def test_generate_sql_calls_llm_and_extracts():
    class FakeLLM:
        def generate(self, prompt, system=None):
            self.prompt = prompt
            self.system = system
            return "```sql\nSELECT COUNT(*) FROM `taxi-chat-data.marts.fct_trips`\n```"

    llm = FakeLLM()
    sql = generate_sql(llm, "Ile było kursów?", CTX)
    assert sql == "SELECT COUNT(*) FROM `taxi-chat-data.marts.fct_trips`"
    assert llm.system is not None and "BigQuery" in llm.system
