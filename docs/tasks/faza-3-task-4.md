# Faza 3 / Task 4: NL2SQL + LangGraph pipeline + CLI (wave 2)

Implement **"Task 4: `nl2sql.py` + `pipeline.py` (LangGraph) + `ask.py` CLI"**
from `docs/superpowers/plans/2026-07-15-faza-3-genai-chat.md`. Read the full
task section AND the plan's "Global Constraints" — both are binding. The plan
contains complete code and TDD steps.

## Dependencies
- REQUIRES tasks 1, 2, 3 merged into your branch. If wave-1 agents are still
  running, set `~/.terminal-agents/scripts/set-depends-on.sh <agent>:committed`
  for each and wait; make sure your worktree actually contains
  `genai/llm_client.py`, `genai/retriever.py`, and `genai/guardrails.py`
  before starting (rebase on the updated base branch if needed).
- Unit tests use fakes for LLM/retriever/BQ (see plan) — no live services.
  The integration file `tests/test_e2e_integration.py` is WRITTEN here but only
  RUN in Task 5 (it stays deselected by default).

## Done when
- `.venv/bin/pytest -v` — full unit suite green, integration deselected.
- `.venv/bin/python -m genai.ask --help` prints usage.
- `docs/learn/faza-3-langgraph-nl2sql.md` (Polish learning note) written.
