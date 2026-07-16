# Faza 3: GenAI "chat with data" (RAG + NL2SQL + guardrails) — Design

**Goal:** A working "chat with data" core on top of the Faza 2 warehouse: a user
asks a question **in Polish**, the system retrieves schema context via RAG
(Chroma + nomic-embed), generates BigQuery SQL with a local LLM (gemma4 via
Ollama), validates it with guardrails **before** execution, runs it on
BigQuery, and answers in Polish. Deliverable: a single-shot CLI —
`python -m genai.ask "pytanie"`.

**Out of scope (later phases):** FastAPI + frontend (Faza 5), model evaluation
gemma4 vs llama3.1 (Faza 6), streaming (Faza 4), Airflow wiring (Faza 6).

**Approach (decided):** hand-rolled thin modules for the core (`llm_client`,
`retriever`, `guardrails` — plain `requests`, `chromadb`, `sqlglot`; no
framework magic, maximum learning value), with the question pipeline
orchestrated as a small **LangGraph** state graph (nodes are our own
functions; the graph earns its keep via the validate→regenerate retry cycle).
Rejected: full LangChain (hides the mechanics this project exists to teach);
no-RAG full-schema prompting (technically viable at this schema size, but RAG
is an explicit learning goal — it will serve as an evaluation baseline in
Faza 6 instead).

## Architecture

```
genai/
├── types.py         # shared contracts: SchemaContext, ValidationResult, LLMError
├── llm_client.py    # HTTP → Ollama: generate() + embed(); model/base_url via constructor
├── indexer.py       # reads dbt/models/**/*.yml + examples.yml → builds Chroma index
├── examples.yml     # curated few-shots: Polish question → correct BigQuery SQL (~10 pairs)
├── retriever.py     # question → embedding → top-k schema docs + top-k few-shots
├── guardrails.py    # SQL validation BEFORE execution (sqlglot + allowlist + LIMIT + BQ dry-run)
├── nl2sql.py        # prompt assembly (question + SchemaContext) → gemma4 → SQL extraction
├── pipeline.py      # LangGraph graph: retrieve → generate_sql → validate ⇄ retry → execute → summarize
└── ask.py           # CLI entry point (python -m genai.ask "pytanie")
```

- **Chroma** runs embedded (`chromadb.PersistentClient`) persisting to
  `data/chroma/` (gitignored). No new docker-compose service.
- **Ollama** runs on the host (`http://localhost:11434`); models already
  installed: `gemma4:latest` (NL2SQL + summarize), `nomic-embed-text` (embeddings).
- **Indexing is a separate manual step** (`python -m genai.indexer`), not part
  of answering a question. dbt YAML descriptions are the single source of truth
  about the schema — nothing is duplicated by hand.
- New dependencies in `requirements.txt`: `chromadb`, `sqlglot`, `langgraph`,
  `pyyaml`. Everything runs in the existing `.venv` (no Docker for genai).

## Question flow (LangGraph state)

Graph state: `question`, `context: SchemaContext`, `sql`, `validation_error`,
`attempts`, `rows`, `scanned_bytes`, `answer`.

1. **retrieve** — embed the question (nomic-embed via Ollama); fetch from
   Chroma: top-k table/column descriptions (k=4) + top-k similar few-shots (k=3).
2. **generate_sql** — gemma4 gets the Polish question, schema context, and
   few-shots; returns English BigQuery SQL. On retry it additionally gets the
   previous attempt's error message.
3. **validate** (guardrails) — see below. Failure → edge back to
   **generate_sql** (max 2 retries); after exhaustion → graceful refusal.
4. **execute** — run on BigQuery with `maximum_bytes_billed` set on the job
   (belt and braces on top of the dry-run gate).
5. **summarize** — gemma4 summarizes the result **in Polish**; CLI prints the
   answer + the SQL used + gigabytes scanned (transparency requirement).

## Module contracts (fixed up front — wave-1 agents build against these)

Defined in `genai/types.py`, committed BEFORE parallel work starts:

