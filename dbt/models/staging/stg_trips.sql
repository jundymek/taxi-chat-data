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
