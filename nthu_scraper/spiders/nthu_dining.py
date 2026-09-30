import scrapy

from nthu_scraper.parsers import ParseError
from nthu_scraper.parsers.dining import parse_dining_html
from nthu_scraper.utils.constants import DINING_JSON_PATH
from nthu_scraper.utils.crawl_safety import log_source_failure
from nthu_scraper.utils.file_utils import save_json
from nthu_scraper.utils.url_utils import normalize_http_url


class DiningItem(scrapy.Item):
    """
    餐廳資料 Item
    """

    data = scrapy.Field()


class DiningSpider(scrapy.Spider):
    """
    清華大學餐廳資訊爬蟲
    """

    name = "nthu_dining"
    allowed_domains = ["ddfm.site.nthu.edu.tw"]
    start_urls = [
        normalize_http_url(
            "https://ddfm.site.nthu.edu.tw/p/404-1494-256455.php?Lang=zh-tw"
        )
    ]
    custom_settings = {
        "ITEM_PIPELINES": {"nthu_scraper.spiders.nthu_dining.DiningPipeline": 1},
    }

    async def start(self):
        for url in self.start_urls:
            yield scrapy.Request(url, errback=log_source_failure)

    def parse(self, response):
        """
        解析餐廳資訊頁面，提取餐廳資料。
        """
        try:
            dining_data = parse_dining_html(response.text, response.url)
        except ParseError as error:
            self.logger.warning(
                "Invalid dining source; retaining previous data: %s", error
            )
            return

        if dining_data:
            yield DiningItem(data=dining_data)
        else:
            self.logger.error("❎ 未能解析到任何餐廳資料")


class DiningPipeline:
    """
    Scrapy Pipeline，用於將爬取的 DiningItem 儲存為 JSON 檔案。
    """

    def open_spider(self, spider):
        """
        Spider 開啟時執行，建立必要的資料夾。
        """
        DINING_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)

    def process_item(self, item, spider):
        """
        處理每一個 DiningItem，儲存餐廳資料到 JSON 檔案。
        """
        if isinstance(item, DiningItem):
            save_json(item["data"], DINING_JSON_PATH)
            spider.logger.info(f'✅ 成功儲存餐廳資料至 "{DINING_JSON_PATH}"')
        return item
