select
    request_id,
    latitude,
    longitude,
    timezone,
    requested_at,
    raw_payload
from {{ source('raw', 'weather_requests') }}

