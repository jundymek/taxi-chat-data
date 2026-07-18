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


class RaisingBQ:
    """insert_rows_json raises (transient RPC/auth/network error) instead of
    returning row-level errors."""

    def __init__(self):
        self.calls = 0

    def insert_rows_json(self, table_id, rows, row_ids=None):
        self.calls += 1
        raise RuntimeError("transient RPC error")


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


def test_insert_exception_nacks_batch_and_does_not_propagate():
    # A raised insert (not a returned error list) must still nack the batch and
    # keep the consumer alive — advertised at-least-once semantics.
    bq = RaisingBQ()
    writer = BatchWriter(bq, "p.stream.trips", batch_size=1)
    msg = FakeMessage(row_to_message(ROW))
    writer.add(msg)  # must not raise
    assert msg.nacked and not msg.acked
    assert writer.inserted == 0
    assert bq.calls == 1


def test_nack_fires_on_retry_hook_to_reset_idle_timer():
    # A nacked batch has a redelivery pending — the CLI must not treat that as
    # idleness, so BatchWriter calls on_retry whenever it nacks.
    bq = FakeBQ(errors=[{"index": 0, "errors": [{"reason": "invalid"}]}])
    bumps = []
    writer = BatchWriter(bq, "p.stream.trips", batch_size=1,
                         on_retry=lambda: bumps.append(1))
    writer.add(FakeMessage(row_to_message(ROW)))
    assert bumps == [1]


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
