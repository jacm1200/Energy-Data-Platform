"""Load a landed ENTSO-E day-ahead price XML file into local PostgreSQL."""

import argparse
import logging
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

from energy_platform.entsoe import parse_day_ahead_prices
from energy_platform.logging_utils import configure_logging
from energy_platform.storage import upsert_day_ahead_prices

logger = logging.getLogger(__name__)


def load_price_file(raw_file: Path, database_url: str) -> int:
    """Read raw XML, parse delivery intervals, and upsert prices."""
    xml_data = raw_file.read_bytes()
    rows = parse_day_ahead_prices(xml_data)
    return upsert_day_ahead_prices(rows, database_url)


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "raw_file",
        type=Path,
        help="Path to a landed ENTSO-E price XML file",
    )
    args = parser.parse_args(argv)

    load_dotenv()
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        logger.error("DATABASE_URL is missing; set it in .env")
        return 2

    try:
        row_count = load_price_file(args.raw_file, database_url)
    except (OSError, ValueError, psycopg.Error) as exc:
        logger.error("ENTSO-E price load failed: %s", exc)
        return 1

    logger.info("upserted %s day-ahead price rows from %s", row_count, args.raw_file)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
