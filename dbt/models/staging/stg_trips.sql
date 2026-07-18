{{ config(materialized='view') }}

with raw_source as (
    select * from {{ source('raw', 'trips') }}
),

raw_cleaned as (
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
    from raw_source
    where fare_amount >= 0
      and total_amount >= 0
      and trip_distance > 0
      and tpep_dropoff_datetime >= tpep_pickup_datetime
      and date(tpep_pickup_datetime) >= '2009-01-01'
      and tpep_pickup_datetime <= current_timestamp()
),

stream_source as (
    select * from {{ source('stream', 'trips') }}
),

stream_cleaned as (
    select
        -- Recompute the key from the stream's columns with the SAME recipe as
        -- raw_cleaned, so a trip that arrived via both paths dedups to one row.
        {{ dbt_utils.generate_surrogate_key([
            'pickup_datetime',
            'dropoff_datetime',
            'pickup_location_id',
            'dropoff_location_id',
            'fare_amount',
            'vendor_id'
        ]) }}                                              as trip_key,
        vendor_id                                          as vendor_id,
        pickup_datetime                                    as pickup_datetime,
        dropoff_datetime                                   as dropoff_datetime,
        date(pickup_datetime)                              as pickup_date,
        timestamp_diff(
            dropoff_datetime, pickup_datetime, minute
        )                                                  as trip_duration_min,
        cast(passenger_count as int64)                     as passenger_count,
        trip_distance                                      as trip_distance,
        cast(ratecode_id as int64)                         as ratecode_id,
        pickup_location_id                                 as pickup_location_id,
        dropoff_location_id                                as dropoff_location_id,
        payment_type                                       as payment_type,
        fare_amount                                        as fare_amount,
        tip_amount                                         as tip_amount,
        tolls_amount                                       as tolls_amount,
        total_amount                                       as total_amount
    from stream_source
    where fare_amount >= 0
      and total_amount >= 0
      and trip_distance > 0
      and dropoff_datetime >= pickup_datetime
      and date(pickup_datetime) >= '2009-01-01'
      and pickup_datetime <= current_timestamp()
),

unioned as (
    -- source_rank makes raw (the authoritative batch load) win over the
    -- simulated stream when a trip arrived via both paths; to_json_string gives
    -- a fully content-deterministic final tie-break. pickup_datetime alone is
    -- NOT enough: it is part of trip_key, so every duplicate pair ties on it and
    -- BigQuery would pick a winner arbitrarily, flapping stg_trips across builds.
    select 0 as source_rank, raw_cleaned.*    from raw_cleaned
    union all
    select 1 as source_rank, stream_cleaned.* from stream_cleaned
),

deduped as (
    select * except (source_rank)
    from unioned
    qualify row_number() over (
        partition by trip_key
        order by source_rank, to_json_string(unioned)
    ) = 1
)

select * from deduped
