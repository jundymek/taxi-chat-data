# Faza 4: Simulated streaming with real Pub/Sub — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Harness note:** Tasks 1 and 2 run as a COHORT of two parallel agents —
> they share message *semantics*, not files. Both MUST intent-sync before
> coding (declare their reading of the contract: NULL serialization, timestamp
> format, dup-inject semantics) and use `agent-msg.sh` for contract questions
> instead of guessing. Tasks 0 and 3 run in the operator session.

**Goal:** `python -m ingestion.stream_producer` replays the local Parquet into
Pub/Sub topic `trips-stream` with throttling and deliberate duplicates;
`python -m ingestion.stream_consumer` writes them to BigQuery `stream.trips`
via streaming inserts with `insertId` dedup — at-least-once demonstrated live.

**Architecture:** two thin CLIs in `ingestion/` sharing a message contract
module (`stream_common.py`), mirroring the existing env-driven `Config` +
idempotent `ensure_*` patterns from Faza 1. Design/spec:
`docs/superpowers/specs/2026-07-16-faza-4-streaming-pubsub-design.md`.

**Tech Stack:** Python 3 in the existing `.venv`, google-cloud-pubsub,
google-cloud-bigquery (installed), pyarrow (installed), pytest.

## Global Constraints

- ALL code, comments, and commit messages in **ENGLISH** (this is infra — no
  Polish user-facing strings here). Per agent task: a Polish learning note
  under `docs/learn/faza-4-<topic>.md` AND a feature record under
  `docs/features/faza-4-streaming-pubsub/<task-id>/README.md` (sections:
  What was built / Files touched / Key decisions / Verification). No
  AI-attribution footers.
- Secrets never in the repo; GCP auth = ADC. Project `taxi-chat-data`, US.
- Unit tests must NOT touch live GCP (fake publisher/subscriber/BQ clients);
  live checks are `@pytest.mark.integration`, run only in Task 3.
- Cost discipline: streaming inserts are billable (~$0.05/GB) — the default
  100k-row sample costs cents; note it in the runbook. No other billable
  surfaces. Dry-run/`--limit` flags default LOW.
- New dependency (Task 0 ONLY — no other task edits `requirements.txt`):
  `google-cloud-pubsub`.
- Tasks 1 and 2 must not modify any file outside their **Files** list; shared
  concerns are already in Task 0's contract. Contract questions → `agent-msg.sh`
  to the cohort peer, NOT unilateral reinterpretation.
- Python in the existing `.venv`: `.venv/bin/python`, `.venv/bin/pytest`.

---

## File Structure

```
ingestion/
├── stream_common.py       # Task 0 — THE contract: fields, trip_key, codecs, ensure_*, StreamConfig
├── stream_producer.py     # Task 1 — Parquet → Pub/Sub (--limit, --rate, --dup-rate)
└── stream_consumer.py     # Task 2 — Pub/Sub → BigQuery streaming inserts
tests/
├── test_stream_common.py  # Task 0
├── test_stream_producer.py# Task 1
└── test_stream_consumer.py# Task 2
docs/learn/
├── faza-4-pubsub-producer.md   # Task 1 (Polish)
└── faza-4-pubsub-consumer.md   # Task 2 (Polish)
docs/features/faza-4-streaming-pubsub/
├── faza-4-task-0/README.md ... faza-4-task-3/README.md (per task)
.env.example                # Task 0 — stream variables
requirements.txt            # Task 0 — google-cloud-pubsub
```

---

## Task 0: `stream_common.py` — message contract, resources, config (in-session, BEFORE spawning)

**Files:**
- Create: `ingestion/stream_common.py`
- Test: `tests/test_stream_common.py`
- Modify: `requirements.txt` (append `google-cloud-pubsub>=2.21`)
- Modify: `.env.example` (append stream section)

**Interfaces:**
- Consumes: `ingestion.config.load_config` / `Config` (existing).
- Produces (Tasks 1–3 rely on EXACTLY this):
  - `MESSAGE_FIELDS: tuple[str, ...]` — the 19 parquet trip columns, fixed order
  - `SURROGATE_KEY_FIELDS: tuple[str, ...]` — the 6 dbt surrogate-key columns
  - `compute_trip_key(row: dict) -> str` — MD5 hex, dbt_utils-compatible
  - `row_to_message(row: dict) -> bytes` — JSON; raises `KeyError` on missing field
  - `message_to_bq_row(data: bytes) -> dict` — raises `ValueError` on bad payload
  - `ensure_stream_resources(cfg: StreamConfig) -> None` — idempotent
  - `StreamConfig` dataclass + `load_stream_config() -> StreamConfig`
    (fields: all of `Config` + `topic`, `subscription`, `dataset_stream`)

- [ ] **Step 1: Write the failing contract tests**

