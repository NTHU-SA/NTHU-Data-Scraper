"""Offline tests for the NTHU Library spider parsers and pipeline."""

import json
from datetime import date

import pytest

from nthu_scraper.spiders import nthu_libraries
from nthu_scraper.spiders.nthu_libraries import (
    CALENDARS,
    JsonPipeline,
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


class TestJsonPipeline:
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
                info = error = staticmethod(lambda *args, **kwargs: None)

        pipeline = JsonPipeline()
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
