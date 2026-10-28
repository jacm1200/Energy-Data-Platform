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
        first_round_trip = (
            first_fold.astimezone(timezone.utc).astimezone(source_timezone).replace(tzinfo=None)
        )
        second_round_trip = (
            second_fold.astimezone(timezone.utc).astimezone(source_timezone).replace(tzinfo=None)
        )
        first_matches = first_round_trip == parsed
        second_matches = second_round_trip == parsed
        offsets_differ = first_fold.utcoffset() != second_fold.utcoffset()
        if first_matches and second_matches and offsets_differ:
            raise ValueError(f"Ambiguous local weather timestamp: {timestamp}")
        if not first_matches and not second_matches:
            raise ValueError(f"Nonexistent local weather timestamp: {timestamp}")
        parsed = first_fold if first_matches else second_fold

    return parsed.astimezone(timezone.utc)


def _validate_measurement(value: Any, field: str) -> None:
    # None is a legitimate missing observation and becomes SQL NULL.
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Weather measurement '{field}' must be numeric or null")
    if not math.isfinite(value):
        raise ValueError(f"Weather measurement '{field}' must be finite")
    if field in {"precipitation", "wind_speed_10m"} and value < 0:
        raise ValueError(f"Weather measurement '{field}' cannot be negative")


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

    if not all(isinstance(values, list) for values in (times, temperatures, precipitation_values)):
        raise ValueError("Weather hourly fields must be lists")
    wind_values = hourly.get("wind_speed_10m", [None] * len(times))
    if not isinstance(wind_values, list):
        raise ValueError("Weather hourly fields must be lists")

    lengths = {
        len(times),
        len(temperatures),
        len(precipitation_values),
        len(wind_values),
    }
    if len(lengths) != 1:
        raise ValueError("Weather hourly fields must have the same number of values")

    rows: list[dict[str, Any]] = []
    seen_timestamps: set[datetime] = set()
    for timestamp, temperature, precipitation, wind in zip(
        times,
        temperatures,
        precipitation_values,
        wind_values,
    ):
        observed_at = _to_utc(timestamp, source_timezone)
        if observed_at in seen_timestamps:
            raise ValueError(f"Duplicate weather timestamp: {timestamp}")
        seen_timestamps.add(observed_at)
        _validate_measurement(temperature, "temperature_2m")
        _validate_measurement(precipitation, "precipitation")
        _validate_measurement(wind, "wind_speed_10m")

        rows.append(
            {
                "source": "open_meteo",
                "observed_at": observed_at,
                "latitude": latitude,
                "longitude": longitude,
                "temperature_2m": temperature,
                "precipitation_mm": precipitation,
                "wind_speed_10m_ms": wind,
            }
        )

    return rows
