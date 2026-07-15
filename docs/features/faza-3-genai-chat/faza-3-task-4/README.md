# faza-3-task-4 — NL2SQL + LangGraph pipeline + CLI

## What was built

The wave-2 integration layer that turns the wave-1 modules (LLM client,
RAG retriever, SQL guardrails) into a working "chat with data" flow:

- `nl2sql` — prompt assembly (system rules + RAG schema context + few-shots +
  optional rejection feedback) and SQL extraction from fenced LLM output
  (```sql fence → plain fence → raw text; trailing semicolon stripped).
- `pipeline` — a LangGraph state graph:
  `retrieve → generate_sql → validate ⇄ retry → execute → summarize | refuse`.
  The conditional edge after `validate` is the point of the graph: on a
  guardrail rejection the Polish `reason` is fed back to the model and it
  retries, up to `config.MAX_SQL_ATTEMPTS`; when attempts are exhausted the
  pipeline refuses politely in Polish instead of executing anything.
  Execution always sets `maximum_bytes_billed` (cost belt independent of the
  guardrail dry-run). All four dependencies are injectable
  (`build_pipeline(llm, retriever, validate_fn, bq_client)`) with lazy
  production defaults.
- `ask` CLI — `python -m genai.ask "pytanie po polsku"`: prints the Polish
  answer, the executed SQL, and GB scanned; `LLMError` → stderr + exit 1.

## Files

- `genai/nl2sql.py` (NEW) — prompt template, `extract_sql`, `generate_sql`.
- `genai/pipeline.py` (NEW) — `AskState` TypedDict, `build_pipeline`, `ask`.
- `genai/ask.py` (NEW) — argparse CLI entry point.
- `tests/test_nl2sql.py` (NEW) — 6 unit tests (prompt content, feedback
  injection, fence extraction, fallback, system prompt reaches the LLM).
- `tests/test_pipeline.py` (NEW) — 3 unit tests with fakes for LLM/retriever/
  validator/BQ: happy path, retry-with-feedback, refusal after exhaustion.
  `FakeBQClient` asserts `maximum_bytes_billed` is set on every job.
- `tests/test_e2e_integration.py` (NEW) — 3 live e2e tests, marked
  `integration`, deselected by default; RUN in Task 5 (needs Ollama, ADC,
  built Chroma index).
- `docs/learn/faza-3-langgraph-nl2sql.md` (NEW) — Polish learning note
  (LangGraph vs LangChain, the graph, TypedDict partial updates, prompt
  anatomy, regex extraction rationale, DI pattern).

## Key decisions

- Implementation follows the phase plan
  (`docs/superpowers/plans/2026-07-15-faza-3-genai-chat.md`, Task 4) verbatim —
  all consumed wave-1 signatures verified against the merged code before
  starting; Task 5 depends on the produced `pipeline.ask` contract.
- No spec file exists at `docs/implementation-artifacts/faza-3-task-4.md`
  (checked worktree and mainline); the plan's Task 4 section is the story
  contract, consistent with how wave-1 siblings shipped.
- Unit tests never touch live GCP or Ollama; the integration file is written
  here but exercised only in Task 5, per the plan.
