# Faza 2: dbt Warehouse (staging → star schema) — Design / Spec

> Design for Faza 2 of `taxi-chat-data`. Consumes `raw.trips` from Faza 1
> (Parquet → GCS → BigQuery raw). Produces a cleaned staging layer and a
> partitioned/clustered star schema in BigQuery, transformed by dbt. Full
> project context: `docs/DESIGN.md` (section 5). Implementation plan follows
> in `docs/superpowers/plans/`.

## 1. Goal

Turn the raw, untransformed `raw.trips` table into a governed dimensional
warehouse using dbt: a cleaned **staging** layer, then a **star schema**
(4 dimensions + 1 fact) in the **marts** layer — with physical optimization
(partitioning + clustering) and a concrete before/after scan measurement.
This is the "logical + physical modeling", "data warehouse", and "SQL
optimization in BigQuery" part of the target job profile.

## 2. Scope

**In scope:** dbt project setup (in Docker, ADC auth), 3 seeds, staging model,
4 dimension models, 1 fact model with partitioning/clustering, dbt data tests +
column descriptions, a partitioning-measurement script, and Polish learning
notes per task.

**Explicitly out of scope (later phases):**
- Streaming / `stream.trips` merge — Faza 4. Staging is built to accept it
  without a rewrite, but does not reference it yet.
- Incremental materialization of `fct_trips` — Faza 4, when a real data inflow
  justifies it (YAGNI for one static month).
- RAG / NL2SQL consumption of `schema.yml` descriptions — Faza 3.
- Airflow orchestration of `dbt run`/`dbt test` — Faza 6.
- Dead-letter handling for bad rows — deliberately not built; bad rows are
  filtered out in staging (a dead-letter table is overkill for one batch file).

## 3. Key decisions (approved in brainstorming)

| Topic | Decision |
|---|---|
| Layering | Medallion: `raw` → `staging` (stg_trips) → `marts` (star schema), all in BigQuery, transformed by dbt |
| Staging vs stream | `stg_trips` reads **only** `raw.trips` for now, but is structured (source + UNION-ready) so Faza 4 can add stream with one model, no rewrite |
| Materialization | staging = **view**; dimensions = **table**; fact = **table** (partitioned + clustered). Incremental deferred to Faza 4 |
| Location names | dbt **seed** from NYC TLC `taxi_zone_lookup.csv` → `dim_location` enriched with borough / zone / service_zone |
| Code dictionaries | dbt **seeds** for payment_type and RatecodeID → `dim_payment` / `dim_ratecode` with official code→description mappings; descriptions also go into `schema.yml` (feed RAG in Faza 3) |
| Fact grain / key | grain = one trip; deterministic **surrogate key** `trip_key = generate_surrogate_key(...)` (dbt_utils) → same trip from raw and stream gets the same key (basis for dedup in Faza 4) |
| Physical optimization | `fct_trips` partitioned by `pickup_date`, clustered by `pickup_location_id` |
| Optimization proof | script does a BigQuery **dry-run** of the same time-range query on a partitioned+clustered vs unpartitioned copy, records `bytes_processed` before/after into a docs note |
| dbt runtime | `dbt-core` + `dbt-bigquery` + `dbt_utils` in a **Docker** container (docker-compose service), mounting `~/.config/gcloud` read-only → **ADC** auth, no key file in repo |

## 4. Architecture and data flow

```
raw.trips (Faza 1)  ──►  staging  ──►  marts (star schema)  ──►  [Faza 3: RAG/NL2SQL]
                      stg_trips           dim_datetime
                      (view:              dim_location   ┐
                       clean, cast,       dim_ratecode   ├─► fct_trips
                       dedup,             dim_payment    ┘   (partition: pickup_date
                       surrogate key)                        cluster: pickup_location_id)
                                                             measures: fare, tip, distance,
                                                                       total, duration_min
     seeds: taxi_zone_lookup.csv, payment_type_lookup.csv, ratecode_lookup.csv
```

Datasets in BigQuery (US, existing `raw`; new): `staging`, `marts`. dbt writes
`stg_trips` into `staging`, dims/fact into `marts`.

## 5. Models

### 5.1 Staging — `stg_trips` (view, source: `raw.trips` via `source()`)

- **Cleaning** (drop rows where): `fare_amount < 0` OR `total_amount < 0`;
  `trip_distance <= 0`; `tpep_pickup_datetime` out of a sane range (before
  2009 or in the future); `tpep_dropoff_datetime < tpep_pickup_datetime`.
- **Types / derived:** cast `passenger_count` and `RatecodeID` FLOAT→INT;
  `pickup_date = DATE(tpep_pickup_datetime)`;
  `trip_duration_min = TIMESTAMP_DIFF(dropoff, pickup, MINUTE)`.
- **Key:** `trip_key = generate_surrogate_key([tpep_pickup_datetime,
  tpep_dropoff_datetime, PULocationID, DOLocationID, fare_amount, VendorID])`.
- **Dedup:** `QUALIFY ROW_NUMBER() OVER (PARTITION BY trip_key ORDER BY
  tpep_pickup_datetime) = 1`.
- Renames raw's CamelCase columns to snake_case, stable, warehouse-friendly
  names (e.g. `PULocationID` → `pickup_location_id`).

### 5.2 Dimensions (tables)

