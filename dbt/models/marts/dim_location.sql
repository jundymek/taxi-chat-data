{{ config(materialized='table') }}

select
    location_id,
    borough,
    zone,
    service_zone
from {{ ref('taxi_zone_lookup') }}