`tests/test_stream_common.py`:
```python
import json

import pytest

from ingestion.stream_common import (
    MESSAGE_FIELDS,
    SURROGATE_KEY_FIELDS,
    compute_trip_key,
    message_to_bq_row,
    row_to_message,
)
from datetime import datetime, timezone

SAMPLE_ROW = {
    "VendorID": 1,
    "tpep_pickup_datetime": datetime(2023, 1, 1, 0, 32, 10, tzinfo=timezone.utc),
    "tpep_dropoff_datetime": datetime(2023, 1, 1, 0, 40, 36, tzinfo=timezone.utc),
    "passenger_count": 1.0,
    "trip_distance": 0.97,
    "RatecodeID": 1.0,
    "store_and_fwd_flag": "N",
    "PULocationID": 161,
    "DOLocationID": 141,
    "payment_type": 2,
    "fare_amount": 9.3,
    "extra": 1.0,
    "mta_tax": 0.5,
    "tip_amount": 0.0,
    "tolls_amount": 0.0,
    "improvement_surcharge": 1.0,
    "total_amount": 14.3,
    "congestion_surcharge": 2.5,
    "airport_fee": 0.0,
}

# Pinned during Task 0 against live BigQuery (see Step 5) — the exact value
# dbt_utils.generate_surrogate_key produces for SAMPLE_ROW's key columns.
GOLDEN_TRIP_KEY = "PINNED-IN-STEP-5"


def test_message_fields_cover_the_parquet_schema():
    assert len(MESSAGE_FIELDS) == 19
    assert set(SURROGATE_KEY_FIELDS) <= set(MESSAGE_FIELDS)


def test_trip_key_is_deterministic_and_hex():
    k1, k2 = compute_trip_key(SAMPLE_ROW), compute_trip_key(dict(SAMPLE_ROW))
    assert k1 == k2
    assert len(k1) == 32 and int(k1, 16) >= 0


def test_trip_key_matches_dbt_golden_value():
    assert compute_trip_key(SAMPLE_ROW) == GOLDEN_TRIP_KEY


def test_row_message_roundtrip():
    payload = row_to_message(SAMPLE_ROW)
    bq_row = message_to_bq_row(payload)
    assert bq_row["trip_key"] == compute_trip_key(SAMPLE_ROW)
    assert bq_row["pickup_datetime"] == "2023-01-01T00:32:10+00:00"
    assert bq_row["fare_amount"] == 9.3
    assert bq_row["vendor_id"] == 1


def test_row_to_message_serializes_none_explicitly():
    row = dict(SAMPLE_ROW, airport_fee=None)
    decoded = json.loads(row_to_message(row))
    assert decoded["airport_fee"] is None


def test_message_to_bq_row_rejects_missing_trip_key():
    with pytest.raises(ValueError):
        message_to_bq_row(json.dumps({"fare_amount": 1.0}).encode())


def test_message_to_bq_row_rejects_non_json():
    with pytest.raises(ValueError):
        message_to_bq_row(b"not-json")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_stream_common.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ingestion.stream_common'`

- [ ] **Step 3: Implement `ingestion/stream_common.py`**

