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
    hash the SAME text dbt hashes. Calibrated against live BQ (plan, Step 5)."""
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
