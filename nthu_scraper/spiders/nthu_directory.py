import json
from pathlib import Path
from typing import Any, Dict, List

import scrapy

from nthu_scraper.utils.constants import DATA_FOLDER
from nthu_scraper.utils.file_utils import load_json, save_json
from nthu_scraper.utils.crawl_safety import WholeDatasetSpider
from nthu_scraper.parsers import ParseError
from nthu_scraper.parsers.directory import (
    URL_PREFIX,
    parse_department_details,
    parse_department_index,
    parse_department_link,
)

# --- 全域參數設定 ---
COMBINED_JSON_FILE = DATA_FOLDER / "directory.json"


# --- 資料結構定義 ---
class ContactInfo:
    """
    聯絡資訊資料結構。
    """

    def __init__(self, data: Dict[str, str | None]):
        """
        初始化 ContactInfo 物件。

        Args:
            data (Dict[str, str]): 聯絡資訊字典，鍵值為項目名稱，值為項目內容。
        """
        self.data = data

    def __repr__(self):
        return f"ContactInfo({self.data})"


class Person:
    """
    人員資料結構。
    """

    def __init__(self, data: Dict[str, str | None]):
        """
        初始化 Person 物件。

        Args:
            data (Dict[str, str]): 人員資訊字典，鍵值為欄位名稱，值為欄位內容。
        """
        self.data = data

    def __repr__(self):
        return f"Person({self.data})"


class DepartmentDetail:
    """
    系所詳細資料結構。
    """

    def __init__(
        self,
        departments: List[Dict[str, str]],
        contact: ContactInfo,
        people: List[Person],
    ):
        """
        初始化 DepartmentDetail 物件。

        Args:
            departments (List[Dict[str, str]]): 下級部門列表，包含名稱和 URL。
            contact (ContactInfo): 聯絡資訊物件。
            people (List[Person]): 人員列表，包含 Person 物件。
        """
        self.departments = departments
        self.contact = contact
        self.people = people

    def __repr__(self):
        return (
            f"DepartmentDetail(departments={self.departments}, "
            f"contact={self.contact}, people_count={len(self.people)})"
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "departments": self.departments,
            "contact": self.contact.data,
            "people": [person.data for person in self.people],
        }


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
        "ITEM_PIPELINES": {"nthu_scraper.spiders.nthu_directory.JsonPipeline": 1},
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


class JsonPipeline:
    """
    Scrapy Pipeline，用於將爬取的 Item 儲存為 JSON 檔案。
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
        處理每一個 Item，儲存系所詳細資料到 JSON 檔案。
        """
        serializable_item = dict(item)
        if hasattr(serializable_item.get("details"), "to_dict"):
            serializable_item["details"] = serializable_item["details"].to_dict()
        spider.logger.info(f"✅ 成功儲存【{item['name']}】")
        self.combined_data.append(serializable_item)
        return item

    def close_spider(self, spider):
        """
        Spider 關閉時執行，合併所有系所 JSON 檔案。
        """
        if not spider.can_replace_dataset(self.combined_data):
            return
        self.combined_data.sort(key=lambda x: x.get("index") or "")
        save_json(self.combined_data, COMBINED_JSON_FILE)
        spider.logger.info(f'✅ 成功儲存通訊錄資料至 "{COMBINED_JSON_FILE}"')