```python
"""Shared contract for the streaming path (Faza 4).

The producer and consumer live in separate modules (and were built by
separate agents); everything they must agree on lives HERE: the message
field set, the trip_key recipe (dbt-compatible), the JSON codec, resource
names, and idempotent resource creation.
"""
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime

from google.api_core.exceptions import AlreadyExists
from google.cloud import bigquery, pubsub_v1

from ingestion.config import Config, load_config

# The 19 columns of yellow_tripdata parquet / raw.trips, fixed order.
MESSAGE_FIELDS: tuple[str, ...] = (
    "VendorID", "tpep_pickup_datetime", "tpep_dropoff_datetime",
    "passenger_count", "trip_distance", "RatecodeID", "store_and_fwd_flag",
    "PULocationID", "DOLocationID", "payment_type", "fare_amount", "extra",
    "mta_tax", "tip_amount", "tolls_amount", "improvement_surcharge",
    "total_amount", "congestion_surcharge", "airport_fee",
)

# Same columns and order as dbt_utils.generate_surrogate_key in stg_trips.
SURROGATE_KEY_FIELDS: tuple[str, ...] = (
    "tpep_pickup_datetime", "tpep_dropoff_datetime",
    "PULocationID", "DOLocationID", "fare_amount", "VendorID",
)

# dbt_utils.generate_surrogate_key null sentinel (verbatim).
_NULL_SENTINEL = "_dbt_utils_surrogate_key_null_"

# Column rename map: parquet name -> stream.trips column name (mirrors stg_trips).
_BQ_COLUMNS: dict[str, str] = {
    "VendorID": "vendor_id",
    "tpep_pickup_datetime": "pickup_datetime",
    "tpep_dropoff_datetime": "dropoff_datetime",
    "passenger_count": "passenger_count",
    "trip_distance": "trip_distance",
    "RatecodeID": "ratecode_id",
    "store_and_fwd_flag": "store_and_fwd_flag",
    "PULocationID": "pickup_location_id",
    "DOLocationID": "dropoff_location_id",
    "payment_type": "payment_type",
    "fare_amount": "fare_amount",
    "extra": "extra",
    "mta_tax": "mta_tax",
    "tip_amount": "tip_amount",
    "tolls_amount": "tolls_amount",
    "improvement_surcharge": "improvement_surcharge",
    "total_amount": "total_amount",
    "congestion_surcharge": "congestion_surcharge",
    "airport_fee": "airport_fee",
}


def _bq_string(value) -> str:
    """Render a value the way BigQuery CAST(x AS STRING) does — trip_key must
    hash the SAME text dbt hashes. Calibrated against live BQ in Task 0."""
    if value is None:
        return _NULL_SENTINEL
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S+00")
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def compute_trip_key(row: dict) -> str:
    joined = "-".join(_bq_string(row[f]) for f in SURROGATE_KEY_FIELDS)
    return hashlib.md5(joined.encode("utf-8")).hexdigest()


def row_to_message(row: dict) -> bytes:
    payload = {}
    for field in MESSAGE_FIELDS:
        value = row[field]  # KeyError on missing field is intentional
        if isinstance(value, datetime):
            value = value.isoformat()
        payload[field] = value
    payload["trip_key"] = compute_trip_key(row)
    return json.dumps(payload).encode("utf-8")


def message_to_bq_row(data: bytes) -> dict:
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Malformed message payload: {exc}") from exc
    missing = [f for f in (*MESSAGE_FIELDS, "trip_key") if f not in payload]
    if missing:
        raise ValueError(f"Message missing fields: {missing}")
    row = {_BQ_COLUMNS[f]: payload[f] for f in MESSAGE_FIELDS}
    row["trip_key"] = payload["trip_key"]
    return row


@dataclass
class StreamConfig(Config):
    topic: str = "trips-stream"
    subscription: str = "trips-stream-sub"
    dataset_stream: str = "stream"


def load_stream_config() -> StreamConfig:
    base = load_config()
    return StreamConfig(
        **vars(base),
        topic=os.getenv("PUBSUB_TOPIC", "trips-stream"),
        subscription=os.getenv("PUBSUB_SUBSCRIPTION", "trips-stream-sub"),
        dataset_stream=os.getenv("BQ_DATASET_STREAM", "stream"),
    )


_TABLE_SCHEMA = [
    bigquery.SchemaField("trip_key", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("vendor_id", "INT64"),
    bigquery.SchemaField("pickup_datetime", "TIMESTAMP"),
    bigquery.SchemaField("dropoff_datetime", "TIMESTAMP"),
    bigquery.SchemaField("passenger_count", "FLOAT64"),
    bigquery.SchemaField("trip_distance", "FLOAT64"),
    bigquery.SchemaField("ratecode_id", "FLOAT64"),
    bigquery.SchemaField("store_and_fwd_flag", "STRING"),
    bigquery.SchemaField("pickup_location_id", "INT64"),
    bigquery.SchemaField("dropoff_location_id", "INT64"),
    bigquery.SchemaField("payment_type", "INT64"),
    bigquery.SchemaField("fare_amount", "FLOAT64"),
    bigquery.SchemaField("extra", "FLOAT64"),
    bigquery.SchemaField("mta_tax", "FLOAT64"),
    bigquery.SchemaField("tip_amount", "FLOAT64"),
    bigquery.SchemaField("tolls_amount", "FLOAT64"),
    bigquery.SchemaField("improvement_surcharge", "FLOAT64"),
    bigquery.SchemaField("total_amount", "FLOAT64"),
    bigquery.SchemaField("congestion_surcharge", "FLOAT64"),
    bigquery.SchemaField("airport_fee", "FLOAT64"),
    bigquery.SchemaField("ingested_at", "TIMESTAMP"),
]


def ensure_stream_resources(cfg: StreamConfig) -> None:
    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(cfg.project_id, cfg.topic)
    try:
        publisher.create_topic(name=topic_path)
        print(f"[pubsub] created topic {topic_path}")
    except AlreadyExists:
        print(f"[pubsub] topic {cfg.topic} already exists")

    subscriber = pubsub_v1.SubscriberClient()
    sub_path = subscriber.subscription_path(cfg.project_id, cfg.subscription)
    try:
        subscriber.create_subscription(
            name=sub_path, topic=topic_path, ack_deadline_seconds=30
        )
        print(f"[pubsub] created subscription {sub_path}")
    except AlreadyExists:
        print(f"[pubsub] subscription {cfg.subscription} already exists")

    bq = bigquery.Client(project=cfg.project_id)
    dataset = bigquery.Dataset(f"{cfg.project_id}.{cfg.dataset_stream}")
    dataset.location = cfg.location
    bq.create_dataset(dataset, exists_ok=True)
    table = bigquery.Table(
        f"{cfg.project_id}.{cfg.dataset_stream}.trips", schema=_TABLE_SCHEMA
    )
    bq.create_table(table, exists_ok=True)
    print(f"[bq] ensured {cfg.dataset_stream}.trips")
```

Note: `test_row_message_roundtrip` asserts renamed columns (`vendor_id`,
`pickup_datetime`) — `message_to_bq_row` returns stg_trips-style names so
`stream.trips` reads naturally next to the warehouse.

- [ ] **Step 4: Add dependency + env template, install**

