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


def test_replay_flushes_accepted_publishes_on_interrupt(parquet_file):
    """A KeyboardInterrupt mid-replay must still await already-accepted futures
    so the client does not drop buffered messages on exit."""
    awaited = []

    class RecordingFuture:
        def __init__(self, index):
            self.index = index

        def result(self, timeout=None):
            awaited.append(self.index)
            return "msg-id"

    class InterruptingPublisher(FakePublisher):
        def publish(self, topic_path, data, **attrs):
            self.published.append((topic_path, data, attrs))
            if len(self.published) == 2:
                raise KeyboardInterrupt
            return RecordingFuture(len(self.published))

    pub = InterruptingPublisher()
    with pytest.raises(KeyboardInterrupt):
        replay(_cfg(parquet_file), pub, limit=3, rate=0, dup_rate=0.0, rng=FixedRng())
    # The one future accepted before the interrupt was flushed.
    assert awaited == [1]
