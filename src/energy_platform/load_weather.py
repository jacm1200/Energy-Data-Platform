"""Load one landed Open-Meteo JSON response into local PostgreSQL."""

import argparse
import json
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

from energy_platform.storage import upsert_weather_rows
from energy_platform.transform import weather_to_rows


def load_weather_file(raw_file: Path, database_url: str) -> int:
    """Read a raw JSON file, normalize it, and upsert its hourly rows."""
    payload = json.loads(raw_file.read_text(encoding="utf-8"))
    rows = weather_to_rows(payload)
    return upsert_weather_rows(rows, database_url)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw_file", type=Path, help="Path to a landed Open-Meteo JSON file")
    args = parser.parse_args(argv)

    load_dotenv()
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        print("DATABASE_URL is missing; set it in .env", file=sys.stderr)
        return 2

    try:
        row_count = load_weather_file(args.raw_file, database_url)
    except (OSError, json.JSONDecodeError, ValueError, psycopg.Error) as exc:
        print(f"Weather load failed: {exc}", file=sys.stderr)
        return 1

    print(f"Upserted {row_count} weather rows from {args.raw_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
