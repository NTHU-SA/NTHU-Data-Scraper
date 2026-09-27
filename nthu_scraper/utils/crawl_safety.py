"""Completeness tracking for crawlers that replace a whole dataset."""

import logging

import scrapy
from scrapy import signals
from scrapy.exceptions import IgnoreRequest
from scrapy.settings.default_settings import RETRY_EXCEPTIONS
from scrapy.spidermiddlewares.httperror import HttpError
from scrapy.utils.misc import load_object

EXPECTED_REQUEST_ERRORS = (
    HttpError,
    IgnoreRequest,
    *(
        load_object(error) if isinstance(error, str) else error
        for error in RETRY_EXCEPTIONS
    ),
)


def log_source_failure(failure):
    failure.trap(*EXPECTED_REQUEST_ERRORS)
    logging.getLogger(__name__).warning(
        "Source request failed; retaining previous data where available: %s (%s)",
        failure.request.url,
        failure.value,
    )


class WholeDatasetSpider(scrapy.Spider):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.crawl_incomplete = False

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super().from_crawler(crawler, *args, **kwargs)
        crawler.signals.connect(spider.handle_spider_error, signal=signals.spider_error)
        crawler.signals.connect(spider.handle_spider_error, signal=signals.item_error)
        return spider

    async def start(self):
        for url in self.start_urls:
            yield scrapy.Request(url, errback=self.handle_request_error)

    def mark_incomplete(self, reason):
        self.crawl_incomplete = True
        self.logger.warning(
            "Incomplete crawl; retaining previous whole dataset: %s", reason
        )

    def handle_request_error(self, failure):
        failure.trap(*EXPECTED_REQUEST_ERRORS)
        self.mark_incomplete(f"{failure.request.url}: {failure.value}")

    def handle_spider_error(self, failure):
        self.mark_incomplete(str(failure.value))

    def can_replace_dataset(self, data):
        if not data:
            self.mark_incomplete("No usable records")
        return not self.crawl_incomplete
