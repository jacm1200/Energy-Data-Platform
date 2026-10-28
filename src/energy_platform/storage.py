"""PostgreSQL persistence for normalized weather rows."""

from typing import Any

import psycopg

CREATE_WEATHER_TABLE = """
CREATE TABLE IF NOT EXISTS weather_observations (
    source TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    temperature_2m DOUBLE PRECISION,
    precipitation_mm DOUBLE PRECISION,
    PRIMARY KEY (source, observed_at, latitude, longitude)
)
"""

UPSERT_WEATHER_ROW = """
INSERT INTO weather_observations (
    source,
    observed_at,
    latitude,
    longitude,
    temperature_2m,
    precipitation_mm
)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (source, observed_at, latitude, longitude)
DO UPDATE SET
    temperature_2m = EXCLUDED.temperature_2m,
    precipitation_mm = EXCLUDED.precipitation_mm
"""

CREATE_DAY_AHEAD_PRICES_TABLE = """
CREATE TABLE IF NOT EXISTS day_ahead_prices (
    source TEXT NOT NULL,
    area_code TEXT NOT NULL,
    delivery_start TIMESTAMPTZ NOT NULL,
    price_amount NUMERIC,
    currency TEXT NOT NULL,
    price_unit TEXT NOT NULL,
    PRIMARY KEY (source, area_code, delivery_start)
)
"""

UPSERT_DAY_AHEAD_PRICE = """
INSERT INTO day_ahead_prices (
    source,
    area_code,
    delivery_start,
    price_amount,
    currency,
    price_unit
)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (source, area_code, delivery_start)
DO UPDATE SET
    price_amount = EXCLUDED.price_amount,
    currency = EXCLUDED.currency,
    price_unit = EXCLUDED.price_unit
"""


def upsert_weather_rows(
    rows: list[dict[str, Any]],
    database_url: str,
) -> int:
    """Create the weather table if needed and idempotently write its rows."""
    values = [
        (
            row["source"],
            row["observed_at"],
            row["latitude"],
            row["longitude"],
            row["temperature_2m"],
            row["precipitation_mm"],
        )
        for row in rows
    ]

    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(CREATE_WEATHER_TABLE)
            if values:
                cursor.executemany(UPSERT_WEATHER_ROW, values)

    return len(values)


def upsert_day_ahead_prices(
    rows: list[dict[str, Any]],
    database_url: str,
) -> int:
    """Create the price table if needed and idempotently write its rows."""
    values = [
        (
            row["source"],
            row["area_code"],
            row["delivery_start"],
            row["price_amount"],
            row["currency"],
            row["price_unit"],
        )
        for row in rows
    ]

    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(CREATE_DAY_AHEAD_PRICES_TABLE)
            if values:
                cursor.executemany(UPSERT_DAY_AHEAD_PRICE, values)

    return len(values)
