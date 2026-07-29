-- Test that temperature values are within realistic ranges
-- Catches data quality issues from the API or transformation layer
select *
from {{ ref('fact_weather_observation') }}
where temperature_c < -80
   or temperature_c > 70
