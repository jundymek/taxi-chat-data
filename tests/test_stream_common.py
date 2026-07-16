import json
from datetime import datetime, timezone

import pytest

from ingestion.stream_common import (
    MESSAGE_FIELDS,
    SURROGATE_KEY_FIELDS,
    compute_trip_key,
    message_to_bq_row,
    row_to_message,
)

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

# Pinned during Task 0 against live BigQuery (see the plan, Task 0 Step 5) —
# the exact value dbt_utils.generate_surrogate_key produces for SAMPLE_ROW.
# Cross-checked against a real stg_trips row (000096339684214f...) too.
GOLDEN_TRIP_KEY = "4c4bf4d2baa22a4be4661b99b21b08b6"


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
