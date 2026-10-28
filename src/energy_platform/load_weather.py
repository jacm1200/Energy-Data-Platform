"""Load one landed Open-Meteo JSON response into local PostgreSQL."""

import argparse
import json
import logging
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

from energy_platform.storage import upsert_weather_rows
from energy_platform.transform import weather_to_rows
from energy_platform.logging_utils import configure_logging

logger = logging.getLogger(__name__)


def load_weather_file(raw_file: Path, database_url: str) -> int:
    """Read a raw JSON file, normalize it, and upsert its hourly rows."""
    payload = json.loads(raw_file.read_text(encoding="utf-8"))
    rows = weather_to_rows(payload)
    return upsert_weather_rows(rows, database_url)


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw_file", type=Path, help="Path to a landed Open-Meteo JSON file")
    args = parser.parse_args(argv)

    load_dotenv()
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        logger.error("DATABASE_URL is missing; set it in .env")
        return 2

    try:
        row_count = load_weather_file(args.raw_file, database_url)
    except (OSError, ValueError, psycopg.Error) as exc:
        logger.error("weather load failed: %s", exc)
        return 1

    logger.info("upserted %s weather rows from %s", row_count, args.raw_file)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
