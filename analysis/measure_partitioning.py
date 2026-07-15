"""Measure the BigQuery scan reduction from partitioning + clustering fct_trips.

Runs dry-runs (no execution, no cost) of the same time-range + location query
against the partitioned/clustered fct_trips and an unpartitioned copy, and
writes a before/after report. Uses ADC on the host (not the dbt container).
"""
import os

from google.cloud import bigquery

PROJECT = os.getenv("GCP_PROJECT_ID", "taxi-chat-data")
MARTS = f"{PROJECT}.marts"

# A representative analytical query: trips in a single day from one zone.
QUERY_TEMPLATE = """
SELECT COUNT(*) AS n, SUM(total_amount) AS revenue
FROM `{table}`
WHERE pickup_date = '2023-01-15'
  AND pickup_location_id = 161
"""


def build_unpartitioned_copy(client: bigquery.Client, project: str) -> str:
    """Create marts.fct_trips_unpartitioned (same rows, no partition/cluster)."""
    src = f"{project}.marts.fct_trips"
    dst = f"{project}.marts.fct_trips_unpartitioned"
    client.query(
        f"CREATE OR REPLACE TABLE `{dst}` AS SELECT * FROM `{src}`"
    ).result()
    return dst


def dry_run_bytes(client: bigquery.Client, sql: str) -> int:
    """Return total_bytes_processed for a dry-run of sql (no execution)."""
    job = client.query(
        sql,
        job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False),
    )
    return job.total_bytes_processed


def format_report(part_bytes: int, unpart_bytes: int) -> str:
    """Pure formatter: before/after scan bytes and the percentage reduction."""
    reduction = (1 - part_bytes / unpart_bytes) * 100 if unpart_bytes else 0.0
    return (
        "## Partitioning + clustering scan measurement\n\n"
        f"- Unpartitioned scan (before): {unpart_bytes:,} bytes\n"
        f"- Partitioned + clustered scan (after): {part_bytes:,} bytes\n"
        f"- Reduction: {reduction:.1f}%\n"
    )


def main() -> None:
    client = bigquery.Client(project=PROJECT)
    unpart_id = build_unpartitioned_copy(client, PROJECT)
    part_sql = QUERY_TEMPLATE.format(table=f"{MARTS}.fct_trips")
    unpart_sql = QUERY_TEMPLATE.format(table=unpart_id)
    part_bytes = dry_run_bytes(client, part_sql)
    unpart_bytes = dry_run_bytes(client, unpart_sql)
    report = format_report(part_bytes, unpart_bytes)
    print(report)
    with open("docs/learn/faza-2-partitioning-measurement.md", "w") as f:
        f.write("# Faza 2: Pomiar optymalizacji (partycjonowanie + klasteryzacja)\n\n")
        f.write(report)
        f.write(
            "\n> Zapytanie testowe: przejazdy z jednej strefy w jednym dniu.\n"
            "> Pomiar przez BigQuery dry-run (bez wykonania, bez kosztu skanu).\n"
        )


if __name__ == "__main__":
    main()
