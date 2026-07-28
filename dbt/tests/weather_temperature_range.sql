select *

from {{ ref('fact_weather_observation') }}

where temperature_c < -80
   or temperature_c > 70

