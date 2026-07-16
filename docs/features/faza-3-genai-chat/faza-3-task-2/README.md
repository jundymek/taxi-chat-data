# Faza 3 / Task 2: RAG layer — Chroma indexer, curated few-shots, retriever

## What was built
The retrieval half of the "chat with data" pipeline. `genai/indexer.py` reads
dbt model YAML files (`dbt/models/**/*__models.yml`) — the single source of
truth about the warehouse schema — and indexes one document per model into an
embedded Chroma database (`data/chroma/`), alongside a second collection of
curated Polish-question → BigQuery-SQL few-shot examples from
`genai/examples.yml`. `genai/retriever.py` embeds an incoming question and
returns the top-k most similar schema docs and examples as a prompt-ready
`SchemaContext` (the Task 0 contract dataclass consumed by Task 4).

## Files touched
- `genai/indexer.py` (NEW) — YAML → docs formatting, full-rebuild index build
  (`build_index`), collection-name constants shared with the retriever;
  runnable as `python -m genai.indexer` (live run deferred to Task 5).
- `genai/examples.yml` (NEW) — 10 hand-curated PL → BigQuery SQL few-shots
  covering counts, aggregates, and every dimension JOIN in the star schema.
- `genai/retriever.py` (NEW) — `Retriever.retrieve(question, k_schema, k_examples)
  -> SchemaContext`, k capped at collection size.
- `tests/test_indexer.py` (NEW, 4 tests) — doc formatting, dataset-prefix
  mapping, YAML loading against tmp fixtures.
- `tests/test_retriever.py` (NEW, 2 tests) — similarity ordering and k-capping
  against a tmp Chroma seeded with a deterministic `FakeEmbedder`.
- `docs/learn/faza-3-rag-retriever.md` (NEW) — Polish learning note (RAG on
  schema, vector DB mechanics, collections, few-shots, DI in tests).
- `docs/tasks/faza-3-task-2.md` (UPDATE) — completion checklist + Dev Agent Record.

## Key decisions
- **Embedder is injected, never imported in tests.** `embedder=None` lazily
  constructs Task 1's `LLMClient` at runtime; unit tests pass a deterministic
  2-d `FakeEmbedder` — no Ollama, no network, type-only coupling to Task 1.
- **Index is rebuilt from scratch** (`delete_collection` + `create_collection`)
  so removed models/examples disappear instead of lingering.
- **Schema docs and few-shots live in separate Chroma collections** so the
  prompt always gets a controlled mix of both (k_schema=4, k_examples=3).
- **Shared plan file left untouched**: Task 2 completion checkboxes are
  tracked in the story file to avoid merge conflicts between wave-1 agents.

## Verification
`.venv/bin/pytest tests/test_indexer.py tests/test_retriever.py -v` → 6 passed;
full unit suite → 21 passed, integration deselected. No live services touched.
