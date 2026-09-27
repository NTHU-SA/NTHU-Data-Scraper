"""Data-URI-only spiders for subprocess tests of the real Scrapy lifecycle."""

from datetime import date
from urllib.parse import quote

import scrapy
from twisted.internet.error import DNSLookupError

from nthu_scraper.spiders.nthu_libraries import LibrariesSpider
from nthu_scraper.spiders.nthu_buses import BusesSpider
from nthu_scraper.spiders.nthu_maps import MapSpider
from nthu_scraper.spiders.nthu_courses import CoursesSpider
from nthu_scraper.spiders.nthu_announcements_item import AnnouncementsItemSpider
from nthu_scraper.storage import write_json_atomic
from nthu_scraper.utils.constants import DATA_FOLDER
from nthu_scraper.utils.crawl_safety import log_source_failure


class FailRequestMiddleware:
    def process_request(self, request, spider):
        if request.meta.get("implementation_error"):
            raise AttributeError("offline injected downloader regression")
        if request.meta.get("fail_request") or request.url == "data:text/plain,failed":
            raise DNSLookupError("offline injected upstream failure")


class OfflineLibrariesSpider(LibrariesSpider):
    name = "offline_libraries"
    custom_settings = {
        **LibrariesSpider.custom_settings,
        "RETRY_ENABLED": False,
        "DOWNLOADER_MIDDLEWARES": {"safety_spiders.FailRequestMiddleware": 543},
    }

    async def start(self):
        yield scrapy.Request(
            "data:text/xml," + quote("<rss><channel><item><title>New</title></item></channel></rss>"),
            callback=self.parse_rss_feed, cb_kwargs={"rss_type": "news"},
        )
        yield scrapy.Request(
            "data:text/xml,broken", callback=self.parse_rss_feed,
            cb_kwargs={"rss_type": "exhibit"},
            errback=self.handle_error, meta={"fail_request": True},
        )
        yield scrapy.Request(
            "data:text/xml,%3Crss%3E", callback=self.parse_rss_feed,
            cb_kwargs={"rss_type": "branches"},
        )
        yield scrapy.Request(
            "data:text/calendar,broken", callback=self.parse_calendar_feed,
            cb_kwargs={"calendar_id": "main", "google_id": "main@test"},
        )
        ics = (
            "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:new\r\n"
            f"DTSTART;VALUE=DATE:{date.today().year}0927\r\n"
            "SUMMARY:New\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
        )
        yield scrapy.Request(
            "data:text/calendar," + quote(ics), callback=self.parse_calendar_feed,
            cb_kwargs={"calendar_id": "hss", "google_id": "hss@test"},
        )


class OfflineBusesSpider(BusesSpider):
    name = "offline_buses"
    allowed_domains = []
    custom_settings = {
        **BusesSpider.custom_settings,
        "ROBOTSTXT_OBEY": False,
        "RETRY_ENABLED": False,
        "DOWNLOADER_MIDDLEWARES": {"safety_spiders.FailRequestMiddleware": 543},
    }

    async def start(self):
        yield scrapy.Request(
            "data:text/html," + quote('const towardTSMCBuildingInfo = {route:"new"};'),
            meta={"bus_type": "main"}, errback=log_source_failure,
        )
        yield scrapy.Request(
            "data:text/html,failed", meta={"bus_type": "nanda", "fail_request": True},
            errback=log_source_failure,
        )


class OfflineAnnouncementsSpider(AnnouncementsItemSpider):
    name = "offline_announcements"
    custom_settings = {
        **AnnouncementsItemSpider.custom_settings,
        "ROBOTSTXT_OBEY": False,
        "RETRY_ENABLED": False,
        "DOWNLOADER_MIDDLEWARES": {"safety_spiders.FailRequestMiddleware": 543},
    }


class OfflineBrokenLibrarySpider(OfflineLibrariesSpider):
    name = "offline_broken_library"

    def parse_rss_feed(self, response, rss_type):
        raise ValueError("offline injected library regression")


class OfflineCoursesSpider(CoursesSpider):
    name = "offline_courses"
    allowed_domains = []

    async def start(self):
        yield scrapy.Request(
            "data:application/json," + quote('{"error": "unexpected structure"}'),
            meta={"data_type": "latest"},
        )


class OfflineMapsSpider(MapSpider):
    name = "offline_maps"
    allowed_domains = []
    custom_settings = {
        **MapSpider.custom_settings,
        "ROBOTSTXT_OBEY": False,
        "RETRY_ENABLED": False,
        "DOWNLOADER_MIDDLEWARES": {"safety_spiders.FailRequestMiddleware": 543},
    }

    async def start(self):
        yield scrapy.Request(
            "data:text/html," + quote('<option value="1,2">New</option>'),
            meta={"map_type": "MainZH"}, errback=log_source_failure,
        )
        yield scrapy.Request(
            "data:text/html,failed", meta={"map_type": "MainEN", "fail_request": True},
            errback=log_source_failure,
        )


class BadHookPipeline:
    def process_item(self, item, spider, unexpected_required_argument):
        return item


class FailurePipeline:
    @classmethod
    def from_crawler(cls, crawler):
        if crawler.spider.scenario == "import":
            raise ImportError("offline injected import regression")
        if crawler.spider.scenario == "hook":
            return BadHookPipeline()
        return cls()

    def open_spider(self, spider):
        if spider.scenario == "open":
            raise RuntimeError("offline injected open regression")

    def process_item(self, item, spider):
        if spider.scenario == "item":
            raise RuntimeError("offline injected item regression")
        if spider.scenario == "write":
            write_json_atomic({"bad": object()}, DATA_FOLDER / "preserved.json")
        return item

    def close_spider(self, spider):
        if spider.scenario == "close":
            raise RuntimeError("offline injected close regression")


class OfflineFailureSpider(scrapy.Spider):
    name = "offline_failure"
    scenario = "success"
    custom_settings = {
        "ROBOTSTXT_OBEY": False,
        "ITEM_PIPELINES": {"safety_spiders.FailurePipeline": 1},
        "DOWNLOADER_MIDDLEWARES": {"safety_spiders.FailRequestMiddleware": 543},
    }

    async def start(self):
        if self.scenario == "start":
            raise RuntimeError("offline injected start regression")
        yield scrapy.Request(
            "data:text/plain,test",
            meta={"implementation_error": self.scenario == "request"},
            errback=log_source_failure,
        )

    def parse(self, response):
        if self.scenario == "callback":
            raise AttributeError("offline injected parser regression")
        yield {"ok": True}
