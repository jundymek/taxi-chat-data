# Faza 3 / Task 0: genai scaffold — shared contracts, config, deps

## What was built
The foundation the parallel waves built on, executed in the operator session
BEFORE spawning agents (contracts had to exist on the base branch at fork
time). `genai/types.py` defines the three cross-task contracts (`LLMError`,
`SchemaContext`, `ValidationResult`), `genai/config.py` centralizes paths,
model names, the dataset allowlist, and the cost limits (1 GB scan gate,
LIMIT 100, 3 SQL attempts). New dependencies (`chromadb`, `sqlglot`,
`langgraph`, `pyyaml`) were added here and ONLY here, so no wave-1 agent ever
touched `requirements.txt` — the lockfile lesson from the harness docs.

## Files touched
- `genai/__init__.py` (NEW) — package marker.
- `genai/config.py` (NEW) — paths (`data/chroma/`, dbt models dir), Ollama
  URL + model names, BQ project/datasets, `MAX_SCAN_BYTES`, `DEFAULT_LIMIT`,
  `MAX_SQL_ATTEMPTS`.
- `genai/types.py` (NEW) — contract dataclasses/exception consumed by every
  later task; never redefined downstream.
- `tests/test_genai_types.py` (NEW, 3 tests) — contract shape checks.
- `requirements.txt` (UPDATE) — the four Faza 3 dependencies.

## Key decisions
- **Contracts-first parallelism**: wave-1 tasks (1/2/3) shared zero files and
  agreed only through `types.py` + `config.py`, which is why three agents
  merged with zero conflicts.
- **All limits live in config**, not inline — guardrails, pipeline, and tests
  reference the same constants.

## Verification
- `.venv/bin/pytest tests/test_genai_types.py -v` — 3 passed (TDD: failed with
  `ModuleNotFoundError` first, passed after implementation).
- Committed as `3cc0262` before any agent was spawned.
