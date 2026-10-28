import json
from datetime import date
from urllib.error import HTTPError, URLError

import pytest

from energy_platform import ingest


def test_weather_url_encodes_expected_query():
    url = ingest.weather_url(
        date(2026, 1, 1),
        date(2026, 1, 2),
        40.4,
        -3.7,
        "Europe/Madrid",
    )
    assert url.startswith(ingest.WEATHER_URL + "?")
    assert "start_date=2026-01-01" in url
    assert "hourly=temperature_2m%2Cprecipitation%2Cwind_speed_10m" in url
    assert "wind_speed_unit=ms" in url


def test_landing_preserves_each_response(tmp_path):
    first = ingest.land_response(
        tmp_path,
        "source",
        date(2026, 1, 1),
        date(2026, 1, 2),
        "json",
        b"one",
    )
    second = ingest.land_response(
        tmp_path,
        "source",
        date(2026, 1, 1),
        date(2026, 1, 2),
        "json",
        b"two",
    )
    assert first != second
    assert first.read_bytes() == b"one"
    assert second.read_bytes() == b"two"


def test_weather_rejects_unexpected_response(tmp_path, monkeypatch):
    monkeypatch.setattr(
        ingest,
        "fetch_bytes",
        lambda _url: json.dumps({"error": True}).encode(),
    )
    with pytest.raises(ValueError, match="expected hourly data"):
        ingest.ingest_weather(tmp_path, date(2026, 1, 1), date(2026, 1, 2))


def test_weather_rejects_empty_response(tmp_path, monkeypatch):
    monkeypatch.setattr(ingest, "fetch_bytes", lambda _url: b"  ")

    with pytest.raises(ValueError, match="empty response"):
        ingest.ingest_weather(tmp_path, date(2026, 1, 1), date(2026, 1, 2))


@pytest.mark.parametrize("body", [b"null", b"[]"])
def test_weather_rejects_non_object_response(tmp_path, monkeypatch, body):
    monkeypatch.setattr(ingest, "fetch_bytes", lambda _url: body)

    with pytest.raises(ValueError, match="expected hourly data"):
        ingest.ingest_weather(tmp_path, date(2026, 1, 1), date(2026, 1, 2))


def test_weather_rejects_mismatched_api_arrays(tmp_path, monkeypatch):
    body = json.dumps(
        {
            "hourly": {
                "time": ["2026-01-01T00:00"],
                "temperature_2m": [1.0],
                "precipitation": [0.0],
                "wind_speed_10m": [],
            },
            "hourly_units": {
                "temperature_2m": "°C",
                "precipitation": "mm",
                "wind_speed_10m": "m/s",
            },
        }
    ).encode()
    monkeypatch.setattr(ingest, "fetch_bytes", lambda _url: body)

    with pytest.raises(ValueError, match="different lengths"):
        ingest.ingest_weather(tmp_path, date(2026, 1, 1), date(2026, 1, 2))


def test_weather_lands_valid_payload_with_wind(tmp_path, monkeypatch):
    payload = {
        "hourly": {
            "time": ["2026-01-01T00:00"],
            "temperature_2m": [1.0],
            "precipitation": [0.0],
            "wind_speed_10m": [2.5],
        },
        "hourly_units": {
            "temperature_2m": "\N{DEGREE SIGN}C",
            "precipitation": "mm",
            "wind_speed_10m": "m/s",
        },
    }
    body = json.dumps(payload).encode()
    monkeypatch.setattr(ingest, "fetch_bytes", lambda _url: body)

    path = ingest.ingest_weather(tmp_path, date(2026, 1, 1), date(2026, 1, 2))

    assert json.loads(path.read_bytes()) == payload


def test_weather_rejects_unexpected_wind_unit(tmp_path, monkeypatch):
    payload = {
        "hourly": {
            "time": ["2026-01-01T00:00"],
            "temperature_2m": [1.0],
            "precipitation": [0.0],
            "wind_speed_10m": [2.5],
        },
        "hourly_units": {
            "temperature_2m": "°C",
            "precipitation": "mm",
            "wind_speed_10m": "km/h",
        },
    }
    monkeypatch.setattr(ingest, "fetch_bytes", lambda _url: json.dumps(payload).encode())

    with pytest.raises(ValueError, match="wind_speed_10m.*must be m/s"):
        ingest.ingest_weather(tmp_path, date(2026, 1, 1), date(2026, 1, 2))


def test_fetch_retries_temporary_connection_error(monkeypatch):
    attempts = 0

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return b"payload"

    def fake_urlopen(_request, timeout):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise URLError("temporary failure")
        return Response()

    monkeypatch.setattr(ingest.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(ingest.time, "sleep", lambda _seconds: None)

    assert ingest.fetch_bytes("https://example.test", max_attempts=2) == b"payload"
    assert attempts == 2


def test_fetch_retries_rate_limit(monkeypatch):
    attempts = 0

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return b"payload"

    def fake_urlopen(_request, timeout):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise HTTPError("https://example.test", 429, "rate limited", {}, None)
        return Response()

    monkeypatch.setattr(ingest.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(ingest.time, "sleep", lambda _seconds: None)

    assert ingest.fetch_bytes("https://example.test", max_attempts=2) == b"payload"
    assert attempts == 2


def test_fetch_does_not_retry_client_errors(monkeypatch):
    attempts = 0

    def fake_urlopen(_request, timeout):
        nonlocal attempts
        attempts += 1
        raise HTTPError("https://example.test", 401, "unauthorized", {}, None)

    monkeypatch.setattr(ingest.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(HTTPError):
        ingest.fetch_bytes("https://example.test", max_attempts=3)
    assert attempts == 1


def test_entsoe_requires_token(tmp_path, monkeypatch):
    monkeypatch.delenv("ENTSOE_API_TOKEN", raising=False)

    with pytest.raises(ValueError, match="ENTSOE_API_TOKEN"):
        ingest.ingest_entsoe(
            tmp_path,
            date(2026, 1, 1),
            date(2026, 1, 2),
        )
