"""
Spider for NTHU Library RSS feeds and opening-hours calendars.

Outputs:
    - data/libraries/rss.json: {rss_type: [item, ...]} for every library RSS feed.
    - data/libraries/calendars.json: the library's public Google Calendars with
      recurring events expanded into single occurrences.

If a source fails, the previously saved data for that source is kept, so a
temporary outage (or an IP block on CI runners) never wipes existing data.
"""

import hashlib
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urljoin

import icalendar
import recurring_ical_events
import scrapy
from scrapy.http import Response
from scrapy.selector import Selector

from nthu_scraper.utils.constants import (
    LIBRARIES_CALENDARS_JSON_PATH,
    LIBRARIES_RSS_JSON_PATH,
)
from nthu_scraper.utils.file_utils import load_json, save_json

LIBRARY_BASE_URL = "https://www.lib.nthu.edu.tw/"
RSS_URL_TEMPLATE = "https://www.lib.nthu.edu.tw/bulletin/RSS/export/rss_{}.xml"
RSS_TYPES = ["news", "eresources", "exhibit", "branches"]

# Opening-hours calendars linked from https://www.lib.nthu.edu.tw/use/hours.html
CALENDARS = {
    "main": "dl2sd3i8pt7ds82ann0ckj2d7k@group.calendar.google.com",  # Main Library
    "hss": "nthuhslib@gmail.com",  # Humanities & Social Sciences Library
    "nanda": "nhcue.libr@gmail.com",  # Nanda Campus Library
}
ICAL_URL_TEMPLATE = "https://calendar.google.com/calendar/ical/{}/public/basic.ics"
CALENDAR_EMBED_URL_TEMPLATE = "https://calendar.google.com/calendar/embed?src={}"

# Taiwan has no DST, so a fixed offset is safe and avoids needing tzdata on Windows.
TAIPEI_TZ = timezone(timedelta(hours=8))


def normalize_rss_item_urls(item: Dict[str, Any]) -> None:
    """Resolve relative links in an RSS item against the library website."""
    if item.get("link"):
        item["link"] = urljoin(LIBRARY_BASE_URL, item["link"])

    image = item.get("image")
    if isinstance(image, dict):
        for field in ("url", "link"):
            if image.get(field):
                image[field] = urljoin(LIBRARY_BASE_URL, image[field])


def parse_rss(xml_text: str) -> List[Dict[str, Any]]:
    """
    Parse a library RSS feed into a list of items.

    Field names follow the RSS tags so the output matches what NTHU-Data-API
    previously produced by parsing the feed on every request.
    """
    selector = Selector(text=xml_text, type="xml")
    selector.remove_namespaces()

    def text_of(node: Selector, tag: str) -> Optional[str]:
        value = node.xpath(f"{tag}/text()").get()
        return value.strip() if value and value.strip() else None

    items = []
    for node in selector.xpath("//channel/item"):
        item: Dict[str, Any] = {
            "guid": text_of(node, "guid"),
            "category": text_of(node, "category"),
            "title": text_of(node, "title"),
            "link": text_of(node, "link"),
            "pubDate": text_of(node, "pubDate"),
            "description": (text_of(node, "description") or "").replace("<br />", ""),
            "author": text_of(node, "author"),
            "image": None,
        }

        image_node = node.xpath("image")
        if image_node:
            item["image"] = {
                "url": text_of(image_node[0], "url"),
                "title": text_of(image_node[0], "title"),
                "link": text_of(image_node[0], "link"),
            }

        normalize_rss_item_urls(item)
        items.append(item)
    return items


