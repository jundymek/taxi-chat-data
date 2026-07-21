"""Prompt assembly and SQL extraction for the NL2SQL step."""
import re

from genai.types import SchemaContext

SYSTEM_PROMPT = (
    "You are an expert BigQuery SQL generator for an NYC taxi data warehouse. "
    "Return exactly ONE standard-SQL SELECT statement inside a ```sql fence. "
    "Use ONLY the tables and columns provided in the context, always fully "
    "qualified as `taxi-chat-data.<dataset>.<table>`. Never modify data. "
    "The user's question is in Polish."
)

_PROMPT_TEMPLATE = """Schema context:
{tables}

Similar solved examples:
{examples}

{feedback}Question: {question}

Reply with the SQL only."""


def build_prompt(question: str, context: SchemaContext, error_feedback: str | None = None) -> str:
    feedback = ""
    if error_feedback:
        feedback = (
            "IMPORTANT — the previous attempt was rejected: "
            f"{error_feedback}\nFix the SQL accordingly.\n\n"
        )
    return _PROMPT_TEMPLATE.format(
        tables="\n\n".join(context.tables),
        examples="\n\n".join(context.examples),
        feedback=feedback,
        question=question,
    )


def extract_sql(response: str) -> str:
    for pattern in (r"```sql\s*(.+?)```", r"```\s*(.+?)```"):
        match = re.search(pattern, response, flags=re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip().rstrip(";")
    return response.strip().rstrip(";")


def generate_sql(
    llm, question: str, context: SchemaContext, error_feedback: str | None = None
) -> str:
    response = llm.generate(build_prompt(question, context, error_feedback), system=SYSTEM_PROMPT)
    return extract_sql(response)
