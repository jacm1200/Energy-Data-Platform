"""Parse ENTSO-E day-ahead price Publication_MarketDocument XML."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any


def _local_name(tag: str) -> str:
    """Return an XML element name without its optional namespace."""
    return tag.rsplit("}", 1)[-1]


def _child(element: ET.Element, name: str) -> ET.Element | None:
    for item in element:
        if _local_name(item.tag) == name:
            return item
    return None


def _text(element: ET.Element, name: str, *, required: bool = True) -> str | None:
    item = _child(element, name)
    value = item.text.strip() if item is not None and item.text else None
    if required and value is None:
        raise ValueError(f"ENTSO-E XML is missing '{name}'")
    return value


def _utc_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Invalid ENTSO-E timestamp: {value}") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"ENTSO-E timestamp must include a timezone: {value}")
    return parsed.astimezone(timezone.utc)


def _resolution_minutes(value: str) -> int:
    match = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?", value)
    if not match:
        raise ValueError(f"Unsupported ENTSO-E resolution: {value}")
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    total = hours * 60 + minutes
    if total <= 0:
        raise ValueError(f"ENTSO-E resolution must be positive: {value}")
    return total


def _point_price(point: ET.Element) -> Decimal | None:
    value = _text(point, "price.amount", required=False)
    if value is None:
        # In ENTSO-E publications, an omitted price can mean it was depublished.
        return None
    try:
        price = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid ENTSO-E price: {value}") from exc
    if not price.is_finite():
        raise ValueError(f"Invalid ENTSO-E price: {value}")
    return price


def parse_day_ahead_prices(xml_data: str | bytes) -> list[dict[str, Any]]:
    """Expand ENTSO-E A01/A03 price curves into one row per delivery interval."""
    try:
        root = ET.fromstring(xml_data)
    except ET.ParseError as exc:
        raise ValueError("ENTSO-E response is not valid XML") from exc

    root_name = _local_name(root.tag)
    if root_name == "Acknowledgement_MarketDocument":
        reason = next(
            (node.text.strip() for node in root.iter() if _local_name(node.tag) == "text" and node.text),
            "no price publication was returned",
        )
        raise ValueError(f"ENTSO-E returned an acknowledgement: {reason}")
    if root_name != "Publication_MarketDocument":
        raise ValueError(f"Unexpected ENTSO-E document: {root_name}")
    if _text(root, "type") != "A44":
        raise ValueError("ENTSO-E document is not a day-ahead price publication (A44)")

    rows: list[dict[str, Any]] = []
    seen_intervals: set[tuple[str, datetime]] = set()
    time_series_list = [node for node in root if _local_name(node.tag) == "TimeSeries"]
    if not time_series_list:
        raise ValueError("ENTSO-E publication contains no TimeSeries")

    for time_series in time_series_list:
        area_code = _text(time_series, "in_Domain.mRID")
        currency = _text(time_series, "currency_Unit.name")
        price_unit = _text(time_series, "price_Measure_Unit.name")
        curve_type = _text(time_series, "curveType")
        if curve_type not in {"A01", "A03"}:
            raise ValueError(f"Unsupported ENTSO-E curve type: {curve_type}")

        periods = [node for node in time_series if _local_name(node.tag) == "Period"]
        if not periods:
            raise ValueError("ENTSO-E time series contains no Period")

        for period in periods:
            interval = _child(period, "timeInterval")
            if interval is None:
                raise ValueError("ENTSO-E Period is missing 'timeInterval'")
            start_text = _text(interval, "start")
            end_text = _text(interval, "end")
            start = _utc_datetime(start_text)
            end = _utc_datetime(end_text)
            if end <= start:
                raise ValueError("ENTSO-E period end must be later than start")

            resolution_text = _text(period, "resolution")
            step_minutes = _resolution_minutes(resolution_text)
            interval_seconds = (end - start).total_seconds()
            step_seconds = step_minutes * 60
            if interval_seconds % step_seconds:
                raise ValueError("ENTSO-E period length is not divisible by its resolution")
            interval_count = int(interval_seconds // step_seconds)

            points = [node for node in period if _local_name(node.tag) == "Point"]
            if not points:
                raise ValueError("ENTSO-E Period contains no Point values")

            positioned_points: list[tuple[int, Decimal | None]] = []
            for point in points:
                position_text = _text(point, "position")
                try:
                    position = int(position_text)
                except ValueError as exc:
                    raise ValueError(f"Invalid ENTSO-E point position: {position_text}") from exc
                if position < 1 or position > interval_count:
                    raise ValueError(f"ENTSO-E point position is outside the period: {position}")
                positioned_points.append((position, _point_price(point)))

            positions = [position for position, _ in positioned_points]
            if positions != sorted(set(positions)):
                raise ValueError("ENTSO-E point positions must be unique and increasing")

            if curve_type == "A01":
                if positions != list(range(1, interval_count + 1)):
                    raise ValueError("A01 curve must provide every interval position")
                expanded_points = [
                    (position, position + 1, price)
                    for position, price in positioned_points
                ]
            else:
                if positions[0] != 1:
                    raise ValueError("A03 curve must start at position 1")
                expanded_points = [
                    (
                        position,
                        positioned_points[index + 1][0]
                        if index + 1 < len(positioned_points)
                        else interval_count + 1,
                        price,
                    )
                    for index, (position, price) in enumerate(positioned_points)
                ]

            for first_position, stop_position, price in expanded_points:
                for position in range(first_position, stop_position):
                    delivery_start = start + timedelta(minutes=(position - 1) * step_minutes)
                    key = (area_code, delivery_start)
                    if key in seen_intervals:
                        raise ValueError(f"Duplicate ENTSO-E delivery interval: {delivery_start.isoformat()}")
                    seen_intervals.add(key)
                    rows.append(
                        {
                            "source": "entsoe",
                            "area_code": area_code,
                            "delivery_start": delivery_start,
                            "price_amount": price,
                            "currency": currency,
                            "price_unit": price_unit,
                        }
                    )

    return rows
