"""Project settings; source-specific overrides live on each spider."""

from nthu_scraper.utils.request_utils import get_default_headers

BOT_NAME = "nthu_scraper"
SPIDER_MODULES = ["nthu_scraper.spiders"]
NEWSPIDER_MODULE = "nthu_scraper.spiders"
COMMANDS_MODULE = "nthu_scraper.commands"

LOG_LEVEL = "INFO"
ROBOTSTXT_OBEY = True

# Reuse a shared user-agent so every spider impersonates a real browser.
DEFAULT_REQUEST_HEADERS = get_default_headers()

TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
FEED_EXPORT_ENCODING = "utf-8"
