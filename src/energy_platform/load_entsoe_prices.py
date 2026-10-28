"""Load a landed ENTSO-E day-ahead price XML file into local PostgreSQL."""

import argparse
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

from energy_platform.entsoe import parse_day_ahead_prices
from energy_platform.storage import upsert_day_ahead_prices


def load_price_file(raw_file: Path, database_url: str) -> int:
    """Read raw XML, parse delivery intervals, and upsert prices."""
    xml_data = raw_file.read_bytes()
    rows = parse_day_ahead_prices(xml_data)
    return upsert_day_ahead_prices(rows, database_url)


def main(argv: list[str] | None = None) -> int:
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
        print("DATABASE_URL is missing; set it in .env", file=sys.stderr)
        return 2

    try:
        row_count = load_price_file(args.raw_file, database_url)
    except (OSError, ValueError, psycopg.Error) as exc:
        print(f"ENTSO-E price load failed: {exc}", file=sys.stderr)
        return 1

    print(f"Upserted {row_count} day-ahead price rows from {args.raw_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