| Dimension | Key | Attributes | Source |
|---|---|---|---|
| `dim_datetime` | `date_key` (DATE) | year, month, day, day_of_week, day_name, is_weekend | generated from the date range present in `stg_trips` |
| `dim_location` | `location_id` (1–265) | borough, zone, service_zone | seed `taxi_zone_lookup` |
| `dim_payment` | `payment_type` (INT) | payment_desc (Credit card, Cash, …) | seed `payment_type_lookup` |
| `dim_ratecode` | `ratecode_id` (INT) | ratecode_desc (Standard, JFK, …) | seed `ratecode_lookup` |

**`dim_datetime` grain = day** (`date_key` is a DATE), matching the fact's
`pickup_date` partition. Hour-level detail, if needed, lives as a plain column
on the fact — the dimension is not exploded to second/hour grain.

### 5.3 Fact — `fct_trips` (table, grain = one trip)

- **Foreign keys:** `trip_key`, `pickup_date` (→ dim_datetime),
  `pickup_location_id` / `dropoff_location_id` (→ dim_location),
  `payment_type` (→ dim_payment), `ratecode_id` (→ dim_ratecode).
- **Measures:** `fare_amount`, `tip_amount`, `tolls_amount`, `total_amount`,
  `trip_distance`, `trip_duration_min`, `passenger_count`.
- **Physical config:**
  ```sql
  {{ config(materialized='table',
            partition_by={'field': 'pickup_date', 'data_type': 'date'},
            cluster_by=['pickup_location_id']) }}
  ```

## 6. Physical optimization measurement

`analysis/measure_partitioning.py`:
- Builds an unpartitioned copy of the fact (`fct_trips_unpartitioned`) alongside
  the partitioned+clustered `fct_trips`.
- Runs a BigQuery **dry-run** (`dry_run=True`, no execution, no cost) of the
  same time-range + location query against both.
- Records `bytes_processed` for both and the reduction into
  `docs/learn/faza-2-partitioning-measurement.md` (with a Polish learning note).
- Gives a concrete, repeatable "scan reduced from X GB to Y GB" for interviews.

The script has a light Python unit test that parses/asserts on a sample dry-run
result structure — it does **not** call BigQuery (consistent with Faza 1's
"don't mock cloud clients; test the pure logic, integration-smoke the rest").

## 7. Governance — dbt tests and descriptions

`schema.yml` files carry both tests and **column descriptions**:
- Tests: `not_null` + `unique` on dimension keys and `trip_key`;
  `relationships` from `fct_trips` FKs to each dimension;
  `accepted_values` on `payment_type` / `ratecode_id`.
- Descriptions: human-readable column docs — these become the knowledge source
  for RAG in Faza 3, so they are written carefully now.
- `dbt test` runs in every build; a red test fails the build (governance gate).

## 8. File structure

```
dbt/
├── dbt_project.yml          # staging=view, marts=table materialization
├── profiles.yml             # BigQuery, ADC (oauth), dataset per layer
├── packages.yml             # dbt_utils
├── seeds/
│   ├── taxi_zone_lookup.csv
│   ├── payment_type_lookup.csv
│   └── ratecode_lookup.csv
├── models/
│   ├── staging/
│   │   ├── _staging__sources.yml   # source: raw.trips
│   │   ├── stg_trips.sql
│   │   └── _staging__models.yml    # descriptions + tests
│   └── marts/
│       ├── dim_datetime.sql
│       ├── dim_location.sql
│       ├── dim_payment.sql
│       ├── dim_ratecode.sql
│       ├── fct_trips.sql
│       └── _marts__models.yml      # descriptions + tests (relationships, unique, not_null, accepted_values)
docker-compose.yml           # + dbt service (mounts ~/.config/gcloud read-only)
analysis/measure_partitioning.py
docs/learn/faza-2-*.md       # Polish learning notes per task
```

`requirements.txt` (the `.venv`) is **not** touched — dbt runs in Docker, not in
the venv. dbt package deps live in `dbt/packages.yml`.

## 9. Error handling / data quality

- Bad rows are **filtered out in staging**, not routed to a dead-letter table.
  A dead-letter is deliberately out of scope for a single batch file; this is a
  conscious simplicity decision, noted for the record.
- `dbt test` failing = build failure — the governance gate for data quality.

## 10. Testing strategy (consistent with Faza 1)

Two levels:
1. **dbt data tests** (`not_null` / `unique` / `relationships` /
   `accepted_values`) — part of every build; the primary verification of this
   phase.
2. **Manual integration verification** — `docker compose run --rm dbt build`
   against real BigQuery, then a sanity query (row count in `fct_trips` ≈ the
   cleaned raw count; a few fact↔dimension joins resolve) plus the partitioning
   measurement.

No Python unit tests for the SQL itself (there is no Python logic to test beyond
the measurement script, which gets a light pure-logic unit test).

## 11. Auth / security (carries Faza 1's posture)

- dbt container mounts `~/.config/gcloud` **read-only** and authenticates to
  BigQuery via ADC (oauth) — no service-account key file anywhere in the repo.
- `.gitignore` already covers key files and `.env`; no new secret surface.
- Free-tier discipline: still one month of data; the measurement script uses
  dry-runs (zero scan cost).

## 12. Working language

Per project convention: all code, SQL, YAML comments, model descriptions, and
commit messages in **English**; additionally a **Polish learning note** per task
under `docs/learn/` (study material for the owner). No AI-attribution footer in
commits or PRs.