`requirements.txt`: append `google-cloud-pubsub>=2.21`.
`.env.example`: append
```
# Streaming (Faza 4)
PUBSUB_TOPIC=trips-stream
PUBSUB_SUBSCRIPTION=trips-stream-sub
BQ_DATASET_STREAM=stream
```
Run: `.venv/bin/pip install -r requirements.txt`

- [ ] **Step 5: Calibrate the golden trip_key against live BigQuery (one free dry query)**

`_bq_string` mimics BigQuery's CAST semantics, which must not be guessed.
Run this ONE query (bytes: 0 — pure expression) and compare with Python:

```bash
bq query --use_legacy_sql=false --format=csv "SELECT to_hex(md5(concat(
  coalesce(cast(timestamp '2023-01-01 00:32:10+00' as string), '_dbt_utils_surrogate_key_null_'), '-',
  coalesce(cast(timestamp '2023-01-01 00:40:36+00' as string), '_dbt_utils_surrogate_key_null_'), '-',
  coalesce(cast(161 as string), '_dbt_utils_surrogate_key_null_'), '-',
  coalesce(cast(141 as string), '_dbt_utils_surrogate_key_null_'), '-',
  coalesce(cast(9.3 as string), '_dbt_utils_surrogate_key_null_'), '-',
  coalesce(cast(1 as string), '_dbt_utils_surrogate_key_null_')) )) AS k"
.venv/bin/python -c "from ingestion.stream_common import compute_trip_key; \
from tests.test_stream_common import SAMPLE_ROW; print(compute_trip_key(SAMPLE_ROW))"
```

If they differ, adjust `_bq_string` (timestamp/float rendering) until they
match, then pin the value into `GOLDEN_TRIP_KEY` in the test. Also spot-check
one real row: `SELECT trip_key FROM staging.stg_trips LIMIT 1` with its source
columns and reproduce it in Python.

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_stream_common.py -v`
Expected: 7 PASS

- [ ] **Step 7: Commit**

```bash
git add ingestion/stream_common.py tests/test_stream_common.py requirements.txt .env.example
git commit -m "feat: streaming contract — message codec, dbt-compatible trip_key, resource ensure (Faza 4 task 0)"
```

Also write `docs/features/faza-4-streaming-pubsub/faza-4-task-0/README.md`
(What was built / Files touched / Key decisions — incl. the calibration story /
Verification) and commit it with the same message amended or a follow-up
`docs:` commit.

---

## Task 1: `stream_producer.py` — Parquet → Pub/Sub (wave 1, agent, cohort with Task 2)

**Files:**
- Create: `ingestion/stream_producer.py`
- Test: `tests/test_stream_producer.py`
- Create: `docs/learn/faza-4-pubsub-producer.md` (Polish learning note)
- Create: `docs/features/faza-4-streaming-pubsub/faza-4-task-1/README.md`

**Interfaces:**
- Consumes (Task 0, exact): `MESSAGE_FIELDS`, `row_to_message(row) -> bytes`,
  `compute_trip_key(row) -> str`, `load_stream_config() -> StreamConfig`
  (`cfg.topic`, `cfg.project_id`, `cfg.data_dir`, `cfg.taxi_month`).
- Produces: CLI `python -m ingestion.stream_producer [--limit N] [--rate R]
  [--dup-rate P] [--month YYYY-MM]`; library function
  `replay(cfg, publisher, limit, rate, dup_rate, rng) -> dict` returning
  `{"published": int, "duplicates": int}` (the dict contract is what tests
  and Task 3's runbook rely on).
- Cohort duty: before coding, write `intent.md` declaring your reading of the
  contract (NULL handling, timestamp serialization, what a duplicate IS: same
  bytes, same trip_key, published twice) and sync with the consumer agent.

- [ ] **Step 1: Write the failing tests**

`tests/test_stream_producer.py`:
```python
import json

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from ingestion.stream_common import MESSAGE_FIELDS, StreamConfig
from ingestion.stream_producer import replay


class FakeFuture:
    def result(self, timeout=None):
        return "msg-id"


class FakePublisher:
    def __init__(self):
        self.published = []

    def topic_path(self, project, topic):
        return f"projects/{project}/topics/{topic}"

    def publish(self, topic_path, data, **attrs):
        self.published.append((topic_path, data, attrs))
        return FakeFuture()


class FixedRng:
    """random() returns values from a fixed script, then 1.0 (never duplicate)."""

    def __init__(self, script=()):
        self.script = list(script)

    def random(self):
        return self.script.pop(0) if self.script else 1.0


