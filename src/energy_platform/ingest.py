"""Download source responses and land immutable raw files for later processing."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ENTSOE_URL = "https://web-api.tp.entsoe.eu/api"
WEATHER_URL = "https://archive-api.open-meteo.com/v1/archive"
ES_BIDDING_ZONE = "10YES-REE------0"


def fetch_bytes(url: str, timeout: int = 30) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "energy-data-platform/0.1"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"Source returned HTTP {response.status}")
        return response.read()


def landing_path(raw_dir: Path, source: str, start: date, end: date, suffix: str) -> Path:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    return raw_dir / source / f"{start.isoformat()}_{end.isoformat()}" / f"{run_id}.{suffix}"


def land_response(raw_dir: Path, source: str, start: date, end: date, suffix: str, body: bytes) -> Path:
    destination = landing_path(raw_dir, source, start, end, suffix)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(body)
    return destination


def weather_url(start: date, end: date, latitude: float, longitude: float, timezone_name: str) -> str:
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": start.isoformat(),
        # Open-Meteo's end_date is inclusive; the CLI uses an exclusive end.
        "end_date": (end - timedelta(days=1)).isoformat(),
        "hourly": "temperature_2m,precipitation",
        "timezone": timezone_name,
    }
    return WEATHER_URL + "?" + urllib.parse.urlencode(params)


def entsoe_url(start: date, end: date, token: str) -> str:
    # ENTSO-E timestamps are UTC; the end is exclusive and represented at midnight.
    params = {
        "securityToken": token,
        "documentType": "A44",
        "in_Domain": ES_BIDDING_ZONE,
        "out_Domain": ES_BIDDING_ZONE,
        "periodStart": start.strftime("%Y%m%d") + "0000",
        "periodEnd": end.strftime("%Y%m%d") + "0000",
    }
    return ENTSOE_URL + "?" + urllib.parse.urlencode(params)


def ingest_weather(raw_dir: Path, start: date, end: date) -> Path:
    latitude = float(os.getenv("WEATHER_LATITUDE", "40.4168"))
    longitude = float(os.getenv("WEATHER_LONGITUDE", "-3.7038"))
    timezone_name = os.getenv("WEATHER_TIMEZONE", "Europe/Madrid")
    body = fetch_bytes(weather_url(start, end, latitude, longitude, timezone_name))
    # Refuse to land an API error payload as if it were a successful dataset.
    payload = json.loads(body)
    if "hourly" not in payload or "hourly_units" not in payload:
        raise ValueError("Open-Meteo response does not contain expected hourly data")
    return land_response(raw_dir, "open_meteo", start, end, "json", body)


def ingest_entsoe(raw_dir: Path, start: date, end: date) -> Path:
    token = os.getenv("ENTSOE_API_TOKEN", "").strip()
    if not token:
        raise ValueError("ENTSOE_API_TOKEN is missing; request a token from ENTSO-E first")
    body = fetch_bytes(entsoe_url(start, end, token))
    if b"Acknowledgement_MarketDocument" in body:
        raise ValueError("ENTSO-E returned an acknowledgement instead of price data")
    if b"Publication_MarketDocument" not in body:
        raise ValueError("ENTSO-E response is not a Publication_MarketDocument")
    return land_response(raw_dir, "entsoe", start, end, "xml", body)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=("weather", "electricity", "all"), default="weather")
    parser.add_argument("--start", type=date.fromisoformat, required=True, help="Start day, YYYY-MM-DD")
    parser.add_argument("--end", type=date.fromisoformat, required=True, help="End day, YYYY-MM-DD (exclusive)")
    parser.add_argument("--raw-dir", type=Path, default=Path(os.getenv("RAW_DATA_DIR", "data/raw")))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.end <= args.start:
        print("--end must be later than --start", file=sys.stderr)
        return 2
    jobs = []
    if args.source in ("weather", "all"):
        jobs.append(("weather", ingest_weather))
    if args.source in ("electricity", "all"):
        jobs.append(("electricity", ingest_entsoe))
    failures = 0
    for label, job in jobs:
        try:
            path = job(args.raw_dir, args.start, args.end)
            print(f"{label}: landed raw response at {path}")
        except (urllib.error.URLError, TimeoutError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
            failures += 1
            print(f"{label}: ingestion failed: {exc}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
