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
import logging
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

import icalendar
import recurring_ical_events
import scrapy
from lxml import etree
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError
from scrapy.http import Response
from scrapy.selector import Selector

from nthu_scraper.utils.constants import (
    LIBRARIES_CALENDARS_JSON_PATH,
    LIBRARIES_RSS_JSON_PATH,
)
from nthu_scraper.utils.crawl_safety import log_source_failure
from nthu_scraper.utils.file_utils import load_json, save_json
from nthu_scraper.utils.url_utils import (
    normalize_http_url,
    normalize_optional_http_url,
)

logger = logging.getLogger(__name__)
LIBRARY_BASE_URL = normalize_http_url("https://www.lib.nthu.edu.tw/")
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


class InvalidLibrarySource(ValueError):
    """An upstream document cannot be safely parsed as a complete source."""


class LibraryRssImage(BaseModel):
    model_config = ConfigDict(extra="allow")

    url: str | None = None
    title: str | None = None
    link: str | None = None


class LibraryRssItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    guid: str | None = None
    category: str | None = None
    title: str = Field(min_length=1)
    link: str | None = None
    pubDate: str | None = None
    description: str
    author: str | None = None
    image: LibraryRssImage | None = None


_RSS_ITEMS_ADAPTER = TypeAdapter(list[LibraryRssItem])


def normalize_rss_item_urls(
    item: dict[str, Any], *, source: str = LIBRARY_BASE_URL
) -> None:
    """Normalize image URLs, leaving the article's link text untouched."""
    image = item.get("image")
    if image is None:
        return
    if not isinstance(image, dict):
        raise InvalidLibrarySource("RSS image must be an object or null")
    context = (
        f"library RSS image (source={source} guid={item.get('guid')!r} "
        f"title={item.get('title')!r})"
    )
    url = normalize_optional_http_url(
        image.get("url"),
        base_url=LIBRARY_BASE_URL,
        logger=logger,
        context=context,
    )
    if url is None:
        item["image"] = None
        return
    image["url"] = url
    image["link"] = normalize_optional_http_url(
        image.get("link"),
        base_url=LIBRARY_BASE_URL,
        logger=logger,
        context=f"{context} link",
    )


def normalize_rss_items(
    data: object, *, source: str = LIBRARY_BASE_URL
) -> list[dict[str, Any]]:
    """Validate a whole feed without dropping articles or publisher metadata."""
    if not isinstance(data, list):
        raise InvalidLibrarySource("RSS feed must be an array")
    items = deepcopy(data)
    for item in items:
        if not isinstance(item, dict):
            raise InvalidLibrarySource("RSS article must be an object")
        if isinstance(item.get("link"), str) and not item["link"].strip():
            item["link"] = None
        normalize_rss_item_urls(item, source=source)
    try:
        parsed = _RSS_ITEMS_ADAPTER.validate_python(items, strict=True)
    except ValidationError as error:
        raise InvalidLibrarySource(str(error)) from error
    return [item.model_dump(mode="json") for item in parsed]


def parse_rss(xml_text: str) -> list[dict[str, Any]]:
    """
    Parse a library RSS feed into a list of items.

    Field names follow the RSS tags so the output matches what NTHU-Data-API
    previously produced by parsing the feed on every request.
    """
    try:
        etree.fromstring(
            xml_text.encode("utf-8"),
            parser=etree.XMLParser(resolve_entities=False, no_network=True),
        )
    except etree.XMLSyntaxError as error:
        raise InvalidLibrarySource(str(error)) from error
    selector = Selector(text=xml_text, type="xml")
    selector.remove_namespaces()

    def text_of(node: Selector, tag: str, *, strip: bool = True) -> str | None:
        value = node.xpath(f"{tag}/text()").get()
        if not value or not value.strip():
            return None
        return value.strip() if strip else value

    channels = selector.xpath("/rss/channel")
    if len(channels) != 1:
        raise InvalidLibrarySource("RSS response must contain exactly one RSS channel")

    items = []
    for node in channels[0].xpath("item"):
        item: dict[str, Any] = {
            "guid": text_of(node, "guid"),
            "category": text_of(node, "category"),
            "title": text_of(node, "title"),
            "link": text_of(node, "link", strip=False),
            "pubDate": text_of(node, "pubDate"),
            "description": (text_of(node, "description") or "").replace("<br />", ""),
            "author": text_of(node, "author"),
            "image": None,
        }

        if not item["title"]:
            raise InvalidLibrarySource("RSS contains an item without a title")

        image_node = node.xpath("image")
        if image_node:
            item["image"] = {
                "url": text_of(image_node[0], "url"),
                "title": text_of(image_node[0], "title"),
                "link": text_of(image_node[0], "link"),
            }

        items.append(item)
    return normalize_rss_items(items)