@pytest.fixture()
def parquet_file(tmp_path):
    rows = {
        "VendorID": [1, 2, 1],
        "tpep_pickup_datetime": [1672531200000000, 1672531260000000, 1672531320000000],
        "tpep_dropoff_datetime": [1672531800000000, 1672531860000000, 1672531920000000],
        "passenger_count": [1.0, 2.0, None],
        "trip_distance": [0.9, 1.2, 3.4],
        "RatecodeID": [1.0, 1.0, 2.0],
        "store_and_fwd_flag": ["N", "N", "Y"],
        "PULocationID": [161, 43, 100],
        "DOLocationID": [141, 237, 200],
        "payment_type": [2, 1, 1],
        "fare_amount": [9.3, 12.1, 33.0],
        "extra": [1.0, 0.0, 0.0],
        "mta_tax": [0.5, 0.5, 0.5],
        "tip_amount": [0.0, 2.0, 5.0],
        "tolls_amount": [0.0, 0.0, 6.55],
        "improvement_surcharge": [1.0, 1.0, 1.0],
        "total_amount": [14.3, 16.1, 46.05],
        "congestion_surcharge": [2.5, 2.5, 2.5],
        "airport_fee": [0.0, 0.0, 1.25],
    }
    # Let pyarrow infer types, but force the timestamp columns (µs since epoch).
    table = pa.table(
        {
            k: (pa.array(v, type=pa.timestamp("us", tz="UTC")) if "datetime" in k else v)
            for k, v in rows.items()
        }
    )
    path = tmp_path / "yellow_tripdata_2023-01.parquet"
    pq.write_table(table, path)
    return tmp_path


def _cfg(data_dir) -> StreamConfig:
    return StreamConfig(
        project_id="test-project", bucket="b", dataset_raw="raw", location="US",
        data_dir=str(data_dir), taxi_month="2023-01",
    )


def test_replay_publishes_limit_rows_with_trip_key_attribute(parquet_file):
    pub = FakePublisher()
    stats = replay(_cfg(parquet_file), pub, limit=2, rate=0, dup_rate=0.0, rng=FixedRng())
    assert stats == {"published": 2, "duplicates": 0}
    assert len(pub.published) == 2
    _, data, attrs = pub.published[0]
    payload = json.loads(data)
    assert set(MESSAGE_FIELDS) <= set(payload)
    assert attrs["trip_key"] == payload["trip_key"]
    assert attrs["source"] == "replay"


def test_replay_injects_duplicates_as_identical_bytes(parquet_file):
    pub = FakePublisher()
    stats = replay(
        _cfg(parquet_file), pub, limit=3, rate=0, dup_rate=0.5,
        rng=FixedRng([0.1, 0.9, 0.9]),  # only row 1 duplicated
    )
    assert stats == {"published": 3, "duplicates": 1}
    assert len(pub.published) == 4
    assert pub.published[0][1] == pub.published[1][1]  # same bytes


def test_replay_missing_parquet_gives_hint(tmp_path):
    with pytest.raises(FileNotFoundError, match="ingestion.download"):
        replay(_cfg(tmp_path), FakePublisher(), limit=1, rate=0, dup_rate=0.0, rng=FixedRng())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_stream_producer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ingestion.stream_producer'`

- [ ] **Step 3: Implement `ingestion/stream_producer.py`**

```python
"""Replay the local Parquet into Pub/Sub, simulating a live feed.

Usage:
    python -m ingestion.stream_producer [--limit 100000] [--rate 500]
                                        [--dup-rate 0.01] [--month 2023-01]

--dup-rate deliberately re-publishes some messages (identical bytes, same
trip_key) so the at-least-once + dedup story is demonstrable downstream.
"""
import argparse
import os
import random
import sys
import time

import pyarrow.parquet as pq
from google.cloud import pubsub_v1

from ingestion.stream_common import load_stream_config, row_to_message, compute_trip_key

_BATCH_ROWS = 1000  # pyarrow read granularity; independent from --rate


def _parquet_path(cfg) -> str:
    path = os.path.join(cfg.data_dir, f"yellow_tripdata_{cfg.taxi_month}.parquet")
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{path} not found — run `python -m ingestion.download` first"
        )
    return path


def replay(cfg, publisher, limit: int, rate: float, dup_rate: float, rng) -> dict:
    topic_path = publisher.topic_path(cfg.project_id, cfg.topic)
    parquet = pq.ParquetFile(_parquet_path(cfg))
    published = duplicates = 0
    started = time.monotonic()
    futures = []
    for batch in parquet.iter_batches(batch_size=_BATCH_ROWS):
        for row in batch.to_pylist():
            if published >= limit:
                break
            data = row_to_message(row)
            attrs = {"trip_key": compute_trip_key(row), "source": "replay"}
            futures.append(publisher.publish(topic_path, data, **attrs))
            published += 1
            if rng.random() < dup_rate:
                futures.append(publisher.publish(topic_path, data, **attrs))
                duplicates += 1
            if rate > 0:
                # keep the average publish rate at `rate` msg/s
                expected_elapsed = published / rate
                sleep_for = expected_elapsed - (time.monotonic() - started)
                if sleep_for > 0:
                    time.sleep(sleep_for)
        if published >= limit:
            break
    for future in futures:
        future.result(timeout=60)
    return {"published": published, "duplicates": duplicates}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Replay Parquet trips into Pub/Sub.")
    parser.add_argument("--limit", type=int, default=100_000)
    parser.add_argument("--rate", type=float, default=500.0, help="msg/s; 0 = unthrottled")
    parser.add_argument("--dup-rate", type=float, default=0.01)
    parser.add_argument("--month", default=None, help="override TAXI_MONTH (YYYY-MM)")
    args = parser.parse_args(argv)

    cfg = load_stream_config()
    if args.month:
        cfg.taxi_month = args.month
    publisher = pubsub_v1.PublisherClient()
    started = time.monotonic()
    try:
        stats = replay(cfg, publisher, args.limit, args.rate, args.dup_rate, random)
    except KeyboardInterrupt:
        print("\n[producer] interrupted — pending publishes flushed by client")
        return 130
    elapsed = time.monotonic() - started
    print(
        f"[producer] published={stats['published']} duplicates={stats['duplicates']} "
        f"elapsed={elapsed:.1f}s rate={stats['published'] / max(elapsed, 0.001):.0f} msg/s"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_stream_producer.py -v`
