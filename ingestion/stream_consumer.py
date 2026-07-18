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
        try:
            errors = self._bq.insert_rows_json(self._table_id, rows, row_ids=row_ids)
        except Exception as exc:  # noqa: BLE001 — transient RPC/client error
            # BigQuery raised instead of returning row-level errors (network,
            # auth, quota). Nack the whole batch and keep the consumer alive:
            # Pub/Sub redelivers, insertId (trip_key) de-dups what landed.
            print(f"[consumer] insert raised ({exc!r}) — nacking batch of {len(rows)}")
            for message in messages:
                message.nack()
            return
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
