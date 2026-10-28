from datetime import datetime, timezone

from energy_platform import storage


def test_weather_upsert_migrates_wind_column_and_writes_measurements(monkeypatch):
    statements = []
    batches = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, statement):
            statements.append(statement)

        def executemany(self, statement, values):
            statements.append(statement)
            batches.extend(values)

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def cursor(self):
            return Cursor()

    monkeypatch.setattr(storage.psycopg, "connect", lambda _url: Connection())
    rows = [
        {
            "source": "open_meteo",
            "observed_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
            "latitude": 40.4,
            "longitude": -3.7,
            "temperature_2m": 10.0,
            "precipitation_mm": 0.1,
            "wind_speed_10m_ms": 5.2,
        }
    ]

    count = storage.upsert_weather_rows(rows, "postgresql://test")

    assert count == 1
    assert "CREATE TABLE IF NOT EXISTS weather_observations" in statements[0]
    assert "ADD COLUMN IF NOT EXISTS wind_speed_10m_ms" in statements[1]
    assert "ON CONFLICT" in statements[2]
    assert batches[0][-1] == 5.2
