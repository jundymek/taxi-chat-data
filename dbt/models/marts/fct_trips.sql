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
