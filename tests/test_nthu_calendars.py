"""Offline coverage for campus calendar requests, parsing, and retention."""

import asyncio
import json
from datetime import date

import pytest
from scrapy import Request
from scrapy.http import Response
from twisted.internet.error import DNSLookupError
from twisted.python.failure import Failure

from nthu_scraper.spiders import nthu_calendars

ICS = b"""BEGIN:VCALENDAR
VERSION:2.0
X-WR-CALNAME:NTHU Academic Calendar
X-WR-TIMEZONE:Asia/Taipei
BEGIN:VEVENT
UID:semester@test
DTSTART;VALUE=DATE:20260901
DTEND;VALUE=DATE:20260902
SUMMARY:Semester begins
END:VEVENT
BEGIN:VEVENT
UID:weekly@test
DTSTART;TZID=Asia/Taipei:20260901T100000
DTEND;TZID=Asia/Taipei:20260901T110000
RRULE:FREQ=WEEKLY;COUNT=2
SUMMARY:Meeting
END:VEVENT
END:VCALENDAR
"""


@pytest.fixture
def spider():
    return nthu_calendars.CalendarsSpider()


@pytest.fixture
def calendar(spider, monkeypatch):
    monkeypatch.setattr(
        nthu_calendars,
        "get_calendar_window",
        lambda today: (date(2026, 1, 1), date(2027, 1, 1)),
    )
    return next(spider.parse_calendar_feed(Response(nthu_calendars.ICAL_URL, body=ICS)))


def test_requests_official_public_feed(spider):
    async def requests():
        return [request async for request in spider.start()]

    (request,) = asyncio.run(requests())
    assert request.url == (
        "https://calendar.google.com/calendar/ical/"
        "nthu.acad%40gmail.com/public/basic.ics"
    )
    assert request.callback == spider.parse_calendar_feed
    assert request.errback == spider.handle_error
    assert spider.custom_settings["ROBOTSTXT_OBEY"] is False


def test_calendar_output_contract(calendar):
    assert calendar == {
        "id": "academic",
        "name": "NTHU Academic Calendar",
        "description": None,
        "timezone": "Asia/Taipei",
        "url": "https://calendar.google.com/calendar/embed?src=nthu.acad@gmail.com",
        "source_url": nthu_calendars.SOURCE_URL,
        "ical_url": nthu_calendars.ICAL_URL,
        "events": calendar["events"],
    }
    events = calendar["events"]
    assert len(events) == 3
    assert events[0] == {
        "id": events[0]["id"],
        "title": "Semester begins",
        "description": None,
        "start": "2026-09-01",
        "end": "2026-09-02",
        "all_day": True,
    }
    assert len({event["id"] for event in events}) == 3
    assert [event["start"] for event in events[1:]] == [
        "2026-09-01T10:00:00+08:00",
        "2026-09-08T10:00:00+08:00",
    ]
    assert all(not event["all_day"] for event in events[1:])


def test_invalid_feed_is_logged_and_not_emitted(spider, caplog):
    assert (
        list(spider.parse_calendar_feed(Response("https://example.test", body=b"bad")))
        == []
    )
    assert "retaining previous data" in caplog.text


def test_parser_regression_propagates(spider, monkeypatch):
    def broken_parser(*args):
        raise ValueError("regression")

    monkeypatch.setattr(nthu_calendars, "parse_calendar", broken_parser)
    with pytest.raises(ValueError, match="regression"):
        list(spider.parse_calendar_feed(Response(nthu_calendars.ICAL_URL, body=ICS)))


def test_errback_only_handles_expected_failures(spider):
    failure = Failure(DNSLookupError("offline"))
    failure.request = Request(nthu_calendars.ICAL_URL)
    spider.handle_error(failure)
    with pytest.raises(AttributeError, match="regression"):
        spider.handle_error(Failure(AttributeError("regression")))


@pytest.fixture
def path(tmp_path, monkeypatch):
    path = tmp_path / "calendars.json"
    monkeypatch.setattr(nthu_calendars, "CALENDARS_JSON_PATH", path)
    return path


def run_pipeline(spider, items):
    pipeline = nthu_calendars.CalendarsPipeline()
    pipeline.open_spider(spider)
    for item in items:
        assert pipeline.process_item(item, spider) is item
    pipeline.close_spider(spider)


def test_saves_root_calendar_and_preserves_other_sources(spider, calendar, path):
    other = {"id": "other", "events": [{"title": "Keep"}]}
    path.write_text(json.dumps([other]), encoding="utf-8")
    run_pipeline(spider, [calendar])
    assert json.loads(path.read_text(encoding="utf-8")) == [calendar, other]
    assert not (path.parent / "libraries").exists()
    before = path.read_bytes()
    run_pipeline(spider, [calendar])
    assert path.read_bytes() == before


@pytest.mark.parametrize("empty", [False, True])
@pytest.mark.parametrize("baseline", [False, True])
def test_failed_or_empty_refresh_never_replaces_data(spider, path, empty, baseline):
    original = b'[{"id": "academic", "events": [{"title": "Old"}]}]'
    if baseline:
        path.write_bytes(original)
    run_pipeline(spider, [{"id": "academic", "events": []}] if empty else [])
    if baseline:
        assert path.read_bytes() == original
    else:
        assert not path.exists()


@pytest.mark.parametrize("baseline", [b"{invalid", b"{}", b"[{}]"])
def test_invalid_baseline_propagates(spider, path, baseline):
    path.write_bytes(baseline)
    with pytest.raises(ValueError):
        run_pipeline(spider, [])
    assert path.read_bytes() == baseline


def test_storage_failure_propagates(spider, calendar, path, monkeypatch):
    def fail_save(*args):
        raise OSError("disk full")

    monkeypatch.setattr(nthu_calendars, "save_json", fail_save)
    with pytest.raises(OSError, match="disk full"):
        run_pipeline(spider, [calendar])
