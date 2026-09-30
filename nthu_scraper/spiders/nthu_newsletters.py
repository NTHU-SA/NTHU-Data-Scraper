from collections.abc import Iterator

import scrapy
from scrapy.http import Response

from nthu_scraper.parsers import ParseError
from nthu_scraper.parsers.newsletters import (
    URL_PREFIX,
    newsletter_entries,
    parse_archive_articles,
    parse_newsletter_entry,
)
from nthu_scraper.utils.constants import NEWSLETTERS_JSON_PATH
from nthu_scraper.utils.crawl_safety import WholeDatasetSpider
from nthu_scraper.utils.file_utils import load_json, save_json


class NewsletterItem(scrapy.Item):
    """
    電子報資料項目。包含名稱、連結、表格資料以及實際的文章內容。
    """

    name = scrapy.Field()
    link = scrapy.Field()
    details = scrapy.Field()
    articles = scrapy.Field()


class NewsletterSpider(WholeDatasetSpider):
    """
    清華大學電子報爬蟲。

    此爬蟲會抓取清華大學所有電子報的列表，以及各個電子報中的文章列表。
    爬取過程使用 Scrapy 框架，可確保高效率的資料收集。
    """

    name = "nthu_newsletters"
    allowed_domains = ["newsletter.cc.nthu.edu.tw"]
    start_urls = [f"{URL_PREFIX}/nthu-list/search.html"]
    custom_settings = {
        "ITEM_PIPELINES": {
            "nthu_scraper.spiders.nthu_newsletters.NewsletterPipeline": 1
        },
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.processed_urls: set[str] = set()

    def parse(self, response: Response) -> Iterator[scrapy.Request]:
        """
        解析電子報列表頁面，提取各電子報的名稱、連結與表格資料。

        Args:
            response (Response): Scrapy 下載器返回的回應物件

        Yields:
            Request: 為每個電子報發送請求，取得其文章列表
        """
        self.logger.info(f"🔗 正在處理電子報列表頁面：{response.url}")

        try:
            entries = newsletter_entries(response)
        except ParseError as error:
            self.mark_incomplete(str(error))
            return

        for entry in entries:
            try:
                newsletter = NewsletterItem(parse_newsletter_entry(entry, response.url))
            except ParseError as error:
                self.mark_incomplete(str(error))
                continue
            link = newsletter["link"]

            # 如果連結已經在處理清單中，跳過
            if link in self.processed_urls:
                continue

            self.processed_urls.add(link)

            # 發送請求獲取此電子報的文章列表
            yield scrapy.Request(
                url=link,
                callback=self.parse_newsletter_content,
                errback=self.handle_request_error,
                meta={"newsletter": newsletter},
                dont_filter=False,  # 不重複處理相同的 URL
            )

    def parse_newsletter_content(self, response: Response) -> Iterator[NewsletterItem]:
        """
        解析單個電子報頁面，提取文章標題、連結和日期。

        Args:
            response (Response): 電子報頁面的回應物件

        Yields:
            NewsletterItem: 包含電子報詳細資訊及其文章列表的 Item 物件
        """
        newsletter = response.meta["newsletter"]
        self.logger.info(f"🔗 正在處理電子報：{newsletter['name']} {response.url}")

        try:
            articles = parse_archive_articles(response, response.url)
        except ParseError as error:
            self.mark_incomplete(f"{response.url}: {error}")
            return

        if not articles:
            self.mark_incomplete(f"No usable newsletter articles: {response.url}")
            return
        newsletter["articles"] = articles
        yield newsletter


class NewsletterPipeline:
    """
    Scrapy Pipeline，用於將爬取的 Item 儲存為 JSON 檔案。
    同時會合併所有電子報資料到一個總合檔案。
    """

    def open_spider(self, spider):
        """
        Spider 開啟時執行，建立必要的資料夾。
        """
        NEWSLETTERS_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
        load_json(NEWSLETTERS_JSON_PATH)
        self.combined_data = []

    def process_item(self, item, spider):
        """
        處理每一個 Item。

        Args:
            item (NewsletterItem): 爬取到的電子報資料
            spider (NewsletterSpider): 爬蟲實例

        Returns:
            NewsletterItem: 處理後的 Item
        """
        serializable_item = dict(item)
        spider.logger.info("Collected newsletter: %s", item["name"])
        spider.logger.debug(serializable_item)
        self.combined_data.append(serializable_item)

        return item

    def close_spider(self, spider):
        """
        Spider 關閉時執行，合併所有電子報 JSON 檔案。
        """
        if not spider.can_replace_dataset(self.combined_data):
            return
        sorted_data = sorted(self.combined_data, key=lambda x: x["name"])
        save_json(sorted_data, NEWSLETTERS_JSON_PATH)
        spider.logger.info(f'✅ 成功儲存電子報資料至 "{NEWSLETTERS_JSON_PATH}"')