Expected: 3 PASS. Also run the full suite: `.venv/bin/pytest` — all green.

- [ ] **Step 5: Write the Polish learning note**

`docs/learn/faza-4-pubsub-producer.md` (po polsku, ~60–100 linii): czym jest
Pub/Sub (topic, subskrypcja, at-least-once z natury), czemu publish zwraca
future i co daje zbieranie futures + `result()` (potwierdzenia), po co
throttling przy symulacji live, czemu duplikaty wstrzykujemy CELOWO (inaczej
"nauka dedupu" byłaby teorią), atrybuty wiadomości vs payload.

- [ ] **Step 6: Write the feature record**

`docs/features/faza-4-streaming-pubsub/faza-4-task-1/README.md` — sections:
What was built / Files touched / Key decisions / Verification (test output).

- [ ] **Step 7: Commit**

```bash
git add ingestion/stream_producer.py tests/test_stream_producer.py \
        docs/learn/faza-4-pubsub-producer.md \
        docs/features/faza-4-streaming-pubsub/faza-4-task-1/README.md
git commit -m "feat(faza-4-task-1): Pub/Sub producer — throttled Parquet replay with duplicate injection"
```

---

## Task 2: `stream_consumer.py` — Pub/Sub → BigQuery (wave 1, agent, cohort with Task 1)

**Files:**
- Create: `ingestion/stream_consumer.py`
- Test: `tests/test_stream_consumer.py`
- Create: `docs/learn/faza-4-pubsub-consumer.md` (Polish learning note)
- Create: `docs/features/faza-4-streaming-pubsub/faza-4-task-2/README.md`

**Interfaces:**
- Consumes (Task 0, exact): `message_to_bq_row(data) -> dict` (raises
  `ValueError`), `load_stream_config()` (`cfg.subscription`, `cfg.project_id`,
  `cfg.dataset_stream`).
- Produces: CLI `python -m ingestion.stream_consumer [--batch-size 500]
  [--max-seconds 2] [--idle-timeout 30]`; class
  `BatchWriter(bq_client, table_id, batch_size)` with methods
  `add(message) -> None` and `flush() -> None`, attributes
  `inserted, rejected, seen: int` (Task 3's runbook reads these counters from
  the final summary line).
- Cohort duty: before coding, write `intent.md` declaring your reading of the
  contract (what you ack vs nack, how you use `trip_key` as insertId, malformed
  handling) and sync with the producer agent; ask contract questions via
  `agent-msg.sh`, don't guess.

- [ ] **Step 1: Write the failing tests**

`tests/test_stream_consumer.py`:
```python
import json
from datetime import datetime, timezone

import pytest

from ingestion.stream_common import row_to_message
from ingestion.stream_consumer import BatchWriter

ROW = {
    "VendorID": 1,
    "tpep_pickup_datetime": datetime(2023, 1, 1, 0, 32, 10, tzinfo=timezone.utc),
    "tpep_dropoff_datetime": datetime(2023, 1, 1, 0, 40, 36, tzinfo=timezone.utc),
    "passenger_count": 1.0, "trip_distance": 0.97, "RatecodeID": 1.0,
    "store_and_fwd_flag": "N", "PULocationID": 161, "DOLocationID": 141,
    "payment_type": 2, "fare_amount": 9.3, "extra": 1.0, "mta_tax": 0.5,
    "tip_amount": 0.0, "tolls_amount": 0.0, "improvement_surcharge": 1.0,
    "total_amount": 14.3, "congestion_surcharge": 2.5, "airport_fee": 0.0,
}


class FakeMessage:
    def __init__(self, data: bytes):
        self.data = data
        self.acked = False
        self.nacked = False

    def ack(self):
        self.acked = True

    def nack(self):
        self.nacked = True


class FakeBQ:
    def __init__(self, errors=None):
        self.errors = errors or []
        self.calls = []

    def insert_rows_json(self, table_id, rows, row_ids=None):
        self.calls.append((table_id, rows, row_ids))
        return self.errors


def test_flushes_when_batch_size_reached_acks_and_uses_trip_key_as_insert_id():
    bq = FakeBQ()
    writer = BatchWriter(bq, "p.stream.trips", batch_size=2)
    m1, m2 = FakeMessage(row_to_message(ROW)), FakeMessage(row_to_message(ROW))
    writer.add(m1)
    assert bq.calls == []          # below batch size — no flush yet
    writer.add(m2)
    assert len(bq.calls) == 1      # size trigger
    table_id, rows, row_ids = bq.calls[0]
    assert row_ids == [rows[0]["trip_key"], rows[1]["trip_key"]]
    assert rows[0]["ingested_at"].endswith("Z") or "+" in rows[0]["ingested_at"]
    assert m1.acked and m2.acked and not m1.nacked


def test_insert_errors_nack_the_whole_batch():
    bq = FakeBQ(errors=[{"index": 0, "errors": [{"reason": "invalid"}]}])
    writer = BatchWriter(bq, "p.stream.trips", batch_size=1)
    msg = FakeMessage(row_to_message(ROW))
    writer.add(msg)
    assert msg.nacked and not msg.acked
    assert writer.inserted == 0


def test_malformed_message_is_acked_and_counted_rejected():
    bq = FakeBQ()
    writer = BatchWriter(bq, "p.stream.trips", batch_size=1)
    bad = FakeMessage(b"not-json")
    writer.add(bad)
    assert bad.acked                # skip, don't redeliver forever
    assert writer.rejected == 1
    assert bq.calls == []           # nothing buffered


def test_explicit_flush_drains_partial_buffer():
    bq = FakeBQ()
    writer = BatchWriter(bq, "p.stream.trips", batch_size=100)
    msg = FakeMessage(row_to_message(ROW))
    writer.add(msg)
    writer.flush()
    assert len(bq.calls) == 1 and msg.acked
    assert writer.inserted == 1 and writer.seen == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_stream_consumer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ingestion.stream_consumer'`

