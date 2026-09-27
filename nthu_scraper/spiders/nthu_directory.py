import scrapy

from nthu_scraper.parsers import ParseError
from nthu_scraper.parsers.directory import (
    URL_PREFIX,
    parse_department_details,
    parse_department_index,
    parse_department_link,
)
from nthu_scraper.utils.constants import DIRECTORY_JSON_PATH
from nthu_scraper.utils.crawl_safety import WholeDatasetSpider
from nthu_scraper.utils.file_utils import load_json, save_json


class DepartmentItem(scrapy.Item):
    """
    Scrapy Item，用於儲存系所詳細資料。
    """

    index = scrapy.Field()
    name = scrapy.Field()
    parent_index = scrapy.Field()  # 上級單位 index
    parent_name = scrapy.Field()  # 上級單位名稱
    url = scrapy.Field()
    details = scrapy.Field()


class DirectorySpider(WholeDatasetSpider):
    """
    清華大學系所資訊爬蟲。
    """

    name = "nthu_directory"
    allowed_domains = ["tel.net.nthu.edu.tw"]
    start_urls = [URL_PREFIX + "index.php"]
    custom_settings = {
        "LOG_LEVEL": "INFO",
        "ITEM_PIPELINES": {"nthu_scraper.spiders.nthu_directory.DirectoryPipeline": 1},
        "AUTOTHROTTLE_ENABLED": True,
    }

    def _parse_department_link(self, link):
        try:
            return parse_department_link(link)
        except ParseError as error:
            self.mark_incomplete(str(error))
            return None

    def parse(self, response):
        """
        解析首頁，抓取所有系所的 URL。

        Args:
            response (scrapy.http.Response): 下載器返回的回應物件。

        Yields:
            scrapy.Request: 針對每個系所 URL 發送請求。
        """
        departments = []
        for entry in response.css("li"):
            department = self._parse_department_link(entry.css("a"))
            if department is None:
                continue
            departments.append(department)
            yield scrapy.Request(
                url=department["url"],
                callback=self.parse_dept_page,
                errback=self.handle_request_error,
                meta={"dept_name": department["name"]},
            )
        if not departments:
            self.mark_incomplete("Directory root contained no departments")

    def parse_dept_page(self, response):
        """
        解析系所頁面，抓取系所詳細資訊，並迭代爬取下級部門。

        Args:
            response (scrapy.http.Response): 系所頁面回應物件。

        Yields:
            DepartmentItem: 包含系所詳細資訊的 Item 物件。
            scrapy.Request: 針對下級部門 URL 發送請求。
        """
        dept_name = response.meta["dept_name"]
        departments = []

        story_left = response.css("div.story_left")
        if story_left:
            for link in story_left.css("a"):
                department = self._parse_department_link(link)
                if department is None:
                    continue
                departments.append(department)
                yield scrapy.Request(
                    url=department["url"],
                    callback=self.parse_dept_page,
                    errback=self.handle_request_error,
                    meta={
                        "dept_name": department["name"],
                        "parent_name": dept_name,
                    },
                )

        try:
            details = parse_department_details(response, departments)
        except ParseError as error:
            self.mark_incomplete(f"{response.url}: {error}")
            return
        if not any(details.values()):
            self.mark_incomplete(f"No department details: {response.url}")
            return

        item = DepartmentItem()
        item["index"] = parse_department_index(response.url)
        item["name"] = dept_name
        item["parent_name"] = response.meta.get("parent_name", None)
        item["url"] = response.url
        item["details"] = details
        yield item


class DirectoryPipeline:
    """
    Scrapy Pipeline，用於將爬取的 Item 儲存為 JSON 檔案。
    """

    def open_spider(self, spider):
        """
        Spider 開啟時執行，建立必要的資料夾。
        """
        DIRECTORY_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
        load_json(DIRECTORY_JSON_PATH)
        self.combined_data = []

    def process_item(self, item, spider):
        """
        處理每一個 Item，儲存系所詳細資料到 JSON 檔案。
        """
        serializable_item = dict(item)
        spider.logger.info("Collected department: %s", item["name"])
        self.combined_data.append(serializable_item)
        return item

    def close_spider(self, spider):
        """
        Spider 關閉時執行，合併所有系所 JSON 檔案。
        """
        if not spider.can_replace_dataset(self.combined_data):
            return
        self.combined_data.sort(key=lambda x: x.get("index") or "")
        save_json(self.combined_data, DIRECTORY_JSON_PATH)
        spider.logger.info(f'✅ 成功儲存通訊錄資料至 "{DIRECTORY_JSON_PATH}"')
