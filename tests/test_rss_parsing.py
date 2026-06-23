"""Tests that exercise the real RSS/Atom parsing and date-normalization code.

The rest of the suite monkeypatches the parser away, so these tests cover the
otherwise-unexercised parsing paths in app/ingestion/rss_base.py against raw
bytes: valid RSS 2.0, valid Atom, malformed XML, empty feeds, and namespaced
elements, plus the timezone normalization in parse_datetime.
"""

from __future__ import annotations

import pytest

from app.ingestion.rss_base import (
    IngestionError,
    parse_datetime,
    parse_rss_payload,
    parse_rss_payload_stdlib,
)

RSS_2_0 = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Example Feed</title>
    <item>
      <title>First item</title>
      <link>https://example.org/a</link>
      <guid>https://example.org/a</guid>
      <pubDate>Tue, 10 Jun 2025 09:00:00 GMT</pubDate>
      <description>Alpha summary</description>
    </item>
    <item>
      <title>Second item</title>
      <link>https://example.org/b</link>
      <description>Beta summary</description>
    </item>
  </channel>
</rss>
"""

ATOM = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Atom Example</title>
  <entry>
    <title>Atom entry</title>
    <link href="https://example.org/atom-1" rel="alternate"/>
    <id>urn:uuid:atom-1</id>
    <published>2025-06-10T09:00:00Z</published>
    <summary>Atom summary</summary>
  </entry>
</feed>
"""

# Dublin Core namespaced element inside an RSS item.
NAMESPACED = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/">
  <channel>
    <item>
      <title>Namespaced item</title>
      <link>https://example.org/ns</link>
      <dc:date>2025-06-10T09:00:00Z</dc:date>
      <description>Namespaced summary</description>
    </item>
  </channel>
</rss>
"""

EMPTY_FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Nothing here</title></channel></rss>
"""

MALFORMED = b"<rss><channel><item><title>unclosed"


def test_stdlib_parses_rss_2_0():
    entries = parse_rss_payload_stdlib(RSS_2_0, "example")
    assert len(entries) == 2
    assert entries[0]["title"] == "First item"
    assert entries[0]["link"] == "https://example.org/a"
    assert entries[0]["summary"] == "Alpha summary"
    # Item without an explicit guid still parses.
    assert entries[1]["title"] == "Second item"


def test_stdlib_parses_atom():
    entries = parse_rss_payload_stdlib(ATOM, "example")
    assert len(entries) == 1
    assert entries[0]["title"] == "Atom entry"
    # The href of the <link> element is preferred over the id.
    assert entries[0]["link"] == "https://example.org/atom-1"
    assert entries[0]["summary"] == "Atom summary"


def test_stdlib_namespace_tolerant_link_and_summary():
    entries = parse_rss_payload_stdlib(NAMESPACED, "example")
    assert len(entries) == 1
    assert entries[0]["title"] == "Namespaced item"
    assert entries[0]["link"] == "https://example.org/ns"


def test_stdlib_empty_feed_returns_no_entries():
    assert parse_rss_payload_stdlib(EMPTY_FEED, "example") == []


def test_stdlib_malformed_xml_raises():
    with pytest.raises(IngestionError):
        parse_rss_payload_stdlib(MALFORMED, "example")


def test_parse_rss_payload_dispatches_and_parses():
    # In environments without feedparser this exercises the stdlib fallback;
    # either way valid bytes must yield entries.
    entries = parse_rss_payload(RSS_2_0, "example")
    assert [entry["title"] for entry in entries] == ["First item", "Second item"]


def test_parse_rss_payload_malformed_raises():
    with pytest.raises(IngestionError):
        parse_rss_payload(MALFORMED, "example")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Tue, 10 Jun 2025 09:00:00 GMT", "2025-06-10T09:00:00Z"),
        ("2025-06-10T09:00:00+00:00", "2025-06-10T09:00:00Z"),
        # Non-UTC offset is normalized to UTC.
        ("2025-06-10T11:00:00+02:00", "2025-06-10T09:00:00Z"),
        # Naive datetime is treated as UTC.
        ("2025-06-10 09:00:00", "2025-06-10T09:00:00Z"),
        # Microseconds are dropped.
        ("2025-06-10T09:00:00.500000Z", "2025-06-10T09:00:00Z"),
    ],
)
def test_parse_datetime_normalizes_to_utc_z(value, expected):
    assert parse_datetime(value) == expected


@pytest.mark.parametrize("value", [None, "", "not a date", 12345, "2025-13-99"])
def test_parse_datetime_invalid_returns_none(value):
    assert parse_datetime(value) is None
