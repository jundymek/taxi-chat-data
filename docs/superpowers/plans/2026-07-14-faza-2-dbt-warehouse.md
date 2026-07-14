# Faza 2: dbt Warehouse (staging → star schema) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform `raw.trips` (Faza 1) into a governed dimensional warehouse with dbt: a cleaned `staging` view, a `marts` star schema (4 dimensions + 1 partitioned/clustered fact), dbt data tests + column descriptions, and a before/after scan measurement — all run through a Dockerized dbt using ADC auth.

**Architecture:** Medallion layering in BigQuery, transformations in dbt. `stg_trips` (view) cleans/casts/dedups `raw.trips` and assigns a deterministic surrogate `trip_key`. Marts (tables): `dim_datetime`, `dim_location`, `dim_payment`, `dim_ratecode`, and `fct_trips` (partitioned by `pickup_date`, clustered by `pickup_location_id`). Dimension descriptions come from CSV seeds and feed RAG in Faza 3. dbt runs in a docker-compose service that mounts `~/.config/gcloud` read-only for ADC.

**Tech Stack:** dbt-core + dbt-bigquery + dbt_utils (in Docker), BigQuery (US), docker-compose, Python 3 (measurement script, uses the existing `.venv` + `google-cloud-bigquery`), pytest.

Design/spec: `docs/superpowers/specs/2026-07-14-faza-2-dbt-warehouse-design.md`.

## Global Constraints

Copied from the spec and project conventions:

- **Working language:** ALL code, SQL, YAML comments, model descriptions, and commit messages in **ENGLISH**. ADDITIONALLY, per task, a **Polish learning note** under `docs/learn/faza-2-<task>.md` (concise but substantive study material). **No AI-attribution / "Generated with" footer** in commits or PR.
- **Secrets NEVER in repo.** dbt authenticates to BigQuery via **ADC** (`method: oauth`), by mounting `~/.config/gcloud` read-only into the container — no service-account key file. `.gitignore` already covers `.env` and key files; add dbt artifacts (`dbt/target/`, `dbt/dbt_packages/`, `dbt/logs/`).
- **BigQuery free tier.** Still one month of data (`raw.trips` ≈ 3.07M rows). The measurement script uses **dry-runs only** (zero scan cost).
- **GCP:** project `taxi-chat-data`, location **US**. Existing dataset `raw`. New datasets `staging`, `marts` (dbt auto-creates them).
- **Materialization:** `staging` = **view**; `marts` = **table**. `fct_trips` = table partitioned by `pickup_date`, clustered by `pickup_location_id`. No incremental (deferred to Faza 4).
- **Fact key:** deterministic `trip_key = dbt_utils.generate_surrogate_key([...])` over the trip-identifying columns (below). No natural trip_id exists in the source.
- **Bad rows are filtered in staging**, not routed to a dead-letter (conscious simplicity for one batch file).
- **Python:** the measurement script runs in the existing `.venv` (`.venv/bin/python`); dbt does NOT run in the venv (it is Dockerized). Do not add dbt to `requirements.txt`.

---

## Prerequisites (MANUAL — verify, do not redo)

These were done in Faza 1 and must still hold. Verify before Task 2:

- `raw.trips` exists in BigQuery with ~3.07M rows:
  `bq query --use_legacy_sql=false "SELECT COUNT(*) FROM \`taxi-chat-data.raw.trips\`"` → ~3066766.
- ADC present: `~/.config/gcloud/application_default_credentials.json` exists.
- Docker is installed and running: `docker --version` and `docker compose version` succeed.
- `.venv` exists with `google-cloud-bigquery` (from Faza 1).

If any check fails, STOP and report rather than guessing.

---

## File Structure

```
dbt/
├── dbt_project.yml               # project config: model paths, staging=view, marts=table, seed schema
├── profiles.yml                  # BigQuery, method: oauth (ADC), one target, dataset per layer via +schema
├── packages.yml                  # dbt_utils
├── seeds/
│   ├── taxi_zone_lookup.csv      # location_id → borough, zone, service_zone (263 rows, from NYC TLC)
│   ├── payment_type_lookup.csv   # payment_type → payment_desc (6 rows)
│   └── ratecode_lookup.csv       # ratecode_id → ratecode_desc (6 rows)
├── models/
│   ├── staging/
│   │   ├── _staging__sources.yml # source raw.trips
│   │   ├── stg_trips.sql         # clean/cast/dedup + trip_key (view)
│   │   └── _staging__models.yml  # stg_trips description + tests
│   └── marts/
│       ├── dim_datetime.sql
│       ├── dim_location.sql
│       ├── dim_payment.sql
│       ├── dim_ratecode.sql
│       ├── fct_trips.sql
│       └── _marts__models.yml    # descriptions + tests (unique, not_null, relationships, accepted_values)
├── Dockerfile                    # dbt-bigquery image (pinned)
docker-compose.yml                # dbt service (mounts ~/.config/gcloud ro, dbt/ as workdir)
analysis/
├── __init__.py
└── measure_partitioning.py       # dry-run bytes_processed: partitioned vs unpartitioned
tests/
└── test_measure_partitioning.py  # pure-logic unit test (no BigQuery)
docs/learn/faza-2-*.md            # Polish learning notes per task
```

