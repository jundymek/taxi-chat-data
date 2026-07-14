{{ config(materialized='table') }}

select
    ratecode_id,
    ratecode_desc
from {{ ref('ratecode_lookup') }}
