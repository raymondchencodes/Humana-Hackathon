{{
    config(
        materialized='view'
    )
}}

-- This code "points" to the raw BigQuery table defined in sources.yml
-- It does not move the data; it just creates a window to look at it.

SELECT 
WITH source AS (
    SELECT * FROM {{ source('raw_humana', 'claims') }}
)

SELECT
    -- Best practice: eventually replace * with explicit column names
    *
FROM {{ source('raw_humana', 'claims') }}
FROM source