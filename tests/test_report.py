from datetime import date

from energy_platform import report
from energy_platform.report import render_svg


def test_render_svg_includes_descriptive_series_and_attribution():
    rows = [
        (date(2026, 1, 1), "10YES-REE------0", "EUR", "MWH", 50.0, 24, 8.0, 3.0, 24, 24),
        (date(2026, 1, 2), "10YES-REE------0", "EUR", "MWH", 60.0, 24, 9.0, 4.0, 24, 24),
    ]

    svg = render_svg(rows)

    assert "Daily average price (EUR/MWh)" in svg
    assert "Daily average temperature" in svg
    assert "Daily average wind speed" in svg
    assert "Weather data by Open-Meteo.com (CC BY 4.0)" in svg
    assert "2026-01-01 to 2026-01-02" in svg


def test_render_svg_explains_when_there_are_no_overlapping_days():
    svg = render_svg([])

    assert "No overlapping UTC dates" in svg


def test_generate_report_writes_query_results_as_svg_and_csv(tmp_path, monkeypatch):
    rows = [(date(2026, 1, 1), "10YES-REE------0", "EUR", "MWH", 20.125, 4, 8.0, 3.5, 24, 24)]

    class Result:
        def fetchall(self):
            return rows

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, _query):
            return Result()

    monkeypatch.setattr(report.psycopg, "connect", lambda _url: Connection())
    query_file = tmp_path / "query.sql"
    query_file.write_text("SELECT fixture", encoding="utf-8")
    svg_file = tmp_path / "report.svg"
    csv_file = tmp_path / "report.csv"

    count = report.generate_report(
        "postgresql://test",
        output_file=svg_file,
        query_file=query_file,
        csv_file=csv_file,
    )

    assert count == 1
    assert "Coverage: 4 price intervals" in svg_file.read_text(encoding="utf-8")
    assert "2026-01-01,10YES-REE------0,EUR,MWH,20.125,4" in csv_file.read_text(encoding="utf-8")
