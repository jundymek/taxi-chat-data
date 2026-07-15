import pytest
from google.api_core.exceptions import BadRequest, NotFound

from genai.guardrails import validate


class FakeDryRunJob:
    def __init__(self, total_bytes_processed):
        self.total_bytes_processed = total_bytes_processed


class FakeBQClient:
    def __init__(self, dry_run_bytes=1_000):
        self.dry_run_bytes = dry_run_bytes
        self.queries = []

    def query(self, sql, job_config=None):
        assert job_config.dry_run is True
        self.queries.append(sql)
        return FakeDryRunJob(self.dry_run_bytes)


BQ = FakeBQClient


def test_rejects_unparseable_sql():
    result = validate("SELEKT gunk FROM", bq_client=BQ())
    assert not result.ok
    assert result.reason is not None


def test_rejects_sql_that_fails_tokenization():
    """Unterminated string literals raise TokenError (not ParseError) in
    sqlglot — still bad SQL, still a rejection, never an exception."""
    result = validate("SELECT 'unterminated FROM `taxi-chat-data.marts.fct_trips`", bq_client=BQ())
    assert not result.ok
    assert result.reason is not None


def test_rejects_non_select_statements():
    for sql in [
        "DELETE FROM `taxi-chat-data.marts.fct_trips` WHERE true",
        "DROP TABLE `taxi-chat-data.marts.fct_trips`",
        "UPDATE `taxi-chat-data.marts.fct_trips` SET fare_amount = 0 WHERE true",
        "INSERT INTO `taxi-chat-data.marts.fct_trips` (trip_key) VALUES ('x')",
    ]:
        result = validate(sql, bq_client=BQ())
        assert not result.ok, sql
        assert "SELECT" in result.reason


def test_rejects_multiple_statements():
    result = validate("SELECT 1; SELECT 2", bq_client=BQ())
    assert not result.ok


def test_rejects_tables_outside_allowlist():
    result = validate("SELECT * FROM `taxi-chat-data.raw.trips` LIMIT 5", bq_client=BQ())
    assert not result.ok
    assert "raw.trips" in result.reason


def test_rejects_unqualified_tables():
    result = validate("SELECT * FROM fct_trips LIMIT 5", bq_client=BQ())
    assert not result.ok


def test_rejects_tables_missing_explicit_project():
    """`marts.fct_trips` without a project would resolve against whatever
    default project the client is configured with — require full
    qualification so the query is pinned to taxi-chat-data."""
    result = validate("SELECT * FROM marts.fct_trips LIMIT 5", bq_client=BQ())
    assert not result.ok
    assert result.reason is not None


def test_rejects_tables_from_foreign_project():
    result = validate("SELECT * FROM `other-project.marts.fct_trips` LIMIT 5", bq_client=BQ())
    assert not result.ok


def test_accepts_allowlisted_table_and_keeps_existing_limit():
    sql = "SELECT trip_key FROM `taxi-chat-data.marts.fct_trips` LIMIT 7"
    result = validate(sql, bq_client=BQ())
    assert result.ok
    assert "LIMIT 7" in result.sql


def test_appends_default_limit_when_missing():
    result = validate("SELECT trip_key FROM `taxi-chat-data.marts.fct_trips`", bq_client=BQ())
    assert result.ok
    assert "LIMIT 100" in result.sql


def test_allows_cte_names_that_are_not_real_tables():
    sql = (
        "WITH daily AS (SELECT pickup_date, COUNT(*) AS trips "
        "FROM `taxi-chat-data.marts.fct_trips` GROUP BY pickup_date) "
        "SELECT * FROM daily ORDER BY trips DESC"
    )
    result = validate(sql, bq_client=BQ())
    assert result.ok


def test_rejects_real_table_shadowed_by_cte_name():
    """A CTE cannot see itself (no RECURSIVE) — the inner `FROM trips` is a
    real, unqualified table and must NOT be exempted just because a CTE of
    the same name exists."""
    sql = "WITH trips AS (SELECT * FROM trips) SELECT * FROM trips"
    result = validate(sql, bq_client=BQ())
    assert not result.ok


def test_rejects_queries_over_scan_budget():
    client = BQ(dry_run_bytes=5_000_000_000)
    result = validate(
        "SELECT trip_key FROM `taxi-chat-data.marts.fct_trips` LIMIT 5",
        max_bytes=1_000_000_000,
        bq_client=client,
    )
    assert not result.ok
    assert result.estimated_bytes == 5_000_000_000


def test_rejects_sql_that_fails_dry_run_validation():
    """Parseable SQL can still be invalid for BigQuery (hallucinated column,
    missing table) — dry-run raises BadRequest/NotFound and validate() must
    return a rejection, not propagate the exception."""

    class RejectingBQClient:
        def __init__(self, error):
            self.error = error

        def query(self, sql, job_config=None):
            assert job_config.dry_run is True
            raise self.error

    for error in [
        BadRequest("Unrecognized name: no_such_column at [1:8]"),
        NotFound("Not found: Table taxi-chat-data:marts.no_such_table"),
    ]:
        result = validate(
            "SELECT no_such_column FROM `taxi-chat-data.marts.fct_trips` LIMIT 5",
            bq_client=RejectingBQClient(error),
        )
        assert not result.ok
        assert result.reason is not None


def test_reports_estimated_bytes_on_success():
    client = BQ(dry_run_bytes=42)
    result = validate("SELECT 1 FROM `taxi-chat-data.marts.dim_payment` LIMIT 1", bq_client=client)
    assert result.ok
    assert result.estimated_bytes == 42