def _to_iso(value: date | datetime) -> str:
    """Serialize an iCal date or datetime; datetimes are converted to Taipei time."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=TAIPEI_TZ)
        return value.astimezone(TAIPEI_TZ).isoformat()
    return value.isoformat()


def _make_event_id(uid: str, start: str) -> str:
    """Build a stable, URL-safe id; recurring occurrences share a UID, so include start."""
    # Public event identifiers, not authentication or integrity checks.
    return hashlib.sha1(f"{uid}|{start}".encode(), usedforsecurity=False).hexdigest()[
        :16
    ]


def _validate_calendar(calendar: icalendar.Calendar) -> None:
    if calendar.name != "VCALENDAR":
        raise InvalidLibrarySource("Expected a VCALENDAR document")
    for component in calendar.walk():
        if component.errors:
            raise InvalidLibrarySource(
                f"Invalid calendar properties: {component.errors}"
            )
        if component.name == "VEVENT":
            _validate_event(component)


def _validate_event(event: icalendar.Event) -> None:
    start = getattr(event.get("DTSTART"), "dt", None)
    if not isinstance(start, (date, datetime)):
        raise InvalidLibrarySource("Calendar event has no usable DTSTART")
    if event.get("DTEND") is None:
        return
    end = getattr(event.get("DTEND"), "dt", None)
    if not isinstance(end, (date, datetime)):
        raise InvalidLibrarySource("Calendar event has no usable DTEND")
    if isinstance(start, datetime) != isinstance(end, datetime):
        raise InvalidLibrarySource("Calendar event mixes date and datetime boundaries")
    parse = (
        datetime.fromisoformat if isinstance(start, datetime) else date.fromisoformat
    )
    if parse(_to_iso(end)) < parse(_to_iso(start)):
        raise InvalidLibrarySource("Calendar event ends before it starts")


def parse_calendar(
    ics_content: bytes | str, window_start: date, window_end: date
) -> dict[str, Any]:
    """
    Parse an iCal feed and expand recurring events within [window_start, window_end).

    A window is required because some events recur forever (no UNTIL/COUNT).
    All-day events use date strings; `end` is exclusive, following iCal semantics.
    """
    try:
        calendar = icalendar.Calendar.from_ical(ics_content)
    except ValueError as error:
        raise InvalidLibrarySource(str(error)) from error
    _validate_calendar(calendar)

    events = []
    try:
        occurrences = recurring_ical_events.of(calendar).between(
            window_start, window_end
        )
    except ValueError as error:
        raise InvalidLibrarySource(str(error)) from error
    for event in occurrences:
        _validate_event(event)
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
        "ITEM_PIPELINES": {"nthu_scraper.spiders.nthu_libraries.LibrariesPipeline": 1},
        # calendar.google.com/robots.txt disallows everything, but the public iCal
        # URL is the official subscription feed meant for calendar clients. We fetch
        # three fixed feeds on a schedule, which is the same as a calendar app does.
        "ROBOTSTXT_OBEY": False,
    }

    async def start(self):
        for rss_type in RSS_TYPES:
            yield scrapy.Request(
                normalize_http_url(RSS_URL_TEMPLATE.format(rss_type)),
                callback=self.parse_rss_feed,
                errback=self.handle_error,
                cb_kwargs={"rss_type": rss_type},
            )

        for calendar_id, google_id in CALENDARS.items():
            yield scrapy.Request(
                normalize_http_url(ICAL_URL_TEMPLATE.format(quote(google_id))),
                callback=self.parse_calendar_feed,
                errback=self.handle_error,
                cb_kwargs={"calendar_id": calendar_id, "google_id": google_id},
            )

    def parse_rss_feed(self, response: Response, rss_type: str):
        try:
            items = parse_rss(response.text)
        except InvalidLibrarySource as error:
            self.logger.warning(
                "Invalid RSS [%s]; retaining previous data: %s", rss_type, error
            )
            return
        self.logger.info(f"✅ Parsed {len(items)} items from RSS [{rss_type}]")
        yield {"kind": "rss", "key": rss_type, "data": items}

    def parse_calendar_feed(self, response: Response, calendar_id: str, google_id: str):
        window_start, window_end = get_calendar_window(datetime.now(TAIPEI_TZ).date())
        try:
            calendar = parse_calendar(response.body, window_start, window_end)
        except InvalidLibrarySource as error:
            self.logger.warning(
                "Invalid calendar [%s]; retaining previous data: %s", calendar_id, error
            )
            return
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
                "url": normalize_http_url(
                    CALENDAR_EMBED_URL_TEMPLATE.format(google_id)
                ),
                "events": calendar["events"],
            },
        }

    def handle_error(self, failure):
        log_source_failure(failure)


class LibrariesPipeline:
    """Merge freshly crawled sources into the existing JSON files."""

    def open_spider(self, spider):
        self.rss: dict[str, list[dict[str, Any]]] = {}
        self.calendars: dict[str, dict[str, Any]] = {}
        previous_rss = load_json(LIBRARIES_RSS_JSON_PATH)
        previous_calendars = load_json(LIBRARIES_CALENDARS_JSON_PATH)
        self.previous_rss = previous_rss if previous_rss is not None else {}
        self.previous_calendars = (
            previous_calendars if previous_calendars is not None else []
        )
        if not isinstance(self.previous_rss, dict) or not isinstance(
            self.previous_calendars, list
        ):
            raise ValueError("Invalid library baseline structure")
        self.previous_rss = {
            key: normalize_rss_items(items, source=key)
            for key, items in self.previous_rss.items()
        }
        self.rss_baseline_changed = (
            previous_rss is not None and self.previous_rss != previous_rss
        )
        spider.logger.info(
            "Loaded library baseline: %d RSS feeds and %d calendars",
            len(self.previous_rss),
            len(self.previous_calendars),
        )

    def process_item(self, item, spider):
        if item["kind"] == "rss":
            item["data"] = normalize_rss_items(item["data"], source=item["key"])
            if not item["data"] and self.previous_rss.get(item["key"]):
                spider.logger.warning("Empty RSS refresh; retaining %s", item["key"])
                return item
            self.rss[item["key"]] = item["data"]
        elif item["kind"] == "calendar":
            if not item["data"]["events"] and any(
                old["id"] == item["key"] and old.get("events")
                for old in self.previous_calendars
            ):
                spider.logger.warning(
                    "Empty calendar refresh; retaining %s", item["key"]
                )
                return item
            self.calendars[item["key"]] = item["data"]
        return item

    def close_spider(self, spider):
        if self.rss or self.rss_baseline_changed:
            # Start from the previous file so feeds that failed this run are kept.
            rss_data = self.previous_rss.copy()
            rss_data.update(self.rss)
            rss_data = {key: rss_data[key] for key in RSS_TYPES if key in rss_data}
            if self.rss_baseline_changed:
                spider.logger.warning("Normalized retained library RSS data")
            self._save(spider, rss_data, LIBRARIES_RSS_JSON_PATH)
        else:
            spider.logger.error("❌ No RSS feed was crawled; keeping existing data")

        if self.calendars:
            previous = self.previous_calendars
            calendars = {calendar["id"]: calendar for calendar in previous}
            calendars.update(self.calendars)
            calendars_data = [calendars[key] for key in CALENDARS if key in calendars]
            self._save(spider, calendars_data, LIBRARIES_CALENDARS_JSON_PATH)
        else:
            spider.logger.error("❌ No calendar was crawled; keeping existing data")

    @staticmethod
    def _save(spider, data, path):
        save_json(data, path)
        spider.logger.info(f'✅ Saved library data to "{path}"')
