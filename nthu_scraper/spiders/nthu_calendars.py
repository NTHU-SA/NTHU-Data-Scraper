"""Publish the university's academic calendar at data/calendars.json."""

from datetime import datetime
from typing import Any
from urllib.parse import quote

import scrapy
from scrapy.http import Response

from nthu_scraper.spiders.nthu_libraries import (
    CALENDAR_EMBED_URL_TEMPLATE,
    ICAL_URL_TEMPLATE,
    TAIPEI_TZ,
    InvalidLibrarySource,
    get_calendar_window,
    parse_calendar,
)
from nthu_scraper.utils.constants import CALENDARS_JSON_PATH
from nthu_scraper.utils.crawl_safety import log_source_failure
from nthu_scraper.utils.file_utils import load_json, save_json
from nthu_scraper.utils.url_utils import normalize_http_url

GOOGLE_ID = "nthu.acad@gmail.com"
SOURCE_URL = "https://dgaa.site.nthu.edu.tw/p/412-1209-2942.php?Lang=zh-tw"
ICAL_URL = normalize_http_url(ICAL_URL_TEMPLATE.format(quote(GOOGLE_ID)))


class CalendarsSpider(scrapy.Spider):
    name = "nthu_calendars"
    custom_settings = {
        "ITEM_PIPELINES": {"nthu_scraper.spiders.nthu_calendars.CalendarsPipeline": 1},
        # Fetch only the official public subscription feed, as a calendar client does.
        "ROBOTSTXT_OBEY": False,
    }

    async def start(self):
        yield scrapy.Request(
            ICAL_URL,
            callback=self.parse_calendar_feed,
            errback=self.handle_error,
        )

    def parse_calendar_feed(self, response: Response):
        window_start, window_end = get_calendar_window(datetime.now(TAIPEI_TZ).date())
        try:
            calendar = parse_calendar(response.body, window_start, window_end)
        except InvalidLibrarySource as error:
            self.logger.warning(
                "Invalid academic calendar; retaining previous data: %s", error
            )
            return
        self.logger.info("Parsed %d academic calendar events", len(calendar["events"]))
        yield {
            "id": "academic",
            **calendar,
            "url": normalize_http_url(CALENDAR_EMBED_URL_TEMPLATE.format(GOOGLE_ID)),
            "source_url": SOURCE_URL,
            "ical_url": ICAL_URL,
        }

    def handle_error(self, failure):
        log_source_failure(failure)


class CalendarsPipeline:
    def open_spider(self, spider):
        previous = load_json(CALENDARS_JSON_PATH)
        self.previous = previous if previous is not None else []
        if not isinstance(self.previous, list) or any(
            not isinstance(calendar, dict)
            or not isinstance(calendar.get("id"), str)
            or not isinstance(calendar.get("events"), list)
            for calendar in self.previous
        ):
            raise ValueError("Invalid campus calendar baseline structure")
        self.calendars: dict[str, dict[str, Any]] = {}

    def process_item(self, item, spider):
        if not item["events"]:
            spider.logger.warning(
                "Empty campus calendar refresh; retaining previous data for %s",
                item["id"],
            )
            return item
        self.calendars[item["id"]] = item
        return item

    def close_spider(self, spider):
        if not self.calendars:
            spider.logger.error(
                "No campus calendar was refreshed; keeping existing data"
            )
            return
        calendars = {calendar["id"]: calendar for calendar in self.previous}
        calendars.update(self.calendars)
        save_json(
            [calendars[key] for key in sorted(calendars)],
            CALENDARS_JSON_PATH,
        )
        spider.logger.info("Saved campus calendars to %s", CALENDARS_JSON_PATH)
