"""Convert Open-Meteo's column-oriented hourly payload into row records."""

import math
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _to_utc(timestamp: Any, source_timezone: ZoneInfo) -> datetime:
    if not isinstance(timestamp, str):
        raise ValueError("Weather timestamps must be strings")
    try:
        parsed = datetime.fromisoformat(timestamp)
    except ValueError as exc:
        raise ValueError(f"Invalid weather timestamp: {timestamp}") from exc

    if parsed.tzinfo is None:
        first_fold = parsed.replace(tzinfo=source_timezone, fold=0)
        second_fold = parsed.replace(tzinfo=source_timezone, fold=1)
        if first_fold.utcoffset() != second_fold.utcoffset():
            raise ValueError(f"Ambiguous local weather timestamp: {timestamp}")

        round_trip = (
            first_fold
            .astimezone(timezone.utc)
            .astimezone(source_timezone)
            .replace(tzinfo=None)
        )
        if round_trip != parsed:
            raise ValueError(f"Nonexistent local weather timestamp: {timestamp}")
        parsed = first_fold

    return parsed.astimezone(timezone.utc)


def _validate_measurement(value: Any, field: str) -> None:
    # None is a legitimate missing observation and becomes SQL NULL.
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Weather measurement '{field}' must be numeric or null")
    if not math.isfinite(value):
        raise ValueError(f"Weather measurement '{field}' must be finite")
    if field == "precipitation" and value < 0:
        raise ValueError("Weather precipitation cannot be negative")


def weather_to_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Pair each timestamp with its temperature and precipitation values."""
    latitude = payload.get("latitude")
    longitude = payload.get("longitude")
    if (
        isinstance(latitude, bool)
        or isinstance(longitude, bool)
        or not isinstance(latitude, (int, float))
        or not isinstance(longitude, (int, float))
        or not math.isfinite(latitude)
        or not math.isfinite(longitude)
        or not -90 <= latitude <= 90
        or not -180 <= longitude <= 180
    ):
        raise ValueError("Weather payload must contain numeric latitude and longitude")

    hourly = payload.get("hourly")
    if not isinstance(hourly, dict):
        raise ValueError("Weather payload must contain an 'hourly' object")

    timezone_name = payload.get("timezone")
    if not isinstance(timezone_name, str):
        raise ValueError("Weather payload must contain a timezone name")
    try:
        source_timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown weather timezone: {timezone_name}") from exc

    required_fields = (
        "time",
        "temperature_2m",
        "precipitation",
    )
    for field in required_fields:
        if field not in hourly:
            raise ValueError(f"Weather hourly data is missing '{field}'")

    times = hourly["time"]
    temperatures = hourly["temperature_2m"]
    precipitation_values = hourly["precipitation"]

    if not all(
        isinstance(values, list)
        for values in (times, temperatures, precipitation_values)
    ):
        raise ValueError("Weather hourly fields must be lists")

    lengths = {
        len(times),
        len(temperatures),
        len(precipitation_values),
    }
    if len(lengths) != 1:
        raise ValueError("Weather hourly fields must have the same number of values")

    rows = []
    seen_timestamps = set()
    for timestamp, temperature, precipitation in zip(
        times,
        temperatures,
        precipitation_values,
    ):
        observed_at = _to_utc(timestamp, source_timezone)
        if observed_at in seen_timestamps:
            raise ValueError(f"Duplicate weather timestamp: {timestamp}")
        seen_timestamps.add(observed_at)
        _validate_measurement(temperature, "temperature_2m")
        _validate_measurement(precipitation, "precipitation")

        rows.append(
            {
                "source": "open_meteo",
                "observed_at": observed_at,
                "latitude": latitude,
                "longitude": longitude,
                "temperature_2m": temperature,
                "precipitation_mm": precipitation,
            }
        )

    return rows
