"""Generate an SVG comparison of daily electricity and weather averages."""

from __future__ import annotations

import logging
import os
import csv
from pathlib import Path
from typing import Any

import psycopg
from dotenv import load_dotenv
from energy_platform.logging_utils import configure_logging

PROJECT_ROOT = Path(__file__).resolve().parents[2]
QUERY_FILE = PROJECT_ROOT / "sql" / "daily_energy_weather.sql"
OUTPUT_FILE = PROJECT_ROOT / "docs" / "daily_energy_weather.svg"
OUTPUT_CSV = PROJECT_ROOT / "docs" / "daily_energy_weather.csv"
WIDTH = 960
HEIGHT = 800
LEFT = 90
RIGHT = 30
PANEL_HEIGHT = 170
PANEL_TOPS = (90, 315, 540)
logger = logging.getLogger(__name__)


def _panel(
    rows: list[tuple[Any, ...]],
    *,
    value_index: int,
    title: str,
    color: str,
    panel_index: int,
) -> list[str]:
    values = [float(row[value_index]) if row[value_index] is not None else None for row in rows]
    available = [value for value in values if value is not None]
    top = PANEL_TOPS[panel_index]
    bottom = top + PANEL_HEIGHT
    lines = [
        f'<text x="{LEFT}" y="{top - 18}" class="title">{title}</text>',
        f'<line x1="{LEFT}" y1="{bottom}" x2="{WIDTH - RIGHT}" y2="{bottom}" class="axis"/>',
    ]
    if not available:
        lines.append(f'<text x="{LEFT}" y="{top + 30}" class="note">No values available</text>')
        return lines

    minimum = min(available)
    maximum = max(available)
    span = maximum - minimum or 1.0
    count = len(rows)
    points = []
    for index, value in enumerate(values):
        if value is None:
            continue
        x = LEFT + index * (WIDTH - LEFT - RIGHT) / max(count - 1, 1)
        y = bottom - (value - minimum) / span * PANEL_HEIGHT
        points.append(f"{x:.1f},{y:.1f}")
    if len(points) == 1:
        x, y = points[0].split(",")
        lines.append(f'<circle cx="{x}" cy="{y}" r="4" fill="{color}"/>')
    elif points:
        lines.append(
            f'<polyline points="{" ".join(points)}" fill="none" stroke="{color}" stroke-width="3"/>'
        )
    lines.append(
        f'<text x="{LEFT - 12}" y="{top + 4}" text-anchor="end" class="tick">{maximum:.2f}</text>'
    )
    lines.append(
        f'<text x="{LEFT - 12}" y="{bottom}" text-anchor="end" class="tick">{minimum:.2f}</text>'
    )
    return lines


def render_svg(rows: list[tuple[Any, ...]]) -> str:
    """Render query rows as a dependency-free three-panel SVG chart."""
    header = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">',
        "<style>text{font-family:Arial,sans-serif;fill:#172033}.title{font-size:18px;font-weight:bold}.tick,.note{font-size:12px}.axis{stroke:#9aa4b2;stroke-width:1}</style>",
        '<text x="90" y="28" class="title">Daily electricity price and weather (UTC)</text>',
    ]
    if rows:
        prices = sum(int(row[5]) for row in rows)
        temperatures = sum(int(row[8]) for row in rows)
        winds = sum(int(row[9]) for row in rows)
        header.append(
            f'<text x="90" y="48" class="note">Coverage: {prices} price intervals; '
            f"{temperatures} temperature and {winds} wind observations</text>"
        )
    panels = [
        *_panel(
            rows,
            value_index=4,
            title="Daily average price (EUR/MWh)",
            color="#be3c35",
            panel_index=0,
        ),
        *_panel(
            rows,
            value_index=6,
            title="Daily average temperature (°C)",
            color="#e18b24",
            panel_index=1,
        ),
        *_panel(
            rows,
            value_index=7,
            title="Daily average wind speed (m/s)",
            color="#277da1",
            panel_index=2,
        ),
    ]
    if rows:
        panels.append(f'<text x="{LEFT}" y="750" class="tick">{rows[0][0]} to {rows[-1][0]}</text>')
    else:
        panels.append(
            '<text x="90" y="390" class="note">No overlapping UTC dates. Load both sources and run this command again.</text>'
        )
    panels.append(
        '<text x="90" y="775" class="tick">Weather data by Open-Meteo.com (CC BY 4.0). Daily averages are descriptive.</text>'
    )
    return "\n".join([*header, *panels, "</svg>"])


def generate_report(
    database_url: str,
    output_file: Path = OUTPUT_FILE,
    query_file: Path = QUERY_FILE,
    csv_file: Path = OUTPUT_CSV,
) -> int:
    """Query PostgreSQL and write SVG and CSV outputs; return comparison-day count."""
    query = query_file.read_text(encoding="utf-8")
    with psycopg.connect(database_url) as connection:
        rows = connection.execute(query).fetchall()
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(render_svg(rows), encoding="utf-8")
    csv_file.parent.mkdir(parents=True, exist_ok=True)
    with csv_file.open("w", newline="", encoding="utf-8") as report_file:
        writer = csv.writer(report_file)
        writer.writerow(
            (
                "day_utc",
                "area_code",
                "currency",
                "price_unit",
                "average_price",
                "price_intervals",
                "average_temperature_c",
                "average_wind_speed_m_s",
                "temperature_observations",
                "wind_observations",
            )
        )
        writer.writerows(rows)
    return len(rows)


def main() -> int:
    configure_logging()
    load_dotenv()
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        logger.error("DATABASE_URL is missing; set it in .env")
        return 2
    try:
        row_count = generate_report(database_url)
    except (OSError, psycopg.Error) as exc:
        logger.error("report generation failed: %s", exc)
        return 1
    logger.info("wrote %s with %s overlapping UTC days", OUTPUT_FILE, row_count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
