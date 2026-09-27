"""Offline tests for the NTHU Library spider parsers and pipeline."""

import json
from datetime import date

import pytest

from nthu_scraper.spiders import nthu_libraries
from nthu_scraper.spiders.nthu_libraries import (
    CALENDARS,
    LibrariesPipeline,
    _make_event_id,
    get_calendar_window,
    parse_calendar,
    parse_rss,
)

RSS_XML = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
<channel>
<title>國立清華大學圖書館</title>
<item>
<guid>2024</guid>
<category>展覽與活動</category>
<title>【活動快訊】週三響時光</title>
<link></link>
<pubDate>Tue, 22 Sep 2026 14:38:27 +0800</pubDate>
<description><![CDATA[第一行<br />
第二行]]></description>
<author>ref@my.nthu.edu.tw (NTHU Library 服務推廣組)</author>
<image><url>//www.lib.nthu.edu.tw/image/news/2/music.jpg</url>
<title>【活動快訊】週三響時光</title>
<link>/</link>
</image>
</item>
<item>
<guid>2025</guid>
<category>最新消息</category>
<title>招募</title>
<link>recruit</link>
<pubDate>Wed, 23 Sep 2026 09:00:00 +0800</pubDate>
<description><![CDATA[內容]]></description>
<author>lib@lib.nthu.edu.tw</author>
</item>
</channel>
</rss>
"""

ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
X-WR-CALNAME:總圖書館開館行事曆
X-WR-TIMEZONE:Asia/Taipei
X-WR-CALDESC:測試日曆
BEGIN:VEVENT
UID:single@test
DTSTART;VALUE=DATE:20260925
DTEND;VALUE=DATE:20260926
SUMMARY:中秋節閉館 Closed
DESCRIPTION:星期五
END:VEVENT
BEGIN:VEVENT
UID:weekly@test
DTSTART;VALUE=DATE:20260906
DTEND;VALUE=DATE:20260907
RRULE:FREQ=WEEKLY;BYDAY=SU
SUMMARY:總圖 10:00-18:00
END:VEVENT
BEGIN:VEVENT
UID:timed@test
DTSTART;TZID=Asia/Taipei:20260928T080000
DTEND;TZID=Asia/Taipei:20260928T220000
SUMMARY:總圖 08:00-22:00
END:VEVENT
BEGIN:VEVENT
UID:old@test
DTSTART;VALUE=DATE:20200101
DTEND;VALUE=DATE:20200102
SUMMARY:Out of window
END:VEVENT
END:VCALENDAR
"""


@pytest.mark.parametrize(
    "start,expected",
    [
        ("2026-09-25", "36c05c1cf357ffe2"),
        ("2026-09-28T22:00:00+08:00", "ad548bfa249d7b68"),
    ],
)
def test_public_event_id_contract(start, expected):
    assert _make_event_id("event@example.test", start) == expected


class TestParseRss:
    def test_parses_all_items(self):
        items = parse_rss(RSS_XML)
        assert [item["guid"] for item in items] == ["2024", "2025"]

    def test_normalizes_urls_and_description(self):
        first, second = parse_rss(RSS_XML)
        assert first["link"] is None
        assert first["description"] == "第一行\n第二行"
        assert (
            first["image"]["url"]
            == "https://www.lib.nthu.edu.tw/image/news/2/music.jpg"
        )
        assert first["image"]["link"] == "https://www.lib.nthu.edu.tw/"
        assert second["link"] == "https://www.lib.nthu.edu.tw/recruit"
        assert second["image"] is None


