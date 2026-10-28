import json
from datetime import date

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
    assert "hourly=temperature_2m%2Cprecipitation" in url


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


def test_entsoe_requires_token(tmp_path, monkeypatch):
    monkeypatch.delenv("ENTSOE_API_TOKEN", raising=False)

    with pytest.raises(ValueError, match="ENTSOE_API_TOKEN"):
        ingest.ingest_entsoe(
            tmp_path,
            date(2026, 1, 1),
            date(2026, 1, 2),
        )
