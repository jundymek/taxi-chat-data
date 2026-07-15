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