Tasks are ordered so each ends with an independently testable deliverable: infra first (Task 1–2), then seeds (Task 3), then staging (Task 4), then dimensions (Task 5), then fact + optimization (Task 6), then the measurement (Task 7), then end-to-end verification (Task 8).

---

## Task 1: dbt project scaffold + Dockerized dbt on ADC

**Files:**
- Create: `dbt/dbt_project.yml`, `dbt/profiles.yml`, `dbt/packages.yml`, `dbt/Dockerfile`
- Create: `docker-compose.yml`
- Modify: `.gitignore` (add dbt artifacts)
- Create: `docs/learn/faza-2-dbt-setup.md`

**Interfaces:**
- Consumes: nothing (first task); relies on ADC at `~/.config/gcloud`.
- Produces: a working `docker compose run --rm dbt <cmd>` that authenticates to BigQuery via ADC. Profile name `taxi_chat_data`, one target `dev`, `method: oauth`, `project: taxi-chat-data`, `location: US`, default `schema: staging`.

- [ ] **Step 1: Add dbt artifacts to `.gitignore`**

Append:
```gitignore
# dbt artifacts
dbt/target/
dbt/dbt_packages/
dbt/logs/
```

- [ ] **Step 2: Create `dbt/dbt_project.yml`**

```yaml
name: taxi_chat_data
version: "1.0.0"
config-version: 2

profile: taxi_chat_data

model-paths: ["models"]
seed-paths: ["seeds"]

models:
  taxi_chat_data:
    staging:
      +materialized: view
      +schema: staging
    marts:
      +materialized: table
      +schema: marts

seeds:
  taxi_chat_data:
    +schema: marts
    +quote_columns: false
```

Note on `+schema`: with dbt-bigquery, `+schema` sets the dataset. dbt composes the dataset name; to get exactly `staging`/`marts` (not `<default>_staging`), the profile's `dataset` is the base. We set the profile `dataset: staging` and override marts via `+schema: marts` (dbt-bigquery uses the custom schema verbatim when `generate_schema_name` is the default macro AND the custom schema differs — see Step 6 verification; if datasets come out concatenated, add the override macro in Step 3b).

- [ ] **Step 3: Create `dbt/profiles.yml`**

```yaml
taxi_chat_data:
  target: dev
  outputs:
    dev:
      type: bigquery
      method: oauth
      project: taxi-chat-data
      dataset: staging
      location: US
      threads: 4
```

- [ ] **Step 3b: Add a `generate_schema_name` override so `+schema` is used verbatim**

Create `dbt/macros/generate_schema_name.sql` (ensures datasets are exactly `staging` / `marts`, not `staging_marts`):

```sql
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
```

Add `macro-paths: ["macros"]` to `dbt_project.yml` (under the paths section).

- [ ] **Step 4: Create `dbt/packages.yml`**

```yaml
packages:
  - package: dbt-labs/dbt_utils
    version: [">=1.1.0", "<2.0.0"]
```

- [ ] **Step 5: Create `dbt/Dockerfile`**

```dockerfile
FROM python:3.12-slim

RUN pip install --no-cache-dir "dbt-bigquery>=1.8,<2.0"

WORKDIR /usr/app/dbt
# Profiles live in the mounted project dir; point dbt at it.
ENV DBT_PROFILES_DIR=/usr/app/dbt

ENTRYPOINT ["dbt"]
CMD ["--version"]
```

- [ ] **Step 6: Create `docker-compose.yml`**

```yaml
services:
  dbt:
    build:
      context: ./dbt
      dockerfile: Dockerfile
    working_dir: /usr/app/dbt
    volumes:
      # Project files (models, seeds, profiles) — live-editable from host.
      - ./dbt:/usr/app/dbt
      # ADC credentials, read-only, so the container authenticates as you.
      - ~/.config/gcloud:/root/.config/gcloud:ro
    environment:
      # gcloud ADC default location inside the container.
      - GOOGLE_CLOUD_PROJECT=taxi-chat-data
```

- [ ] **Step 7: Build the image and verify dbt + ADC connectivity**

Run:
```bash
cd ~/dev/taxi-chat-data
docker compose build dbt
docker compose run --rm dbt deps        # installs dbt_utils
docker compose run --rm dbt debug       # verifies BigQuery connection via ADC
```
Expected: `dbt debug` ends with `All checks passed!` and a successful BigQuery connection. If `debug` reports an auth error, STOP and report (do not embed a key file).