- [ ] **Step 3: Implement `ingestion/stream_consumer.py`**

```python
"""Consume trip messages from Pub/Sub and stream them into BigQuery.

Usage:
    python -m ingestion.stream_consumer [--batch-size 500] [--max-seconds 2]
                                        [--idle-timeout 30]

Semantics (at-least-once):
- ack ONLY after a successful insert_rows_json for the whole buffered batch;
- any insert error → nack the whole batch → Pub/Sub redelivers → BigQuery
  insertId (trip_key) de-duplicates the rows that DID land;
- malformed payload → log + ack + `rejected` counter (conscious simplicity —
  no dead-letter topic in this phase).
"""
import argparse
import sys
import threading
import time
from datetime import datetime, timezone

from google.cloud import bigquery, pubsub_v1

from ingestion.stream_common import load_stream_config, message_to_bq_row


class BatchWriter:
    def __init__(self, bq_client, table_id: str, batch_size: int = 500):
        self._bq = bq_client
        self._table_id = table_id
        self._batch_size = batch_size
        self._lock = threading.Lock()
        self._rows: list[dict] = []
        self._messages: list = []
        self.seen = 0
        self.inserted = 0
        self.rejected = 0

    def add(self, message) -> None:
        with self._lock:
            self.seen += 1
            try:
                row = message_to_bq_row(message.data)
            except ValueError as exc:
                print(f"[consumer] rejected malformed message: {exc}")
                self.rejected += 1
                message.ack()
                return
            row["ingested_at"] = datetime.now(timezone.utc).isoformat()
            self._rows.append(row)
            self._messages.append(message)
            if len(self._rows) >= self._batch_size:
                self._flush_locked()

    def flush(self) -> None:
        with self._lock:
            self._flush_locked()

    def _flush_locked(self) -> None:
        if not self._rows:
            return
        rows, messages = self._rows, self._messages
        self._rows, self._messages = [], []
        row_ids = [row["trip_key"] for row in rows]
        errors = self._bq.insert_rows_json(self._table_id, rows, row_ids=row_ids)
        if errors:
            print(f"[consumer] insert errors ({len(errors)}) — nacking batch of {len(rows)}")
            for message in messages:
                message.nack()
            return
        for message in messages:
            message.ack()
        self.inserted += len(rows)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Pub/Sub → BigQuery stream.trips consumer.")
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--max-seconds", type=float, default=2.0,
                        help="flush a partial buffer after this many seconds")
    parser.add_argument("--idle-timeout", type=float, default=30.0,
                        help="exit after this many seconds without any message")
    args = parser.parse_args(argv)

    cfg = load_stream_config()
    table_id = f"{cfg.project_id}.{cfg.dataset_stream}.trips"
    writer = BatchWriter(bigquery.Client(project=cfg.project_id), table_id, args.batch_size)

    subscriber = pubsub_v1.SubscriberClient()
    sub_path = subscriber.subscription_path(cfg.project_id, cfg.subscription)
    last_seen = time.monotonic()

    def callback(message):
        nonlocal last_seen
        last_seen = time.monotonic()
        writer.add(message)

    flow = pubsub_v1.types.FlowControl(max_messages=1000)
    future = subscriber.subscribe(sub_path, callback=callback, flow_control=flow)
    print(f"[consumer] listening on {sub_path} → {table_id}")
    try:
        while True:
            time.sleep(args.max_seconds)
            writer.flush()
            if time.monotonic() - last_seen > args.idle_timeout:
                print(f"[consumer] idle for {args.idle_timeout}s — shutting down")
                break
    except KeyboardInterrupt:
        print("\n[consumer] interrupted")
    finally:
        future.cancel()
        future.result()
        writer.flush()
        print(
            f"[consumer] seen={writer.seen} inserted={writer.inserted} "
            f"rejected={writer.rejected}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_stream_consumer.py -v`
