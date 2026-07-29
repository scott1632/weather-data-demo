select
    w.weather_id,
    w.request_id,
    w.observation_time,
    w.latitude,
    w.longitude,
    w.temperature,
    w.apparent_temperature,
    w.precipitation,
    w.wind_speed,
    w.weather_code,
    w.ingested_at,
    r.requested_at as request_time
from {{ source('raw', 'weather') }} w
left join {{ source('raw', 'weather_requests') }} r
    on w.request_id = r.request_id