Verify dataset naming by a dry compile (no models yet, so this just confirms config parses):
```bash
docker compose run --rm dbt parse
```
Expected: parses without error.

- [ ] **Step 8: Write the Polish learning note**

Create `docs/learn/faza-2-dbt-setup.md` (in Polish) explaining: what dbt is and the medallion layering, why dbt runs in Docker (reproducible runtime, path to docker-compose + Airflow in Faza 6), why ADC-by-mount over a key file (same security posture as Faza 1), and what the concept teaches (transformation layer / ELT, environment isolation, IaC-style project config).

- [ ] **Step 9: Commit**

```bash
git add .gitignore dbt/ docker-compose.yml docs/learn/faza-2-dbt-setup.md
git commit -m "chore: dockerized dbt project on BigQuery via ADC"
```

---

## Task 2: Seeds — location, payment, ratecode lookups

**Files:**
- Create: `dbt/seeds/taxi_zone_lookup.csv`, `dbt/seeds/payment_type_lookup.csv`, `dbt/seeds/ratecode_lookup.csv`
- Create: `dbt/seeds/_seeds__properties.yml` (column types + descriptions + tests)
- Create: `docs/learn/faza-2-seeds.md`

**Interfaces:**
- Consumes: the dbt project from Task 1.
- Produces: three seed tables in `marts`: `taxi_zone_lookup(location_id INT, borough STRING, zone STRING, service_zone STRING)`, `payment_type_lookup(payment_type INT, payment_desc STRING)`, `ratecode_lookup(ratecode_id INT, ratecode_desc STRING)`. Dimensions in Task 5 `ref()` these.

- [ ] **Step 1: Create `dbt/seeds/payment_type_lookup.csv`**

Official NYC TLC payment_type dictionary:
```csv
payment_type,payment_desc
1,Credit card
2,Cash
3,No charge
4,Dispute
5,Unknown
6,Voided trip
```

- [ ] **Step 2: Create `dbt/seeds/ratecode_lookup.csv`**

Official NYC TLC RatecodeID dictionary:
```csv
ratecode_id,ratecode_desc
1,Standard rate
2,JFK
3,Newark
4,Nassau or Westchester
5,Negotiated fare
6,Group ride
```

- [ ] **Step 3: Create `dbt/seeds/taxi_zone_lookup.csv`**

Download the official NYC TLC zone lookup (263 zones) and normalize the header to snake_case:
```bash
cd ~/dev/taxi-chat-data
curl -sSL "https://d37ci6vzurychx.cloudfront.net/misc/taxi_zone_lookup.csv" -o /tmp/taxi_zone_lookup_raw.csv
head -3 /tmp/taxi_zone_lookup_raw.csv
```
The source header is `LocationID,Borough,Zone,service_zone`. Create `dbt/seeds/taxi_zone_lookup.csv` with header `location_id,borough,zone,service_zone` and the same rows. Concretely:
```bash
{ echo "location_id,borough,zone,service_zone"; tail -n +2 /tmp/taxi_zone_lookup_raw.csv; } > dbt/seeds/taxi_zone_lookup.csv
wc -l dbt/seeds/taxi_zone_lookup.csv   # expect 265 lines (264 rows incl. 264/265 "Unknown" + 1 header)
```
Note: rows may contain commas inside quoted `zone` values — keep the file exactly as the source provides (quoted). Do not hand-edit rows.

- [ ] **Step 4: Create `dbt/seeds/_seeds__properties.yml`**

```yaml
version: 2

seeds:
  - name: taxi_zone_lookup
    description: "NYC TLC taxi zone lookup: maps location_id (1-265) to its borough, zone name, and service zone. Source of geographic names for dim_location."
    config:
      column_types:
        location_id: INT64
        borough: STRING
        zone: STRING
        service_zone: STRING
    columns:
      - name: location_id
        description: "TLC taxi zone id (1-265)."
        tests: [not_null, unique]

  - name: payment_type_lookup
    description: "Official NYC TLC payment_type code dictionary (1=Credit card, 2=Cash, ...)."
    config:
      column_types:
        payment_type: INT64
        payment_desc: STRING
    columns:
      - name: payment_type
        description: "Payment type code."
        tests: [not_null, unique]

  - name: ratecode_lookup
    description: "Official NYC TLC RatecodeID dictionary (1=Standard rate, 2=JFK, ...)."
    config:
      column_types:
        ratecode_id: INT64
        ratecode_desc: STRING
    columns:
      - name: ratecode_id
        description: "Rate code id."
        tests: [not_null, unique]
```

- [ ] **Step 5: Load and test the seeds**