```python
# llm_client.py
class LLMClient:
    def __init__(self, model: str = "gemma4:latest",
                 base_url: str = "http://localhost:11434"): ...
    def generate(self, prompt: str, system: str | None = None) -> str  # raises LLMError
    def embed(self, texts: list[str]) -> list[list[float]]             # nomic-embed-text

# retriever.py
@dataclass
class SchemaContext:
    tables: list[str]      # formatted table/column descriptions, prompt-ready
    examples: list[str]    # formatted "QUESTION: ... SQL: ..." pairs

class Retriever:
    def __init__(self, chroma_dir: Path = DATA_DIR / "chroma",
                 embedder: LLMClient | None = None): ...
    def retrieve(self, question: str, k_schema: int = 4,
                 k_examples: int = 3) -> SchemaContext

# guardrails.py — pure function + result object, NO LLM calls
@dataclass
class ValidationResult:
    ok: bool
    sql: str                      # possibly amended (e.g. LIMIT appended)
    reason: str | None            # Polish, user-facing / retry feedback
    estimated_bytes: int | None   # from BQ dry-run

def validate(sql: str, *, max_bytes: int = 1_000_000_000) -> ValidationResult
```

Coupling rules (what makes wave-1 tasks independent):
- `guardrails` imports nothing from `llm_client`/`retriever` (pure SQL +
  BigQuery client).
- `retriever` receives `LLMClient` via constructor only; its unit tests mock
  embeddings — no dependency on the llm_client task finishing.
- `indexer.py` and `examples.yml` belong to the retriever task.

## Guardrails (validation before execution)

1. Parse with `sqlglot` (BigQuery dialect); unparseable → reject.
2. Single statement, `SELECT` only — reject DML/DDL (`DROP/DELETE/UPDATE/INSERT/MERGE/...`).
3. Table allowlist: only `marts.*` and `staging.*` (block `raw.*` and anything
   outside the project datasets).
4. Enforce `LIMIT`: append `LIMIT 100` when missing (amended SQL is returned,
   not rejected).
5. BigQuery **dry-run**: estimated `bytes_processed > max_bytes` (default
   1 GB) → reject with the estimate in the message. Dry-runs are free — this
   both protects the free tier and demonstrates "NL2SQL risk mitigation" as code.

## Error handling

The user always gets a readable Polish message, never a traceback:
- Ollama unreachable → `LLMError` with a hint (`ollama serve`, model name).
- Guardrail rejection → refusal with `ValidationResult.reason` and the
  rejected SQL printed (transparency).
- Retries exhausted (2) → "I can't answer this safely" + both attempts' errors.
- BigQuery execution errors surfaced with the job error message.

## Testing

- **Unit tests per module**, no live services: Ollama HTTP mocked
  (monkeypatch/responses), BigQuery client stubbed. These are what CI will run.
- **Integration/e2e** marked `@pytest.mark.integration`: 3–4 real Polish
  questions through the full pipeline against live Ollama + BigQuery,
  including one that guardrails MUST reject (e.g. "usuń wszystkie przejazdy")
  and one that exercises the retry cycle if feasible.

## Task split (for the ~/.terminal-agents harness)

| Task | Executor | Scope |
|---|---|---|
| 0 | in-session (before spawning) | `genai/` scaffold + `types.py` contracts + deps + config + pytest markers — committed to the phase branch so wave-1 agents fork with contracts in place |
| 1 | agent, wave 1 | `llm_client.py` + unit tests + Polish learning note |
| 2 | agent, wave 1 | `indexer.py` + `examples.yml` + `retriever.py` + unit tests + learning note |
| 3 | agent, wave 1 | `guardrails.py` + unit tests + learning note |
| 4 | agent, wave 2 | `nl2sql.py` + `pipeline.py` (LangGraph) + `ask.py` CLI + tests; `depends-on` tasks 1–3 |
| 5 | in-session | live e2e run, README offer-map update, final verification before PR |

Wave-1 agents touch no shared files (dependencies land in task 0 — the
lockfile lesson from the harness's MULTI-PROJECT.md). BigQuery contention is
not an issue this phase: only guardrails touch BQ and only via dry-runs +
small SELECTs in integration tests.

## Conventions (binding, as in previous phases)

- ALL code, SQL, prompts-to-model scaffolding comments, and commit messages in
  **English**. User-facing chat strings (answers, refusals) in **Polish**.
- Per task, a Polish learning note under `docs/learn/faza-3-<topic>.md`.
- No AI-attribution footers in commits or PRs.
- Secrets never in the repo; BigQuery auth stays on ADC. Free-tier discipline:
  dry-run gate + `maximum_bytes_billed` on every executed job.