class TestParseCalendar:
    @pytest.fixture
    def calendar(self):
        return parse_calendar(ICS, date(2026, 9, 1), date(2026, 10, 1))

    def test_metadata(self, calendar):
        assert calendar["name"] == "總圖書館開館行事曆"
        assert calendar["description"] == "測試日曆"
        assert calendar["timezone"] == "Asia/Taipei"

    def test_expands_recurring_events_within_window(self, calendar):
        sundays = [
            e["start"] for e in calendar["events"] if e["title"] == "總圖 10:00-18:00"
        ]
        assert sundays == ["2026-09-06", "2026-09-13", "2026-09-20", "2026-09-27"]

    def test_excludes_events_outside_window(self, calendar):
        assert all(e["title"] != "Out of window" for e in calendar["events"])

    def test_all_day_event(self, calendar):
        event = next(e for e in calendar["events"] if e["start"] == "2026-09-25")
        assert event["all_day"] is True
        assert event["end"] == "2026-09-26"
        assert event["description"] == "星期五"

    def test_timed_event_uses_taipei_offset(self, calendar):
        event = next(e for e in calendar["events"] if not e["all_day"])
        assert event["start"] == "2026-09-28T08:00:00+08:00"
        assert event["end"] == "2026-09-28T22:00:00+08:00"

    def test_ids_are_unique_and_stable(self, calendar):
        ids = [e["id"] for e in calendar["events"]]
        assert len(ids) == len(set(ids))
        again = parse_calendar(ICS, date(2026, 9, 1), date(2026, 10, 1))
        assert ids == [e["id"] for e in again["events"]]

    def test_events_are_sorted(self, calendar):
        starts = [e["start"] for e in calendar["events"]]
        assert starts == sorted(starts)


def test_calendar_window_is_year_aligned():
    assert get_calendar_window(date(2026, 9, 25)) == (
        date(2025, 1, 1),
        date(2028, 1, 1),
    )


class TestLibrariesPipeline:
    @pytest.fixture
    def paths(self, tmp_path, monkeypatch):
        rss_path = tmp_path / "rss.json"
        calendars_path = tmp_path / "calendars.json"
        monkeypatch.setattr(nthu_libraries, "LIBRARIES_RSS_JSON_PATH", rss_path)
        monkeypatch.setattr(
            nthu_libraries, "LIBRARIES_CALENDARS_JSON_PATH", calendars_path
        )
        return rss_path, calendars_path

    @staticmethod
    def _run(items):
        class FakeSpider:
            class logger:
                info = warning = error = staticmethod(lambda *args, **kwargs: None)

        pipeline = LibrariesPipeline()
        pipeline.open_spider(FakeSpider)
        for item in items:
            pipeline.process_item(item, FakeSpider)
        pipeline.close_spider(FakeSpider)

    def test_keeps_previous_data_for_failed_sources(self, paths):
        rss_path, calendars_path = paths
        rss_path.write_text(
            json.dumps({"news": ["old"], "exhibit": ["old"]}), encoding="utf-8"
        )
        calendars_path.write_text(
            json.dumps(
                [{"id": "main", "events": ["old"]}, {"id": "hss", "events": ["old"]}]
            ),
            encoding="utf-8",
        )

        self._run(
            [
                {"kind": "rss", "key": "news", "data": ["new"]},
                {
                    "kind": "calendar",
                    "key": "hss",
                    "data": {"id": "hss", "events": ["new"]},
                },
            ]
        )

        assert json.loads(rss_path.read_text(encoding="utf-8")) == {
            "news": ["new"],
            "exhibit": ["old"],
        }
        assert json.loads(calendars_path.read_text(encoding="utf-8")) == [
            {"id": "main", "events": ["old"]},
            {"id": "hss", "events": ["new"]},
        ]

    def test_does_not_write_when_everything_failed(self, paths):
        rss_path, calendars_path = paths
        self._run([])
        assert not rss_path.exists()
        assert not calendars_path.exists()

    def test_calendars_follow_configured_order(self, paths):
        _, calendars_path = paths
        self._run(
            [
                {"kind": "calendar", "key": key, "data": {"id": key, "events": []}}
                for key in reversed(list(CALENDARS))
            ]
        )
        saved = json.loads(calendars_path.read_text(encoding="utf-8"))
        assert [c["id"] for c in saved] == list(CALENDARS)

    def test_empty_refresh_preserves_nonempty_sources(self, paths):
        rss_path, calendars_path = paths
        rss_path.write_text(json.dumps({"news": ["old"]}), encoding="utf-8")
        calendars_path.write_text(
            json.dumps([{"id": "main", "events": ["old"]}]), encoding="utf-8"
        )
        self._run(
            [
                {"kind": "rss", "key": "news", "data": []},
                {
                    "kind": "calendar",
                    "key": "main",
                    "data": {"id": "main", "events": []},
                },
            ]
        )
        assert json.loads(rss_path.read_text(encoding="utf-8")) == {"news": ["old"]}
        assert json.loads(calendars_path.read_text(encoding="utf-8")) == [
            {"id": "main", "events": ["old"]}
        ]


