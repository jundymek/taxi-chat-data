# faza-3-task-3 — SQL guardrails (`genai/guardrails.py`)

## What was built

`validate(sql, *, max_bytes=config.MAX_SCAN_BYTES, bq_client=None) -> ValidationResult`
— the safety gate every LLM-generated SQL statement must pass before touching
BigQuery. Gates, in order:

1. Parse with sqlglot (BigQuery dialect) — unparseable input rejected.
2. Exactly one statement, and it must be a SELECT (CTEs/UNIONs allowed).
3. Every referenced table must be fully qualified and live in an allowlisted
   dataset (`staging`, `marts`); tables from other GCP projects rejected;
   CTE names correctly excluded from the table check.
4. `LIMIT` enforced — `config.DEFAULT_LIMIT` (100) appended when missing.
5. BigQuery dry-run — query rejected when estimated scan exceeds `max_bytes`
   (default 1 GB); estimate is free (dry-run bills nothing). Dry-run
   `BadRequest`/`NotFound` (hallucinated column/table that parses fine) is
   returned as a rejection, not raised.

Bad SQL never raises — the function always returns a `ValidationResult`
(`ok`, possibly-amended `sql`, Polish `reason`, `estimated_bytes`). Rejection
reasons are Polish because they are shown to the user and fed back to the
model on retry. Exceptions are reserved for infrastructure failures.

## Files

- `genai/guardrails.py` (NEW) — the validator; consumes only `genai.config`,
  `genai.types`, sqlglot, and an injectable BigQuery client.
- `tests/test_guardrails.py` (NEW) — 11 unit tests with a `FakeBQClient`
  stub; no live GCP touched (dry-run flag asserted on the stub). The 11th
  test (beyond the plan's 10) covers dry-run validation errors — added after
  a Codex review P1 finding.
- `docs/learn/faza-3-guardrails.md` (NEW) — Polish learning note (why AST
  over regex, allowlist as least privilege, dry-run economics, verdict-not-
  exception pattern).

## Key decisions

- Implementation follows the phase plan
  (`docs/superpowers/plans/2026-07-15-faza-3-genai-chat.md`, Task 3) verbatim
  — Task 4 depends on this exact `validate` signature and semantics.
- No imports from `llm_client`/`retriever` — task is fully independent of
  wave-1 siblings (tasks 1 and 2).
- Codex review P1 (accepted, fixed): the plan's verbatim code let BigQuery
  semantic errors (`BadRequest`/`NotFound` on dry-run) escape as exceptions,
  violating the "never raises for bad SQL" contract; now caught and returned
  as a Polish rejection. Other exceptions still propagate (infrastructure).
- Verified against installed sqlglot 30.12.0: 11/11 tests pass, full suite
  26 passed / 1 integration-deselected.
