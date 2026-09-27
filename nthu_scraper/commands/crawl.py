"""Make implementation failures fatal instead of relying on Scrapy's log output."""

import logging

from scrapy import signals
from scrapy.commands.crawl import Command as ScrapyCrawlCommand


class _CrawlErrors(logging.Handler):
    def __init__(self):
        super().__init__(logging.ERROR)
        self.failed = False

    def emit(self, record):
        # Expected upstream failures are handled explicitly without a traceback.
        if record.exc_info:
            self.failed = True


class Command(ScrapyCrawlCommand):
    def _create_crawler(self, *args, **kwargs):
        crawler = super()._create_crawler(*args, **kwargs)
        self._checked_crawler = crawler
        crawler.signals.connect(self._implementation_error, signal=signals.spider_error)
        crawler.signals.connect(self._implementation_error, signal=signals.item_error)
        return crawler

    def _implementation_error(self, failure):
        self._errors.failed = True

    def run(self, args, opts):
        self._errors = _CrawlErrors()
        self._checked_crawler = None
        root_logger = logging.getLogger()
        root_logger.addHandler(self._errors)
        try:
            super().run(args, opts)
        finally:
            root_logger.removeHandler(self._errors)
        if self._errors.failed:
            self.exitcode = 1
        if self._checked_crawler is not None:
            stats = self._checked_crawler.stats
            if stats is None or stats.get_value("finish_reason") != "finished":
                self.exitcode = 1