@pytest.mark.parametrize("error_type", [AttributeError, ValueError])
def test_library_implementation_error_is_not_treated_as_upstream_failure(
    monkeypatch, error_type
):
    def broken_parser(text):
        raise error_type("implementation regression")

    monkeypatch.setattr(nthu_libraries, "parse_rss", broken_parser)
    from scrapy.http import TextResponse

    response = TextResponse("https://example.test", body=b"test", encoding="utf-8")
    spider = nthu_libraries.LibrariesSpider()
    items = spider.parse_rss_feed(response, "news")
    with pytest.raises(error_type):
        list(items)


def test_library_errback_does_not_swallow_implementation_errors():
    from twisted.python.failure import Failure

    spider = nthu_libraries.LibrariesSpider()
    failure = Failure(AttributeError("regression"))
    with pytest.raises(AttributeError):
        spider.handle_error(failure)


@pytest.mark.parametrize(
    "xml",
    [
        "",
        "<html>Unavailable</html>",
        "<rss><channel>",
        "<rss><channel><item><link>/no-title</link></item></channel></rss>",
    ],
)
def test_invalid_rss_is_not_an_empty_feed(xml):
    with pytest.raises(nthu_libraries.InvalidLibrarySource):
        parse_rss(xml)


def test_valid_empty_rss_and_optional_fields():
    assert parse_rss("<rss><channel></channel></rss>") == []
    assert parse_rss(
        "<rss><channel><item><title>Only title</title></item></channel></rss>"
    ) == [
        {
            "guid": None,
            "category": None,
            "title": "Only title",
            "link": None,
            "pubDate": None,
            "description": "",
            "author": None,
            "image": None,
        }
    ]


@pytest.mark.parametrize(
    "ics",
    [
        "",
        "not a calendar",
        "BEGIN:VCALENDAR\nVERSION:2.0\n",
        "BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:missing-start\nEND:VEVENT\nEND:VCALENDAR",
        "BEGIN:VCALENDAR\nBEGIN:VEVENT\nDTSTART:invalid\nEND:VEVENT\nEND:VCALENDAR",
    ],
)
def test_invalid_calendar_is_not_an_empty_calendar(ics):
    with pytest.raises(nthu_libraries.InvalidLibrarySource):
        parse_calendar(ics, date(2026, 1, 1), date(2027, 1, 1))


def test_empty_calendar():
    assert parse_calendar(
        b"BEGIN:VCALENDAR\nVERSION:2.0\nEND:VCALENDAR",
        date(2026, 1, 1),
        date(2027, 1, 1),
    ) == {"name": None, "description": None, "timezone": None, "events": []}


def test_calendar_missing_end_uses_existing_defaults():
    calendar = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:all-day
DTSTART;VALUE=DATE:20260901
SUMMARY:All day
END:VEVENT
BEGIN:VEVENT
UID:utc
DTSTART:20260902T010000Z
SUMMARY:UTC
END:VEVENT
END:VCALENDAR"""
    events = parse_calendar(calendar, date(2026, 9, 1), date(2026, 9, 3))["events"]
    assert events[0]["end"] == "2026-09-02"
    assert events[1]["start"] == events[1]["end"] == "2026-09-02T09:00:00+08:00"
