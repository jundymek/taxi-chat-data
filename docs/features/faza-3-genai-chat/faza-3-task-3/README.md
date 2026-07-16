# faza-3-task-3 — SQL guardrails (`genai/guardrails.py`)

## What was built

`validate(sql, *, max_bytes=config.MAX_SCAN_BYTES, bq_client=None) -> ValidationResult`
— the safety gate every LLM-generated SQL statement must pass before touching
BigQuery. Gates, in order:

1. Parse with sqlglot (BigQuery dialect) — unparseable input rejected.
2. Exactly one statement, and it must be a SELECT (CTEs/UNIONs allowed;
   harmless outer parentheses unwrapped).
3. Every referenced table must be fully qualified as
   `taxi-chat-data.<dataset>.<table>` (missing or foreign project rejected —
   never resolved against the client's default project) and live in an
   allowlisted dataset (`staging`, `marts`); CTE references are excluded
   scope-aware via `sqlglot.optimizer.scope.build_scope` (a real table
   shadowed by a same-named CTE alias is still checked).
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
- `tests/test_guardrails.py` (NEW) — 19 unit tests with a `FakeBQClient`
  stub; no live GCP touched (dry-run flag asserted on the stub). Nine tests
  beyond the plan's 10: dry-run validation errors, missing/foreign project
  qualification, tokenizer failures, CTE-shadowed real tables, parenthesized
  SELECTs (from Codex review findings), plus regex-defeating attack shapes
  (`SELECT 1; DROP ...`, comment-prefixed DELETE, blocked table nested in
  subquery/JOIN) requested by the operator.
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
- Codex review P2 (accepted, fixed): the plan's code only rejected a *wrong*
  project on a table reference, not a *missing* one, so `marts.fct_trips`
  would resolve against the client's default project. Every real table now
  requires the explicit `taxi-chat-data` project.
- Codex review run-3 P1 (accepted, fixed): `sqlglot.parse` can raise
  `TokenError` (unterminated string literal), not only `ParseError`; the
  parse gate now catches the `SqlglotError` base class.
- Codex review run-4 P1 (accepted, fixed): the name-only CTE exemption let
  `WITH trips AS (SELECT * FROM trips) SELECT * FROM trips` smuggle the real
  unqualified inner table through; table resolution is now scope-aware via
  `sqlglot.optimizer.scope.build_scope`.
- Codex review run-5 P2 (accepted, fixed): a query wrapped in outer parens
  parses as `exp.Subquery` and was falsely rejected; now unwrapped before
  the SELECT-only gate.
- Verified against installed sqlglot 30.12.0: 19/19 tests pass, full suite
  34 passed / 1 integration-deselected.
