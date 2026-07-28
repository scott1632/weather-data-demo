select
    w.weather_id,
    w.observation_time,
    w.latitude,
    w.longitude,
    w.temperature as temperature_c,
    w.apparent_temperature as apparent_temperature_c,
    w.precipitation as precipitation_mm,
    w.wind_speed as wind_speed_kmh,
    w.weather_code,
    r.requested_at as source_request_time
from {{ ref('stg_weather') }} w
left join {{ ref('stg_weather_requests') }} r
    on w.request_id = r.request_id