Run:
```bash
docker compose run --rm dbt seed
docker compose run --rm dbt test --select "resource_type:seed"
```
Expected: 3 seeds loaded into `marts`; tests pass (not_null + unique on each key).

Independently verify:
```bash
bq query --use_legacy_sql=false "SELECT COUNT(*) AS n FROM \`taxi-chat-data.marts.taxi_zone_lookup\`"
```
Expected: `n` = 264 (or 265 depending on the source's Unknown rows — record the actual number).

- [ ] **Step 6: Write the Polish learning note**

Create `docs/learn/faza-2-seeds.md` (Polish): what seeds are (small, versioned reference data loaded from CSV), why we enrich raw codes with human-readable descriptions (governance + NL2SQL: LLM can answer "trips paid by cash" not "payment_type=2"), and the concept (conformed dimensions, reference/lookup data, code→label mapping feeding RAG in Faza 3).

- [ ] **Step 7: Commit**

```bash
git add dbt/seeds/ docs/learn/faza-2-seeds.md
git commit -m "feat: dbt seeds for taxi zone, payment, and ratecode lookups"
```

---

## Task 3: Staging model `stg_trips` (clean, cast, dedup, surrogate key)

**Files:**
- Create: `dbt/models/staging/_staging__sources.yml`
- Create: `dbt/models/staging/stg_trips.sql`
- Create: `dbt/models/staging/_staging__models.yml`
- Create: `docs/learn/faza-2-staging.md`

**Interfaces:**
- Consumes: source `raw.trips` (Faza 1 schema — CamelCase columns: `VendorID`, `tpep_pickup_datetime`, `tpep_dropoff_datetime`, `passenger_count` FLOAT, `trip_distance` FLOAT, `RatecodeID` FLOAT, `PULocationID` INT, `DOLocationID` INT, `payment_type` INT, `fare_amount` FLOAT, `tip_amount`, `tolls_amount`, `total_amount`, ...).
- Produces: view `staging.stg_trips` with snake_case columns and these fields (relied on by Task 5 dims and Task 6 fact): `trip_key STRING`, `vendor_id INT`, `pickup_datetime TIMESTAMP`, `dropoff_datetime TIMESTAMP`, `pickup_date DATE`, `trip_duration_min INT`, `passenger_count INT`, `trip_distance FLOAT`, `ratecode_id INT`, `pickup_location_id INT`, `dropoff_location_id INT`, `payment_type INT`, `fare_amount`, `tip_amount`, `tolls_amount`, `total_amount` (FLOAT).

- [ ] **Step 1: Create `dbt/models/staging/_staging__sources.yml`**

```yaml
version: 2

sources:
  - name: raw
    database: taxi-chat-data
    schema: raw
    tables:
      - name: trips
        description: "Raw NYC Taxi trips loaded from Parquet in Faza 1 (untransformed)."
```

- [ ] **Step 2: Write the model as a failing build (RED via a test that can't pass yet)**

First write the model file with the full logic (dbt has no separate "test file"; the RED/GREEN cycle here is: add the model + its schema tests, run `dbt build` and see it fail before the model is correct, then pass). Create `dbt/models/staging/stg_trips.sql`:

```sql
{{ config(materialized='view') }}

with source as (
    select * from {{ source('raw', 'trips') }}
),

cleaned as (
    select
        {{ dbt_utils.generate_surrogate_key([
            'tpep_pickup_datetime',
            'tpep_dropoff_datetime',
            'PULocationID',
            'DOLocationID',
            'fare_amount',
            'VendorID'
        ]) }}                                              as trip_key,
        VendorID                                           as vendor_id,
        tpep_pickup_datetime                               as pickup_datetime,
        tpep_dropoff_datetime                              as dropoff_datetime,
        date(tpep_pickup_datetime)                         as pickup_date,
        timestamp_diff(
            tpep_dropoff_datetime, tpep_pickup_datetime, minute
        )                                                  as trip_duration_min,
        cast(passenger_count as int64)                     as passenger_count,
        trip_distance                                      as trip_distance,
        cast(RatecodeID as int64)                          as ratecode_id,
        PULocationID                                       as pickup_location_id,
        DOLocationID                                       as dropoff_location_id,
        payment_type                                       as payment_type,
        fare_amount                                        as fare_amount,
        tip_amount                                         as tip_amount,
        tolls_amount                                       as tolls_amount,
        total_amount                                       as total_amount
    from source
    where fare_amount >= 0
      and total_amount >= 0
      and trip_distance > 0
      and tpep_dropoff_datetime >= tpep_pickup_datetime
      and date(tpep_pickup_datetime) >= '2009-01-01'
      and tpep_pickup_datetime <= current_timestamp()
),

deduped as (
    select *
    from cleaned
    qualify row_number() over (
        partition by trip_key order by pickup_datetime
    ) = 1
)

select * from deduped
```

- [ ] **Step 3: Create `dbt/models/staging/_staging__models.yml` with descriptions + tests**

```yaml
version: 2

models:
  - name: stg_trips
    description: "Cleaned, typed, deduplicated NYC Taxi trips from raw.trips. One row per trip, keyed by a deterministic surrogate trip_key. Bad rows (negative amounts, non-positive distance, impossible dates) are filtered out here."
    columns:
      - name: trip_key
        description: "Deterministic surrogate key (hash of pickup/dropoff datetime, PU/DO location, fare, vendor). Same trip yields the same key across raw and (future) stream — basis for deduplication."
        tests: [not_null, unique]
      - name: pickup_datetime
        description: "Trip start timestamp."
        tests: [not_null]
      - name: pickup_date
        description: "Date of pickup (partition key of fct_trips)."
        tests: [not_null]
      - name: pickup_location_id
        description: "TLC taxi zone id where the trip started."
        tests: [not_null]
      - name: dropoff_location_id
        description: "TLC taxi zone id where the trip ended."
      - name: payment_type
        description: "Payment type code (joins dim_payment)."
      - name: ratecode_id
        description: "Rate code id (joins dim_ratecode)."
```

- [ ] **Step 4: Build and test the model — verify it runs and passes**

Run:
```bash
docker compose run --rm dbt build --select stg_trips
```
Expected: `stg_trips` builds as a view; its tests (`not_null`, `unique` on `trip_key`, etc.) PASS. `unique` on `trip_key` passing proves dedup works.

Independently sanity-check row count (cleaned ≤ raw):
```bash
bq query --use_legacy_sql=false "SELECT COUNT(*) AS n FROM \`taxi-chat-data.staging.stg_trips\`"
```
Expected: `n` > 0 and `n` ≤ 3066766 (some rows filtered). Record the value.

- [ ] **Step 5: Write the Polish learning note**

Create `docs/learn/faza-2-staging.md` (Polish): what staging does (clean/cast/dedup + surrogate key), why a deterministic hash key (dedup now, raw+stream reconciliation in Faza 4), why filter bad rows here rather than a dead-letter (simplicity for one batch), why staging is a view (always fresh, zero storage), and the concept (silver/staging layer, surrogate keys, `QUALIFY` dedup, data cleaning in ELT).

- [ ] **Step 6: Commit**

```bash
git add dbt/models/staging/ docs/learn/faza-2-staging.md
git commit -m "feat: stg_trips staging model (clean, cast, dedup, surrogate key)"
```

---

## Task 4: Dimensions (`dim_location`, `dim_payment`, `dim_ratecode`, `dim_datetime`)

**Files:**
- Create: `dbt/models/marts/dim_location.sql`, `dim_payment.sql`, `dim_ratecode.sql`, `dim_datetime.sql`
- Create: `dbt/models/marts/_marts__models.yml` (dimension parts; fact added in Task 5)
- Create: `docs/learn/faza-2-dimensions.md`

**Interfaces:**
- Consumes: seeds `taxi_zone_lookup`, `payment_type_lookup`, `ratecode_lookup` (Task 2); `stg_trips` (Task 3) for the datetime range.
- Produces: tables in `marts`: `dim_location(location_id INT, borough, zone, service_zone)`, `dim_payment(payment_type INT, payment_desc)`, `dim_ratecode(ratecode_id INT, ratecode_desc)`, `dim_datetime(date_key DATE, year, month, day, day_of_week, day_name, is_weekend)`. Task 5's `fct_trips` `ref()`s these for `relationships` tests.

- [ ] **Step 1: Create `dbt/models/marts/dim_location.sql`**

```sql
{{ config(materialized='table') }}

select
    location_id,
    borough,
    zone,
    service_zone
from {{ ref('taxi_zone_lookup') }}
```

- [ ] **Step 2: Create `dbt/models/marts/dim_payment.sql`**

```sql
{{ config(materialized='table') }}

select
    payment_type,
    payment_desc
from {{ ref('payment_type_lookup') }}
```

- [ ] **Step 3: Create `dbt/models/marts/dim_ratecode.sql`**

```sql
{{ config(materialized='table') }}

select
    ratecode_id,
    ratecode_desc
from {{ ref('ratecode_lookup') }}
```

- [ ] **Step 4: Create `dbt/models/marts/dim_datetime.sql`**

Generate one row per distinct pickup date present in staging (grain = day):

```sql
{{ config(materialized='table') }}

with dates as (
    select distinct pickup_date as date_key
    from {{ ref('stg_trips') }}
)

select
    date_key,
    extract(year    from date_key)                       as year,
    extract(month   from date_key)                       as month,
    extract(day     from date_key)                       as day,
    extract(dayofweek from date_key)                     as day_of_week,   -- 1=Sunday..7=Saturday
    format_date('%A', date_key)                          as day_name,
    extract(dayofweek from date_key) in (1, 7)           as is_weekend
from dates
```

- [ ] **Step 5: Create `dbt/models/marts/_marts__models.yml` (dimensions)**

```yaml
version: 2

models:
  - name: dim_location
    description: "Location dimension: TLC taxi zones enriched with borough, zone name, and service zone. Referenced by fct_trips pickup/dropoff location ids."
    columns:
      - name: location_id
        description: "TLC taxi zone id (primary key)."
        tests: [not_null, unique]
      - name: borough
        description: "NYC borough the zone belongs to."

  - name: dim_payment
    description: "Payment dimension: payment_type code with its human-readable description."
    columns:
      - name: payment_type
        description: "Payment type code (primary key)."
        tests: [not_null, unique]
      - name: payment_desc
        description: "Human-readable payment method (e.g. Credit card, Cash)."

  - name: dim_ratecode
    description: "Rate code dimension: RatecodeID with its human-readable description."
    columns:
      - name: ratecode_id
        description: "Rate code id (primary key)."
        tests: [not_null, unique]
      - name: ratecode_desc
        description: "Human-readable rate code (e.g. Standard rate, JFK)."

  - name: dim_datetime
    description: "Date dimension at day grain, built from the pickup dates present in the data. Referenced by fct_trips.pickup_date."
    columns:
      - name: date_key
        description: "Calendar date (primary key); matches fct_trips.pickup_date."
        tests: [not_null, unique]
      - name: is_weekend
        description: "True for Saturday/Sunday."
```

- [ ] **Step 6: Build and test the dimensions**

Run:
```bash
docker compose run --rm dbt build --select dim_location dim_payment dim_ratecode dim_datetime
```
Expected: four tables built in `marts`; all `not_null`/`unique` tests PASS.

- [ ] **Step 7: Write the Polish learning note**

Create `docs/learn/faza-2-dimensions.md` (Polish): what dimensions are in a star schema (context/attributes for slicing facts), why `dim_datetime` is at day grain (matches the fact partition; avoids exploding to second grain), why location/payment/ratecode come from seeds (conformed, reusable), and the concept (star schema, dimension vs fact, conformed dimensions, degenerate vs surrogate keys).

- [ ] **Step 8: Commit**

```bash
git add dbt/models/marts/dim_*.sql dbt/models/marts/_marts__models.yml docs/learn/faza-2-dimensions.md
git commit -m "feat: star-schema dimensions (location, payment, ratecode, datetime)"
```

---

## Task 5: Fact `fct_trips` (partitioned + clustered) + relationship tests

**Files:**
- Create: `dbt/models/marts/fct_trips.sql`
- Modify: `dbt/models/marts/_marts__models.yml` (append the `fct_trips` block)
- Create: `docs/learn/faza-2-fact.md`

**Interfaces:**
- Consumes: `stg_trips` (Task 3); dimensions (Task 4) for `relationships` tests.
- Produces: table `marts.fct_trips`, partitioned by `pickup_date` (DATE), clustered by `pickup_location_id`, grain = one trip, keyed by `trip_key`. Columns: `trip_key`, `pickup_date`, `pickup_location_id`, `dropoff_location_id`, `payment_type`, `ratecode_id`, `pickup_datetime`, `dropoff_datetime`, `trip_duration_min`, `passenger_count`, `trip_distance`, `fare_amount`, `tip_amount`, `tolls_amount`, `total_amount`.

- [ ] **Step 1: Create `dbt/models/marts/fct_trips.sql`**

```sql
{{ config(
    materialized='table',
    partition_by={'field': 'pickup_date', 'data_type': 'date'},
    cluster_by=['pickup_location_id']
) }}

select
    trip_key,
    pickup_date,
    pickup_location_id,
    dropoff_location_id,
    payment_type,
    ratecode_id,
    pickup_datetime,
    dropoff_datetime,
    trip_duration_min,
    passenger_count,
    trip_distance,
    fare_amount,
    tip_amount,
    tolls_amount,
    total_amount
from {{ ref('stg_trips') }}
```

- [ ] **Step 2: Append the `fct_trips` block to `dbt/models/marts/_marts__models.yml`**

```yaml
  - name: fct_trips
    description: "Trip fact table at one-row-per-trip grain. Partitioned by pickup_date and clustered by pickup_location_id for scan efficiency. Measures: fare, tip, tolls, total, distance, duration, passenger count."
    columns:
      - name: trip_key
        description: "Deterministic surrogate key from staging (primary key)."
        tests: [not_null, unique]
      - name: pickup_date
        description: "Partition key; joins dim_datetime.date_key."
        tests:
          - not_null
          - relationships:
              to: ref('dim_datetime')
              field: date_key
      - name: pickup_location_id
        description: "Cluster key; joins dim_location.location_id."
        tests:
          - relationships:
              to: ref('dim_location')
              field: location_id
      - name: payment_type
        description: "Joins dim_payment.payment_type."
        tests:
          - relationships:
              to: ref('dim_payment')
              field: payment_type
      - name: ratecode_id
        description: "Joins dim_ratecode.ratecode_id."
```

Note: `ratecode_id` and `dropoff_location_id` may contain source values outside the seed dictionaries (e.g. RatecodeID 99 appears in raw NYC data). Do NOT add a `relationships` test on `ratecode_id` or on `dropoff_location_id` — those would fail on legitimately messy raw values that we deliberately kept. `pickup_location_id` (1–265) and `payment_type` (1–6) and `pickup_date` are safe to constrain.

- [ ] **Step 3: Build and test the fact**

Run:
```bash
docker compose run --rm dbt build --select fct_trips
```
Expected: `fct_trips` builds as a partitioned+clustered table; `not_null`/`unique`/`relationships` tests PASS.

Verify partitioning + clustering landed:
```bash
bq query --use_legacy_sql=false "SELECT ddl FROM \`taxi-chat-data.marts.INFORMATION_SCHEMA.TABLES\` WHERE table_name='fct_trips'"
```
Expected: DDL contains `PARTITION BY pickup_date` and `CLUSTER BY pickup_location_id`.

- [ ] **Step 4: Write the Polish learning note**

Create `docs/learn/faza-2-fact.md` (Polish): what a fact table is (measures at a grain, foreign keys to dimensions), why partition by `pickup_date` (time queries prune partitions → less scanned) and cluster by `pickup_location_id` (co-locates rows by zone), why we intentionally DON'T put a relationships test on `ratecode_id`/`dropoff_location_id` (raw data has out-of-dictionary values — a real governance nuance), and the concept (fact vs dimension, physical optimization, partition pruning, clustering).

- [ ] **Step 5: Commit**

```bash
git add dbt/models/marts/fct_trips.sql dbt/models/marts/_marts__models.yml docs/learn/faza-2-fact.md
git commit -m "feat: fct_trips fact (partitioned by pickup_date, clustered by location)"
```

---

## Task 6: Partitioning measurement (dry-run bytes_processed, before/after)

**Files:**
- Create: `analysis/__init__.py`, `analysis/measure_partitioning.py`
- Create: `tests/test_measure_partitioning.py`
- Create: `docs/learn/faza-2-partitioning-measurement.md`

**Interfaces:**
- Consumes: `marts.fct_trips` (Task 5). Uses the existing `.venv` + `google-cloud-bigquery` and ADC (this runs on the host, not in the dbt container).
- Produces:
  - `build_unpartitioned_copy(client, project) -> str` — creates `marts.fct_trips_unpartitioned` (same rows, no partition/cluster), returns its table id.
  - `dry_run_bytes(client, sql) -> int` — returns `total_bytes_processed` for a dry-run of `sql`.
  - `format_report(part_bytes: int, unpart_bytes: int) -> str` — pure function returning a human-readable before/after markdown block. **Unit-tested.**
  - `main()` — wires it together and writes the report note.

- [ ] **Step 1: Write the failing unit test for the pure formatter**

`tests/test_measure_partitioning.py`:
```python
from analysis.measure_partitioning import format_report


def test_format_report_shows_before_after_and_reduction():
    report = format_report(part_bytes=100_000_000, unpart_bytes=500_000_000)
    assert "500,000,000" in report          # unpartitioned (before)
    assert "100,000,000" in report          # partitioned (after)
    assert "80.0%" in report                # reduction = 1 - 100/500
```

- [ ] **Step 2: Run the test — verify it fails**

Run: `.venv/bin/python -m pytest tests/test_measure_partitioning.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'analysis.measure_partitioning'`.

- [ ] **Step 3: Implement `analysis/measure_partitioning.py`**

```python
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
```

- [ ] **Step 4: Run the unit test — verify it passes**

Run: `.venv/bin/python -m pytest tests/test_measure_partitioning.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Run the real measurement (integration, manual)**

Run:
```bash
.venv/bin/python -m analysis.measure_partitioning
```
Expected: prints the before/after report; the partitioned scan should be **smaller** than the unpartitioned scan (partition pruning on `pickup_date` + clustering on `pickup_location_id`). Writes `docs/learn/faza-2-partitioning-measurement.md`. Record the actual numbers.

If the two numbers are equal (no reduction), STOP and report — it means partitioning/clustering isn't being exercised by the query, and the fact config or the query predicate needs review (do not fake a reduction).

- [ ] **Step 6: Finish the Polish learning note**

The script writes `docs/learn/faza-2-partitioning-measurement.md` with the numbers. Extend it (in Polish) with a paragraph: why partition pruning reduces scanned bytes, why clustering helps on `pickup_location_id`, and the concept (BigQuery bills by bytes scanned — physical layout directly controls cost/performance; this is the "SQL optimization in BigQuery" job requirement, with a concrete measured figure).

- [ ] **Step 7: Commit**

```bash
git add analysis/ tests/test_measure_partitioning.py docs/learn/faza-2-partitioning-measurement.md
git commit -m "feat: measure partitioning/clustering scan reduction via dry-run"
```

---

## Task 7: End-to-end build + Faza 2 verification

**Files:** none new — consistency verification and status update.
- Modify: `README.md` (mark Faza 2 done)
- Create: `docs/learn/faza-2-e2e-verification.md`

**Interfaces:** uses the whole dbt project + the measurement script.

- [ ] **Step 1: Full clean build from scratch**

Run:
```bash
docker compose run --rm dbt build
```
Expected: `dbt build` runs seeds → staging → marts and ALL data tests in one go. End state: `Completed successfully`, 0 errors, 0 test failures. This is the primary Faza 2 deliverable (the whole warehouse builds and passes governance).

- [ ] **Step 2: Sanity query — star schema joins resolve**

Run (a query a human/LLM would ask — revenue by borough and payment method for one day):
```bash
bq query --use_legacy_sql=false "
SELECT l.borough, p.payment_desc, COUNT(*) AS trips, ROUND(SUM(f.total_amount),2) AS revenue
FROM \`taxi-chat-data.marts.fct_trips\` f
JOIN \`taxi-chat-data.marts.dim_location\` l ON f.pickup_location_id = l.location_id
JOIN \`taxi-chat-data.marts.dim_payment\`  p ON f.payment_type = p.payment_type
WHERE f.pickup_date = '2023-01-15'
GROUP BY 1, 2 ORDER BY revenue DESC LIMIT 10"
```
Expected: rows come back with real borough names (Manhattan, Queens, …) and payment descriptions (Credit card, Cash) — proving the star schema joins end to end. Record a couple of rows.

- [ ] **Step 3: Update README status**

In `README.md`, change `- [ ] Faza 2` to `- [x] Faza 2`.

- [ ] **Step 4: Write the Polish learning note**

Create `docs/learn/faza-2-e2e-verification.md` (Polish): what a full `dbt build` does (DAG: seeds → staging → marts, with tests as gates), how the star schema answers a business question via joins (borough + payment from ids), and the concept (dbt DAG/lineage, build-time data testing as a quality gate, the warehouse as the queryable product feeding Faza 3).

- [ ] **Step 5: Commit**

```bash
git add README.md docs/learn/faza-2-e2e-verification.md
git commit -m "docs: Faza 2 (dbt warehouse) complete and verified"
```

---

## Self-Review (done while writing this plan)

**Spec coverage (design sections):**
- §3 medallion / materialization (staging=view, marts=table) → Task 1 config, Task 3–5 ✅
- §3 staging reads only raw, stream-ready → Task 3 (source-based, single model) ✅
- §5.1 clean/cast/dedup/surrogate key → Task 3 ✅
- §5.2 four dimensions incl. seed-backed → Task 2 + Task 4 ✅
- §5.3 fact partitioned by pickup_date, clustered by pickup_location_id → Task 5 ✅
- §6 measurement (dry-run before/after) → Task 6 ✅
- §7 governance (tests + descriptions feeding RAG) → schema.yml files in Tasks 2–5 ✅
- §11 ADC in Docker, no key file → Task 1 ✅
- §10 testing strategy (dbt tests primary + manual integration + pure-logic unit test for the script) → Tasks 3–7 ✅
- §12 English code + Polish learning notes, no AI footer → every task ✅

**Placeholder scan:** No TBD/TODO; every step has concrete code/commands. The one conditional (Task 1 Step 2/3b dataset-naming) is resolved by including the `generate_schema_name` override up front. ✅

**Type consistency:** `stg_trips` output columns (Task 3) match what `dim_datetime`/`fct_trips` consume (Tasks 4–5): `pickup_date`, `pickup_location_id`, `trip_key`, etc. Seed columns (Task 2: `location_id`, `payment_type`, `ratecode_id`) match dimension `ref()`s and the fact's `relationships` targets (Task 5). `format_report(part_bytes, unpart_bytes)` signature identical in test and impl (Task 6). ✅

**Deliberate governance nuance flagged:** no `relationships` test on `ratecode_id`/`dropoff_location_id` (raw data carries out-of-dictionary codes we intentionally keep) — called out in Task 5 so a reviewer doesn't treat it as a missing test.

**Out of scope (later phases, own plans):** streaming/`stream.trips` merge (Faza 4), incremental fct_trips (Faza 4), RAG consumption of descriptions (Faza 3), Airflow orchestration (Faza 6).
