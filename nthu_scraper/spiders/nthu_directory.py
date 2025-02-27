import json
import os
from pathlib import Path
from typing import Any, Dict, List

import scrapy

# --- 全域參數設定 ---
DATA_FOLDER = Path(os.getenv("DATA_FOLDER", "temp"))
COMBINED_JSON_FILE = DATA_FOLDER / "directory.json"
URL_PREFIX = "https://tel.net.nthu.edu.tw/nthusearch/"

# --- 中英文對照字典 ---
DEPARTMENT_TRANSLATION = {
    "分機": "extension",
    "直撥電話": "phone",
    "傳真電話": "fax",
    "Email": "email",
    "網頁": "website",
    "姓名": "name",
    "職稱/職責": "title",
    "備註": "note",
}


# --- 輔助函式 ---
def _translate_key(key: str) -> str:
    """
    將中文 key 轉換為英文 key。

    Args:
        key (str): 中文 key。

    Returns:
        str: 英文 key。
    """
    key = key.strip().replace("　", "")  # 移除空白
    if key in DEPARTMENT_TRANSLATION:
        return DEPARTMENT_TRANSLATION[key]
    else:
        print(f"❌ 未知的 key: {key}")
        return key


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


class DirectorySpider(scrapy.Spider):
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

    def parse(self, response):
        """
        解析首頁，抓取所有系所的 URL。

        Args:
            response (scrapy.http.Response): 下載器返回的回應物件。

        Yields:
            scrapy.Request: 針對每個系所 URL 發送請求。
        """
        departments = []
        for dept_link in response.css("li a"):
            href = dept_link.css("::attr(href)").get()
            name = dept_link.css("::text").get()
            if href and name:
                dept_url = URL_PREFIX + href
                departments.append({"name": name.strip(), "url": dept_url})
                yield scrapy.Request(
                    url=dept_url,
                    callback=self.parse_dept_page,
                    meta={"dept_name": name.strip() if name else "Unknown Department"},
                )

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
        contact_data = {}
        people_data_list = []

        story_left = response.css("div.story_left")
        if story_left:
            for link in story_left.css("a"):
                dept_page_link = link.css("::attr(href)").get()
                dept_page_name = link.css("::text").get()
                if dept_page_link and dept_page_name:
                    sub_dept_url = URL_PREFIX + dept_page_link
                    departments.append(
                        {
                            "name": dept_page_name.strip(),
                            "url": sub_dept_url,
                        }
                    )
                    yield scrapy.Request(
                        url=sub_dept_url,
                        callback=self.parse_dept_page,
                        meta={
                            "dept_name": dept_page_name.strip(),
                            "parent_name": dept_name,
                        },  # 傳遞 parent_name
                    )

        story_max = response.css("div.story_max")
        if story_max:
            tables = story_max.css("table")
            if tables:
                contact_table = tables[0]
                contact_data = self.parse_contact_table(contact_table)
                if len(tables) > 1:
                    people_table = tables[1]
                    people_data_list = self.parse_people_table(people_table)

        dept_detail = DepartmentDetail(
            departments=departments,
            contact=ContactInfo(contact_data),
            people=[Person(p) for p in people_data_list],
        )

        # 計算 index
        query_params = response.url.split("?")[1] if "?" in response.url else ""
        dd_value = None
        for param in query_params.split("&"):
            if "dd=" in param:
                dd_value = param.split("=")[1]
                break

        item = DepartmentItem()
        item["index"] = dd_value
        item["name"] = dept_name
        item["parent_name"] = response.meta.get("parent_name", None)
        item["url"] = response.url
        item["details"] = dept_detail
        yield item

    def parse_contact_table(self, table):
        """
        解析聯絡資訊表格。

        Args:
            table (scrapy.selector.Selector): 聯絡資訊表格的 Selector 物件。

        Returns:
            Dict[str, str]: 解析後的聯絡資訊字典。
        """
        contact = {}
        for row in table.css("tr"):
            cols = row.css("td")
            if len(cols) >= 2:
                key_selector = cols[0].css("::text")
                value_selector = cols[1]

                key = key_selector.get().strip() if key_selector else ""
                if key == "":
                    continue
                key = _translate_key(key)  # 將中文 key 轉換為英文 key

                link = value_selector.css("a::attr(href)").get()
                value_text = value_selector.css("::text").get()  # 先取得 text

                if link:
                    value = link.replace("mailto:", "") if "mailto:" in link else link
                elif value_text:
                    value = value_text.strip()
                else:
                    value = "N/A"
                contact[key] = value
        return contact

    def parse_people_table(self, table):
        """
        解析人員資訊表格。

        Args:
            table (scrapy.selector.Selector): 人員資訊表格的 Selector 物件。

        Returns:
            List[Dict[str, str]]: 解析後的人員資訊列表。
        """
        people = []
        rows = table.css("tr")
        if rows:
            header_texts = [th.css("::text").get() for th in rows[0].css("td")]
            headers = [
                h.strip() if h else f"header_{i}" for i, h in enumerate(header_texts)
            ]

            for row in rows[1:]:
                cols = row.css("td")
                person = {}
                for i, col in enumerate(cols):
                    if i < len(headers):  # 確保 header 存在
                        header = headers[i]
                        header = _translate_key(header)  # 將中文 key 轉換為英文 key
                        link = col.css("a::attr(href)").get()
                        col_text = col.css("::text").get()  # 先取得 text
                        if link:
                            person[header] = link.replace("mailto:", "")
                        elif col_text:
                            person[header] = col_text.strip()
                        else:
                            person[header] = None
                people.append(person)
        return people


class JsonPipeline:
    """
    Scrapy Pipeline，用於將爬取的 Item 儲存為 JSON 檔案。
    """

    def open_spider(self, spider):
        """
        Spider 開啟時執行，建立必要的資料夾。
        """
        COMBINED_JSON_FILE.parent.mkdir(parents=True, exist_ok=True)
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
        self.combined_data.sort(key=lambda x: x.get("index", ""))
        with open(COMBINED_JSON_FILE, "w", encoding="utf-8") as f:
            json.dump(self.combined_data, f, ensure_ascii=False, indent=4)
        spider.logger.info(f'✅ 成功儲存通訊錄資料至 "{COMBINED_JSON_FILE}"')
