from datetime import date

from energy_platform import report
from energy_platform.report import render_svg


def _relative_luminance(color: str) -> float:
    channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    ]
    return sum(weight * channel for weight, channel in zip((0.2126, 0.7152, 0.0722), linear))


def _contrast_ratio(foreground: str, background: str) -> float:
    luminances = sorted((_relative_luminance(foreground), _relative_luminance(background)))
    return (luminances[1] + 0.05) / (luminances[0] + 0.05)


def test_render_svg_includes_descriptive_series_and_attribution():
    rows = [
        (date(2026, 1, 1), "10YES-REE------0", "EUR", "MWH", 50.0, 24, 8.0, 3.0, 24, 24),
        (date(2026, 1, 2), "10YES-REE------0", "EUR", "MWH", 60.0, 24, 9.0, 4.0, 24, 24),
        (date(2026, 1, 3), "10YES-REE------0", "EUR", "MWH", 55.0, 24, 8.5, 3.5, 24, 24),
    ]

    svg = render_svg(rows)

    assert "Daily average price (EUR/MWh)" in svg
    assert "Daily average temperature" in svg
    assert "Daily average wind speed" in svg
    assert "Weather data by Open-Meteo.com (CC BY 4.0)" in svg
    assert "2026-01-01 to 2026-01-03" in svg


def test_render_svg_explains_when_there_are_no_overlapping_days():
    svg = render_svg([])

    assert "No overlapping UTC dates" in svg
    assert "Insufficient data for a trend (0 days)" in svg


def test_fewer_than_three_days_render_value_cards_instead_of_points():
    rows = [
        (date(2026, 1, 1), "10YES-REE------0", "EUR", "MWH", 20.125, 4, 1.2, 1.07, 24, 24),
        (date(2026, 1, 2), "10YES-REE------0", "EUR", "MWH", 21.0, 24, 2.0, 2.0, 24, 24),
    ]

    svg = render_svg(rows)

    assert "Insufficient data for a trend (2 days)" in svg
    assert svg.count('<rect x="') == 2
    assert "20.12 EUR/MWh" in svg
    assert "1.07 m/s (24 observations)" in svg
    assert "<polyline" not in svg
    assert "<circle" not in svg


def test_equal_series_values_show_one_tick_per_axis():
    rows = [
        (date(2026, 1, day), "10YES-REE------0", "EUR", "MWH", 10.0, 24, 1.0, 2.0, 24, 24)
        for day in (1, 2, 3)
    ]

    svg = render_svg(rows)

    assert svg.count(">10.00</text>") == 1
    assert svg.count(">1.00</text>") == 1
    assert svg.count(">2.00</text>") == 1


def test_synthetic_flag_marks_title_and_note():
    row = (date(2026, 1, 1), "10YES-REE------0", "EUR", "MWH", 20.125, 4, 1.2, 1.07, 24, 24)

    svg = render_svg([row], synthetic=True)

    assert svg.count(report.SYNTHETIC_LABEL) == 2
    assert "Insufficient data for a trend (1 day)" in svg


def test_svg_has_white_background_and_standard_price_unit():
    row = (date(2026, 1, 1), "10YES-REE------0", "EUR", "MWH", 20.125, 4, 1.2, 1.07, 24, 24)

    svg = render_svg([row], synthetic=True)

    assert svg.splitlines()[1] == '<rect width="100%" height="100%" fill="#ffffff"/>'
    assert "EUR/MWh" in svg
    assert "EUR/MWH" not in svg


def test_svg_text_colors_have_sufficient_contrast_on_white():
    svg = render_svg([], synthetic=True)

    assert _contrast_ratio(report.TEXT_COLOR, report.BACKGROUND_COLOR) >= 4.5
    assert _contrast_ratio(report.ALERT_COLOR, report.BACKGROUND_COLOR) >= 4.5
    assert f"fill:{report.TEXT_COLOR}" in svg
    assert f"fill:{report.ALERT_COLOR}" in svg


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
    csv_output = csv_file.read_text(encoding="utf-8")
    assert "price_unit_label" in csv_output.splitlines()[0]
    assert "2026-01-01,10YES-REE------0,EUR,MWh,EUR/MWh,20.125,4" in csv_output


def test_cli_synthetic_flag_is_explicit_and_forwarded(monkeypatch):
    captured = {}

    def fake_generate_report(database_url, *, synthetic=False):
        captured["database_url"] = database_url
        captured["synthetic"] = synthetic
        return 1

    monkeypatch.setenv("DATABASE_URL", "postgresql://test")
    monkeypatch.setattr(report, "generate_report", fake_generate_report)

    result = report.main(["--synthetic"])

    assert result == 0
    assert captured == {"database_url": "postgresql://test", "synthetic": True}
