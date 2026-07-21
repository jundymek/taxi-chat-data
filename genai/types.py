"""Shared contracts between genai modules. Wave-1 tasks build against these."""
from dataclasses import dataclass


class LLMError(Exception):
    """Raised when the Ollama backend is unreachable or returns garbage."""


@dataclass
class SchemaContext:
    """RAG retrieval result, prompt-ready."""
    tables: list[str]    # formatted table/column descriptions
    examples: list[str]  # formatted "QUESTION: ...\nSQL: ..." pairs


@dataclass
class ValidationResult:
    """Guardrail verdict for one SQL statement."""
    ok: bool
    sql: str                        # possibly amended (e.g. LIMIT appended)
    reason: str | None              # user-facing / retry feedback
    estimated_bytes: int | None     # from the BigQuery dry-run
