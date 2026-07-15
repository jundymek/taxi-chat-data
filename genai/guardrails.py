"""SQL guardrails: validate generated SQL BEFORE it touches real data.

Order of gates:
1. Parse (sqlglot, BigQuery dialect) — reject unparseable input.
2. Exactly one statement, and it must be a plain SELECT (CTEs allowed).
3. Every referenced table must live in an allowlisted dataset (staging/marts).
4. Enforce a LIMIT (append config.DEFAULT_LIMIT when missing).
5. BigQuery dry-run — reject when the estimated scan exceeds max_bytes.

Reasons are in Polish: they go straight to the user (or back to the model as
retry feedback).
"""
import sqlglot
from sqlglot import exp

from genai import config
from genai.types import ValidationResult


def _reject(sql: str, reason: str, estimated_bytes: int | None = None) -> ValidationResult:
    return ValidationResult(ok=False, sql=sql, reason=reason, estimated_bytes=estimated_bytes)


def validate(sql: str, *, max_bytes: int = config.MAX_SCAN_BYTES, bq_client=None) -> ValidationResult:
    try:
        statements = sqlglot.parse(sql, read="bigquery")
    except sqlglot.errors.ParseError as exc:
        return _reject(sql, f"Nie udało się sparsować SQL: {exc}")

    statements = [s for s in statements if s is not None]
    if len(statements) != 1:
        return _reject(sql, "Dozwolone jest dokładnie jedno zapytanie SQL.")

    statement = statements[0]
    if not isinstance(statement, (exp.Select, exp.Union)):
        return _reject(sql, "Dozwolone są wyłącznie zapytania SELECT (odczyt danych).")

    cte_names = {cte.alias_or_name for cte in statement.find_all(exp.CTE)}
    for table in statement.find_all(exp.Table):
        if table.name in cte_names and not table.db:
            continue  # reference to a CTE, not a real table
        if table.catalog != config.BQ_PROJECT:
            # Missing project would silently resolve against the client's
            # default — require `project.dataset.table`, always.
            return _reject(
                sql,
                f"Tabela {table.sql(dialect='bigquery')} musi być w pełni kwalifikowana "
                f"jako `{config.BQ_PROJECT}.<dataset>.<tabela>`.",
            )
        if table.db not in config.ALLOWED_DATASETS:
            shown = f"{table.db}.{table.name}" if table.db else table.name
            return _reject(
                sql,
                f"Tabela {shown} jest poza dozwolonymi zbiorami danych "
                f"({', '.join(sorted(config.ALLOWED_DATASETS))}).",
            )

    if not statement.args.get("limit"):
        statement = statement.limit(config.DEFAULT_LIMIT)
    final_sql = statement.sql(dialect="bigquery")

    if bq_client is None:
        from google.cloud import bigquery
        bq_client = bigquery.Client(project=config.BQ_PROJECT)
    from google.api_core.exceptions import BadRequest, NotFound
    from google.cloud.bigquery import QueryJobConfig

    try:
        job = bq_client.query(final_sql, job_config=QueryJobConfig(dry_run=True, use_query_cache=False))
    except (BadRequest, NotFound) as exc:
        # Parseable but invalid for BigQuery (hallucinated column/table etc.)
        # is a normal bad-SQL case, not an infrastructure failure.
        return _reject(final_sql, f"BigQuery odrzucił zapytanie: {exc.message or exc}")
    estimated = job.total_bytes_processed
    if estimated is not None and estimated > max_bytes:
        return _reject(
            final_sql,
            f"Zapytanie przeskanowałoby ~{estimated / 1e9:.2f} GB "
            f"(limit: {max_bytes / 1e9:.2f} GB). Doprecyzuj pytanie.",
            estimated_bytes=estimated,
        )

    return ValidationResult(ok=True, sql=final_sql, reason=None, estimated_bytes=estimated)
