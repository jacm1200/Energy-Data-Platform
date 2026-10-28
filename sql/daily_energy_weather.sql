WITH daily_prices AS (
    SELECT
        (delivery_start AT TIME ZONE 'UTC')::date AS day_utc,
        area_code,
        currency,
        price_unit,
        AVG(price_amount)::double precision AS average_price,
        COUNT(price_amount) AS price_intervals
    FROM day_ahead_prices
    GROUP BY 1, 2, 3, 4
),
daily_weather AS (
    SELECT
        (observed_at AT TIME ZONE 'UTC')::date AS day_utc,
        AVG(temperature_2m) AS average_temperature_c,
        AVG(wind_speed_10m_ms) AS average_wind_speed_m_s,
        COUNT(temperature_2m) AS temperature_observations,
        COUNT(wind_speed_10m_ms) AS wind_observations
    FROM weather_observations
    GROUP BY 1
)
SELECT
    prices.day_utc,
    prices.area_code,
    prices.currency,
    prices.price_unit,
    prices.average_price,
    prices.price_intervals,
    weather.average_temperature_c,
    weather.average_wind_speed_m_s,
    weather.temperature_observations,
    weather.wind_observations
FROM daily_prices AS prices
INNER JOIN daily_weather AS weather USING (day_utc)
ORDER BY prices.day_utc, prices.area_code;