Expected: 4 PASS. Also run the full suite: `.venv/bin/pytest` — all green.

- [ ] **Step 5: Write the Polish learning note**

`docs/learn/faza-4-pubsub-consumer.md` (po polsku, ~60–100 linii): pull vs
push, flow control i po co limitować wiadomości w locie, semantyka ack/nack i
dlaczego ack DOPIERO po udanym zapisie, at-least-once w praktyce (redelivery po
nacku), rola insertId (trip_key) jako best-effort dedup po stronie BQ i jego
okno czasowe, świadoma rezygnacja z dead-letter (log+ack+licznik) i kiedy w
realu byłaby zła.

- [ ] **Step 6: Write the feature record**

`docs/features/faza-4-streaming-pubsub/faza-4-task-2/README.md` — sections:
What was built / Files touched / Key decisions / Verification (test output).

- [ ] **Step 7: Commit**

```bash
git add ingestion/stream_consumer.py tests/test_stream_consumer.py \
        docs/learn/faza-4-pubsub-consumer.md \
        docs/features/faza-4-streaming-pubsub/faza-4-task-2/README.md
git commit -m "feat(faza-4-task-2): Pub/Sub consumer — batched streaming inserts with insertId dedup"
```

---

## Task 3: Live run, dedup verification, docs, PR (in-session, after Tasks 1–2 merge)

**Files:**
- Modify: `README.md` (streaming section + status checkbox)
- Create: `docs/features/faza-4-streaming-pubsub/faza-4-task-3/README.md`

- [ ] **Step 1: Ensure resources**

Run: `.venv/bin/python -c "from ingestion.stream_common import *; ensure_stream_resources(load_stream_config())"`
Expected: creates topic `trips-stream`, sub `trips-stream-sub`, dataset
`stream`, table `stream.trips` (idempotent on re-run).

- [ ] **Step 2: Replay with the consumer running**

Terminal A: `.venv/bin/python -m ingestion.stream_consumer`
Terminal B: `.venv/bin/python -m ingestion.stream_producer --limit 100000 --rate 500 --dup-rate 0.02`
Expected: producer summary `published=100000 duplicates≈2000`; consumer drains
and idles out with `inserted ≥ 100000` seen (redeliveries possible).

- [ ] **Step 3: Verify dedup in BigQuery**

```bash
bq query --use_legacy_sql=false "SELECT COUNT(*) total, COUNT(DISTINCT trip_key) uniq FROM \`taxi-chat-data.stream.trips\`"
bq query --use_legacy_sql=false "SELECT trip_key, COUNT(*) c FROM \`taxi-chat-data.stream.trips\` GROUP BY trip_key HAVING c > 1 LIMIT 10"
```
Expected: `total == uniq` (or a handful of stragglers — record the number
against the producer's injected-duplicate count; insertId is best-effort).

- [ ] **Step 4: README + feature record + full suite**

README: check the Faza 4 box, add a short "Streaming (Faza 4)" section
(commands from Steps 1–2, the cost note, the dedup verification query).
Write `docs/features/faza-4-streaming-pubsub/faza-4-task-3/README.md`.
Run `.venv/bin/pytest` — all green.

- [ ] **Step 5: Commit, push, PR**

```bash
git add README.md docs/features/faza-4-streaming-pubsub/faza-4-task-3/
git commit -m "docs: README streaming section + Faza 4 verification record"
git push -u origin feat/faza-4-streaming-pubsub
gh pr create --base master --title "Faza 4: simulated streaming — Pub/Sub producer/consumer, stream.trips" \
  --body "$(cat <<'EOF'
## What
Streaming path next to batch: producer replays the local Parquet into Pub/Sub
topic `trips-stream` (throttled, with deliberate duplicate injection), consumer
writes to BigQuery `stream.trips` via streaming inserts with insertId
(dbt-compatible `trip_key`). At-least-once semantics: ack only after a
successful insert, nack → redelivery, insertId de-duplicates.

## Evidence
(paste: producer summary, consumer summary, and the two dedup queries from
Task 3 Steps 2–3 — total vs uniq counts against injected duplicates)

## Tests
- unit: `pytest` all green (fake publisher/subscriber/BQ — no live GCP)
- golden: Python `compute_trip_key` pinned against live BigQuery/dbt recipe
EOF
)"
```

---

## Harness execution notes (operator)

- Task 0 in-session FIRST (contract + golden calibration), commit to
  `feat/faza-4-streaming-pubsub`, push, bump `DEFAULT_BASE` in the profile.
- Wave 1: `launch-task.sh --project taxi-chat-data --autonomous --names <a>,<b>
  faza-4-task-1 faza-4-task-2`. The task specs declare them a COHORT — each
  agent sets `cohort` accordingly; the intent-gate hook blocks edits until
  both ack each other's intent.
- Task 3 in-session after both PRs merge into the phase branch.
