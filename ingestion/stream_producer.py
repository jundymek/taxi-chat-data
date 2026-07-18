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

from ingestion.stream_common import compute_trip_key, load_stream_config, row_to_message

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
    try:
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
    finally:
        # Await every accepted publish — even on KeyboardInterrupt mid-replay —
        # so messages already handed to the client are not dropped on exit.
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
        print("\n[producer] interrupted — already-published messages were flushed")
        return 130
    elapsed = time.monotonic() - started
    print(
        f"[producer] published={stats['published']} duplicates={stats['duplicates']} "
        f"elapsed={elapsed:.1f}s rate={stats['published'] / max(elapsed, 0.001):.0f} msg/s"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
