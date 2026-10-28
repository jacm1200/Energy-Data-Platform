from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from energy_platform.entsoe import parse_day_ahead_prices
from energy_platform import load_entsoe_prices


FIXTURE = Path(__file__).parent / "fixtures" / "entsoe_a44_a03_sample.xml"


def test_parse_a03_expands_price_blocks_to_delivery_intervals():
    rows = parse_day_ahead_prices(FIXTURE.read_bytes())

    assert [row["price_amount"] for row in rows] == [
        Decimal("45.25"),
        Decimal("45.25"),
        Decimal("-5.00"),
        Decimal("-5.00"),
    ]
    assert [row["delivery_start"] for row in rows] == [
        datetime(2026, 1, 1, hour, tzinfo=timezone.utc)
        for hour in range(4)
    ]
    assert rows[0]["area_code"] == "10YES-REE------0"
    assert rows[0]["currency"] == "EUR"
    assert rows[0]["price_unit"] == "MWH"


def test_parse_acknowledgement_instead_of_prices():
    xml = b"""<Acknowledgement_MarketDocument>
        <Reason><code>999</code><text>No matching data found</text></Reason>
    </Acknowledgement_MarketDocument>"""

    with pytest.raises(ValueError, match="No matching data found"):
        parse_day_ahead_prices(xml)


def test_parse_rejects_non_price_publication():
    xml = b"<Publication_MarketDocument><type>A25</type></Publication_MarketDocument>"

    with pytest.raises(ValueError, match="not a day-ahead price"):
        parse_day_ahead_prices(xml)


def test_parse_rejects_invalid_xml():
    with pytest.raises(ValueError, match="not valid XML"):
        parse_day_ahead_prices(b"<broken")


def test_parse_a01_keeps_each_fixed_interval():
    xml = b"""<Publication_MarketDocument xmlns="urn:test">
      <type>A44</type>
      <TimeSeries>
        <in_Domain.mRID>10YES-REE------0</in_Domain.mRID>
        <currency_Unit.name>EUR</currency_Unit.name>
        <price_Measure_Unit.name>MWH</price_Measure_Unit.name>
        <curveType>A01</curveType>
        <Period>
          <timeInterval><start>2026-01-01T00:00Z</start><end>2026-01-01T02:00Z</end></timeInterval>
          <resolution>PT60M</resolution>
          <Point><position>1</position><price.amount>10</price.amount></Point>
          <Point><position>2</position><price.amount>20</price.amount></Point>
        </Period>
      </TimeSeries>
    </Publication_MarketDocument>"""

    rows = parse_day_ahead_prices(xml)

    assert [row["price_amount"] for row in rows] == [Decimal("10"), Decimal("20")]


def test_load_price_file_parses_xml_and_sends_rows_to_storage(tmp_path, monkeypatch):
    raw_file = tmp_path / "prices.xml"
    raw_file.write_bytes(FIXTURE.read_bytes())
    captured = {}

    def fake_upsert(rows, database_url):
        captured["rows"] = rows
        captured["database_url"] = database_url
        return len(rows)

    monkeypatch.setattr(
        load_entsoe_prices,
        "upsert_day_ahead_prices",
        fake_upsert,
    )

    count = load_entsoe_prices.load_price_file(raw_file, "postgresql://test")

    assert count == 4
    assert captured["database_url"] == "postgresql://test"
    assert len(captured["rows"]) == 4