def _to_iso(value: date | datetime) -> str:
    """Serialize an iCal date or datetime; datetimes are converted to Taipei time."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=TAIPEI_TZ)
        return value.astimezone(TAIPEI_TZ).isoformat()
    return value.isoformat()


def _make_event_id(uid: str, start: str) -> str:
    """Build a stable, URL-safe id; recurring occurrences share a UID, so include start."""
    return hashlib.sha1(f"{uid}|{start}".encode("utf-8")).hexdigest()[:16]


def parse_calendar(
    ics_content: bytes | str, window_start: date, window_end: date
) -> Dict[str, Any]:
    """
    Parse an iCal feed and expand recurring events within [window_start, window_end).

    A window is required because some events recur forever (no UNTIL/COUNT).
    All-day events use date strings; `end` is exclusive, following iCal semantics.
    """
    calendar = icalendar.Calendar.from_ical(ics_content)

    events = []
    for event in recurring_ical_events.of(calendar).between(window_start, window_end):
        dtstart = event.get("DTSTART").dt
        dtend_prop = event.get("DTEND")
        if dtend_prop is not None:
            dtend = dtend_prop.dt
        elif isinstance(dtstart, datetime):
            dtend = dtstart
        else:
            dtend = dtstart + timedelta(days=1)

        start = _to_iso(dtstart)
        events.append(
            {
                "id": _make_event_id(str(event.get("UID", "")), start),
                "title": str(event.get("SUMMARY", "")).strip(),
                "description": str(event.get("DESCRIPTION", "")).strip() or None,
                "start": start,
                "end": _to_iso(dtend),
                "all_day": not isinstance(dtstart, datetime),
            }
        )

    events.sort(key=lambda e: (e["start"], e["title"], e["id"]))
    return {
        "name": str(calendar.get("X-WR-CALNAME", "")).strip() or None,
        "description": str(calendar.get("X-WR-CALDESC", "")).strip() or None,
        "timezone": str(calendar.get("X-WR-TIMEZONE", "")).strip() or None,
        "events": events,
    }


def get_calendar_window(today: date) -> tuple[date, date]:
    """
    Keep last year through next year.

    Year-aligned bounds keep the output stable between runs, so the scheduled
    workflow only commits when the calendar really changes.
    """
    return date(today.year - 1, 1, 1), date(today.year + 2, 1, 1)


class LibrariesSpider(scrapy.Spider):
    """Crawl the NTHU Library RSS feeds and opening-hours calendars."""

    name = "nthu_libraries"
    custom_settings = {
        "ITEM_PIPELINES": {"nthu_scraper.spiders.nthu_libraries.JsonPipeline": 1},
        # calendar.google.com/robots.txt disallows everything, but the public iCal
        # URL is the official subscription feed meant for calendar clients. We fetch
        # three fixed feeds on a schedule, which is the same as a calendar app does.
        "ROBOTSTXT_OBEY": False,
    }

    async def start(self):
        for rss_type in RSS_TYPES:
            yield scrapy.Request(
                RSS_URL_TEMPLATE.format(rss_type),
                callback=self.parse_rss_feed,
                errback=self.handle_error,
                cb_kwargs={"rss_type": rss_type},
            )

        for calendar_id, google_id in CALENDARS.items():
            yield scrapy.Request(
                ICAL_URL_TEMPLATE.format(quote(google_id)),
                callback=self.parse_calendar_feed,
                errback=self.handle_error,
                cb_kwargs={"calendar_id": calendar_id, "google_id": google_id},
            )

    def parse_rss_feed(self, response: Response, rss_type: str):
        items = parse_rss(response.text)
        self.logger.info(f"✅ Parsed {len(items)} items from RSS [{rss_type}]")
        yield {"kind": "rss", "key": rss_type, "data": items}

    def parse_calendar_feed(self, response: Response, calendar_id: str, google_id: str):
        window_start, window_end = get_calendar_window(datetime.now(TAIPEI_TZ).date())
        calendar = parse_calendar(response.body, window_start, window_end)
        self.logger.info(
            f"✅ Parsed {len(calendar['events'])} events from calendar [{calendar_id}]"
        )
        yield {
            "kind": "calendar",
            "key": calendar_id,
            "data": {
                "id": calendar_id,
                "name": calendar["name"],
                "description": calendar["description"],
                "timezone": calendar["timezone"],
                "url": CALENDAR_EMBED_URL_TEMPLATE.format(google_id),
                "events": calendar["events"],
            },
        }

    def handle_error(self, failure):
        self.logger.error(
            f"❌ Request failed: {failure.request.url} ({failure.value!r})"
        )


class JsonPipeline:
    """Merge freshly crawled sources into the existing JSON files."""

    def open_spider(self):
        self.rss: Dict[str, List[Dict[str, Any]]] = {}
        self.calendars: Dict[str, Dict[str, Any]] = {}

    def process_item(self, item):
        if item["kind"] == "rss":
            self.rss[item["key"]] = item["data"]
        elif item["kind"] == "calendar":
            self.calendars[item["key"]] = item["data"]
        return item

    def close_spider(self, spider):
        if self.rss:
            # Start from the previous file so feeds that failed this run are kept.
            rss_data = load_json(LIBRARIES_RSS_JSON_PATH) or {}
            rss_data.update(self.rss)
            rss_data = {key: rss_data[key] for key in RSS_TYPES if key in rss_data}
            self._save(spider, rss_data, LIBRARIES_RSS_JSON_PATH)
        else:
            spider.logger.error("❌ No RSS feed was crawled; keeping existing data")

        if self.calendars:
            previous = load_json(LIBRARIES_CALENDARS_JSON_PATH) or []
            calendars = {calendar["id"]: calendar for calendar in previous}
            calendars.update(self.calendars)
            calendars_data = [calendars[key] for key in CALENDARS if key in calendars]
            self._save(spider, calendars_data, LIBRARIES_CALENDARS_JSON_PATH)
        else:
            spider.logger.error("❌ No calendar was crawled; keeping existing data")

    @staticmethod
    def _save(spider, data, path):
        if save_json(data, path):
            spider.logger.info(f'✅ Saved library data to "{path}"')
        else:
            spider.logger.error(f'❌ Failed to save library data to "{path}"')
