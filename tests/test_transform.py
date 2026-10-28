from datetime import datetime, timezone

import pytest

from energy_platform.transform import weather_to_rows


def test_weather_to_rows_pairs_hourly_values():
    payload = {
        "latitude": 40.4168,
        "longitude": -3.7038,
        "timezone": "Europe/Madrid",
        "hourly": {
            "time": ["2026-01-01T00:00", "2026-01-01T01:00"],
            "temperature_2m": [1.9, 1.5],
            "precipitation": [0.0, 0.2],
        }
    }

    rows = weather_to_rows(payload)

    assert rows == [
        {
            "source": "open_meteo",
            "observed_at": datetime(2025, 12, 31, 23, tzinfo=timezone.utc),
            "latitude": 40.4168,
            "longitude": -3.7038,
            "temperature_2m": 1.9,
            "precipitation_mm": 0.0,
        },
        {
            "source": "open_meteo",
            "observed_at": datetime(2026, 1, 1, 0, tzinfo=timezone.utc),
            "latitude": 40.4168,
            "longitude": -3.7038,
            "temperature_2m": 1.5,
            "precipitation_mm": 0.2,
        },
    ]


def test_weather_to_rows_rejects_different_list_lengths():
    payload = {
        "latitude": 40.4168,
        "longitude": -3.7038,
        "timezone": "Europe/Madrid",
        "hourly": {
            "time": ["2026-01-01T00:00", "2026-01-01T01:00"],
            "temperature_2m": [1.9],
            "precipitation": [0.0, 0.2],
        }
    }

    with pytest.raises(ValueError, match="same number of values"):
        weather_to_rows(payload)


def test_weather_to_rows_converts_local_time_to_utc():
    payload = {
        "latitude": 40.4168,
        "longitude": -3.7038,
        "timezone": "Europe/Madrid",
        "hourly": {
            "time": ["2026-01-01T00:00"],
            "temperature_2m": [1.9],
            "precipitation": [0.0],
        },
    }

    rows = weather_to_rows(payload)

    assert rows[0]["observed_at"] == datetime(
        2025,
        12,
        31,
        23,
        tzinfo=timezone.utc,
    )


def test_weather_to_rows_requires_coordinates():
    payload = {
        "timezone": "Europe/Madrid",
        "hourly": {
            "time": [],
            "temperature_2m": [],
            "precipitation": [],
        },
    }

    with pytest.raises(ValueError, match="numeric latitude and longitude"):
        weather_to_rows(payload)


def test_weather_to_rows_rejects_coordinates_out_of_range():
    payload = {
        "latitude": 91,
        "longitude": -3.7,
        "timezone": "UTC",
        "hourly": {
            "time": [],
            "temperature_2m": [],
            "precipitation": [],
        },
    }

    with pytest.raises(ValueError, match="numeric latitude and longitude"):
        weather_to_rows(payload)


def test_weather_to_rows_rejects_invalid_timestamp():
    payload = {
        "latitude": 40.4,
        "longitude": -3.7,
        "timezone": "UTC",
        "hourly": {
            "time": ["not-a-timestamp"],
            "temperature_2m": [1.0],
            "precipitation": [0.0],
        },
    }

    with pytest.raises(ValueError, match="Invalid weather timestamp"):
        weather_to_rows(payload)


def test_weather_to_rows_rejects_negative_precipitation():
    payload = {
        "latitude": 40.4,
        "longitude": -3.7,
        "timezone": "UTC",
        "hourly": {
            "time": ["2026-01-01T00:00"],
            "temperature_2m": [1.0],
            "precipitation": [-0.1],
        },
    }

    with pytest.raises(ValueError, match="cannot be negative"):
        weather_to_rows(payload)


def test_weather_to_rows_preserves_missing_measurements():
    payload = {
        "latitude": 40.4,
        "longitude": -3.7,
        "timezone": "UTC",
        "hourly": {
            "time": ["2026-01-01T00:00"],
            "temperature_2m": [None],
            "precipitation": [None],
        },
    }

    rows = weather_to_rows(payload)

    assert rows[0]["temperature_2m"] is None
    assert rows[0]["precipitation_mm"] is None


def test_weather_to_rows_rejects_ambiguous_local_time():
    payload = {
        "latitude": 40.4,
        "longitude": -3.7,
        "timezone": "Europe/Madrid",
        "hourly": {
            "time": ["2026-10-25T02:00"],
            "temperature_2m": [10.0],
            "precipitation": [0.0],
        },
    }

    with pytest.raises(ValueError, match="Ambiguous local weather timestamp"):
        weather_to_rows(payload)


def test_weather_to_rows_rejects_duplicate_timestamps():
    payload = {
        "latitude": 40.4,
        "longitude": -3.7,
        "timezone": "UTC",
        "hourly": {
            "time": ["2026-01-01T00:00", "2026-01-01T00:00"],
            "temperature_2m": [1.0, 1.1],
            "precipitation": [0.0, 0.0],
        },
    }

    with pytest.raises(ValueError, match="Duplicate weather timestamp"):
        weather_to_rows(payload)
