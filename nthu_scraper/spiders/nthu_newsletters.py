import json
import re
from datetime import datetime
from pathlib import Path
from typing import Set

import scrapy
from scrapy.http import Response

from nthu_scraper.utils.constants import DATA_FOLDER
from nthu_scraper.utils.file_utils import load_json, save_json
from nthu_scraper.utils.crawl_safety import WholeDatasetSpider

# --- 全域參數設定 ---
COMBINED_JSON_FILE = DATA_FOLDER / "newsletters.json"
URL_PREFIX = "https://newsletter.cc.nthu.edu.tw"


# --- 資料結構定義 ---
class NewsletterItem(scrapy.Item):
    """
    電子報資料項目。包含名稱、連結、表格資料以及實際的文章內容。
    """

    name = scrapy.Field()
    link = scrapy.Field()
    details = scrapy.Field()
    articles = scrapy.Field()


class NewsletterArticle(scrapy.Item):
    """
    電子報中單篇文章的資料結構。
    """

    title = scrapy.Field()
    link = scrapy.Field()
    date = scrapy.Field()


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
        "ITEM_PIPELINES": {"nthu_scraper.spiders.nthu_newsletters.JsonPipeline": 1},
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.processed_urls: Set[str] = set()

    def parse(self, response: Response) -> scrapy.Request:
        """
        解析電子報列表頁面，提取各電子報的名稱、連結與表格資料。

        Args:
            response (Response): Scrapy 下載器返回的回應物件

        Yields:
            Request: 為每個電子報發送請求，取得其文章列表
        """
        self.logger.info(f"🔗 正在處理電子報列表頁面：{response.url}")

        gallery = response.css("div.gallery")
        if not gallery:
            self.mark_incomplete("Newsletter root contained no gallery")
            return

        for li in gallery.css("li"):
            h3 = li.css("h3")
            if not h3:
                continue

            a = h3.css("a")
            if not a:
                continue

            name = a.css("::text").get().strip()
            link = a.css("::attr(href)").get()

            if not link or not name:
                continue

            # 提取表格資料
            table_data = {}
            table = li.css("table")
            if table:
                for row in table.css("tr"):
                    elements = row.css("td, th")  # 同時選擇 td 與 th
                    if len(elements) == 2:
                        key = elements[0].css("::text").get().strip()
                        value = elements[1].css("::text").get().strip()
                        if key and value:  # 確保兩者都非空
                            table_data[key] = value

            newsletter = NewsletterItem()
            newsletter["name"] = name
            newsletter["link"] = link
            newsletter["details"] = table_data
            newsletter["articles"] = []

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

    def parse_newsletter_content(self, response: Response) -> NewsletterItem:
        """
        解析單個電子報頁面，提取文章標題、連結和日期。

        Args:
            response (Response): 電子報頁面的回應物件

        Yields:
            NewsletterItem: 包含電子報詳細資訊及其文章列表的 Item 物件
        """
        newsletter = response.meta["newsletter"]
        self.logger.info(f"🔗 正在處理電子報：{newsletter['name']} {response.url}")

        content = response.css("div#acyarchivelisting")
        if not content:
            self.logger.warning(f"⚠️ 找不到電子報內容：{newsletter['name']}")
            self.mark_incomplete(f"Missing newsletter content: {response.url}")
            return

        table = content.css("table.contentpane")
        if not table:
            self.logger.warning(f"⚠️ 找不到文章表格：{newsletter['name']}")
            self.mark_incomplete(f"Missing newsletter article table: {response.url}")
            return

        articles = []
        for archive_row in table.css("div.archiveRow"):
            article = NewsletterArticle()

            # 提取文章標題與連結
            a = archive_row.css("a")
            if a:
                onclick = a.css("::attr(onclick)").get()
                if onclick:
                    match = re.search(r"openpopup\('(.*?)',", onclick)
                    if match:
                        article["link"] = f"{URL_PREFIX}{match.group(1)}"
                article["title"] = a.css("::text").get().strip()

            # 提取文章日期
            date_span = archive_row.css("span.sentondate")
            if date_span:
                date_str = date_span.css("::text").get().strip()
                if date_str:
                    date_str = date_str.replace("Sent on ", "")
                    date_str = self._convert_chinese_month_to_english(date_str)
                    try:
                        parsed_date = datetime.strptime(date_str, "%d %b %Y")
                        article["date"] = parsed_date.strftime("%Y-%m-%d")
                    except ValueError:
                        self.logger.error(f"❎ 日期解析錯誤: {date_str}")
                        article["date"] = date_str  # 保留原始日期字串

            # 只有當文章至少有標題時才加入列表
            if article.get("title"):
                articles.append(dict(article))
            else:
                self.mark_incomplete(f"Unusable newsletter article: {response.url}")

        if not articles:
            self.mark_incomplete(f"No usable newsletter articles: {response.url}")
            return
        newsletter["articles"] = articles
        yield newsletter

    def _convert_chinese_month_to_english(self, date_str: str) -> str:
        """
        將中文月份轉換為英文縮寫。

        Args:
            date_str (str): 包含中文月份的日期字串

        Returns:
            str: 轉換後的日期字串，月份為英文縮寫
        """
        month_mapping = {
            " 一月 ": " Jan ",
            " 二月 ": " Feb ",
            " 三月 ": " Mar ",
            " 四月 ": " Apr ",
            " 五月 ": " May ",
            " 六月 ": " Jun ",
            " 七月 ": " Jul ",
            " 八月 ": " Aug ",
            " 九月 ": " Sep ",
            " 十月 ": " Oct ",
            " 十一月 ": " Nov ",
            " 十二月 ": " Dec ",
        }
        for zh_month, en_month in month_mapping.items():
            date_str = date_str.replace(zh_month, en_month)
        return date_str


class JsonPipeline:
    """
    Scrapy Pipeline，用於將爬取的 Item 儲存為 JSON 檔案。
    同時會合併所有電子報資料到一個總合檔案。
    """

    def open_spider(self, spider):
        """
        Spider 開啟時執行，建立必要的資料夾。
        """
        COMBINED_JSON_FILE.parent.mkdir(parents=True, exist_ok=True)
        load_json(COMBINED_JSON_FILE)
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
        spider.logger.info(f"✅ 成功儲存【{item['name']}】資料")
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
        if save_json(sorted_data, COMBINED_JSON_FILE):
            spider.logger.info(f'✅ 成功儲存電子報資料至 "{COMBINED_JSON_FILE}"')
        else:
            spider.logger.error(f'❌ 儲存電子報資料失敗 "{COMBINED_JSON_FILE}"')
