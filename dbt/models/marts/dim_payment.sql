{{ config(materialized='table') }}

select
    payment_type,
    payment_desc
from {{ ref('payment_type_lookup') }}
