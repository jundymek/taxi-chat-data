"""LangGraph pipeline: retrieve → generate_sql → validate ⇄ retry → execute → summarize.

The graph earns its keep through the validate→generate_sql back-edge: on a
guardrail rejection the model gets the rejection reason as feedback and tries
again (config.MAX_SQL_ATTEMPTS total attempts).
"""
from functools import partial
from typing import TypedDict

from langgraph.graph import END, StateGraph

from genai import config, guardrails, nl2sql
from genai.types import SchemaContext, ValidationResult

SUMMARY_SYSTEM = (
    "You are a helpful data analyst. Answer briefly and concretely, based ONLY "
    "on the provided query result rows. Reply in the SAME LANGUAGE as the "
    "user's question — if they ask in Polish, answer in Polish; if they ask in "
    "English, answer in English."
)

REFUSAL_TEMPLATE = "I can't answer that question safely. Last rejection reason: {reason}"


class AskState(TypedDict, total=False):
    question: str
    context: SchemaContext
    sql: str
    validation: ValidationResult
    attempts: int
    error_feedback: str
    rows: list[dict]
    scanned_bytes: int
    answer: str
    refused: bool


def build_pipeline(llm=None, retriever=None, validate_fn=None, bq_client=None):
    if llm is None:
        from genai.llm_client import LLMClient
        llm = LLMClient()
    if retriever is None:
        from genai import retriever as retriever_mod
        # Share the LLM as embedder only when it can embed; a generation-only
        # injected LLM must not break the default retriever.
        embedder = llm if hasattr(llm, "embed") else None
        retriever = retriever_mod.Retriever(embedder=embedder)
    if bq_client is None:
        from google.cloud import bigquery
        bq_client = bigquery.Client(project=config.BQ_PROJECT)
    if validate_fn is None:
        # Dry-run validation and execution must agree on project/auth/location.
        validate_fn = partial(guardrails.validate, bq_client=bq_client)

    def retrieve(state: AskState) -> AskState:
        return {"context": retriever.retrieve(state["question"]), "attempts": 0,
                "refused": False, "rows": []}

    def generate_sql(state: AskState) -> AskState:
        sql = nl2sql.generate_sql(
            llm, state["question"], state["context"], state.get("error_feedback")
        )
        return {"sql": sql, "attempts": state["attempts"] + 1}

    def validate(state: AskState) -> AskState:
        result = validate_fn(state["sql"])
        updates: AskState = {"validation": result}
        if not result.ok:
            updates["error_feedback"] = result.reason
        return updates

    def route_after_validate(state: AskState) -> str:
        if state["validation"].ok:
            return "execute"
        if state["attempts"] >= config.MAX_SQL_ATTEMPTS:
            return "refuse"
        return "generate_sql"

    def execute(state: AskState) -> AskState:
        from google.cloud.bigquery import QueryJobConfig
        job = bq_client.query(
            state["validation"].sql,
            job_config=QueryJobConfig(maximum_bytes_billed=config.MAX_SCAN_BYTES),
        )
        rows = [dict(row.items()) for row in job.result()]
        return {"rows": rows, "scanned_bytes": job.total_bytes_processed or 0,
                "sql": state["validation"].sql}

    def summarize(state: AskState) -> AskState:
        prompt = (
            f"Question: {state['question']}\n"
            f"SQL used: {state['sql']}\n"
            f"Result rows (max 20 shown): {state['rows'][:20]}\n"
            "Answer the question in the same language it was asked in."
        )
        return {"answer": llm.generate(prompt, system=SUMMARY_SYSTEM)}

    def refuse(state: AskState) -> AskState:
        reason = state["validation"].reason or "unknown"
        return {"refused": True, "answer": REFUSAL_TEMPLATE.format(reason=reason)}

    graph = StateGraph(AskState)
    graph.add_node("retrieve", retrieve)
    graph.add_node("generate_sql", generate_sql)
    graph.add_node("validate", validate)
    graph.add_node("execute", execute)
    graph.add_node("summarize", summarize)
    graph.add_node("refuse", refuse)

    graph.set_entry_point("retrieve")
    graph.add_edge("retrieve", "generate_sql")
    graph.add_edge("generate_sql", "validate")
    graph.add_conditional_edges("validate", route_after_validate,
                                {"execute": "execute", "generate_sql": "generate_sql",
                                 "refuse": "refuse"})
    graph.add_edge("execute", "summarize")
    graph.add_edge("summarize", END)
    graph.add_edge("refuse", END)
    return graph.compile()


def ask(question: str) -> dict:
    """Convenience wrapper used by the CLI: real components, one question."""
    app = build_pipeline()
    return app.invoke({"question": question})
