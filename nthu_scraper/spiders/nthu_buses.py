"""清華大學公車資訊爬蟲 - 重構版本"""

import re
import ast
from pathlib import Path
from typing import Any, Dict, List, Optional

import scrapy

from nthu_scraper.utils.constants import (
    ANNOUNCEMENTS_JSON_PATH,
    BUSES_FOLDER,
    BUSES_JSON_PATH,
)
from nthu_scraper.utils.file_utils import load_json, save_json

# 公車路線配置
BUS_CONFIG = {
    "main": {
        "url": "https://affairs.site.nthu.edu.tw/p/412-1165-20978.php?Lang=zh-tw",
        "schedule_images": None,
        "info_vars": ["towardTSMCBuildingInfo", "towardMainGateInfo"],
        "schedule_vars": [
            "weekdayBusScheduleTowardTSMCBuilding",
            "weekendBusScheduleTowardTSMCBuilding",
            "weekdayBusScheduleTowardMainGate",
            "weekendBusScheduleTowardMainGate",
        ],
    },
    "nanda": {
        "url": "https://affairs.site.nthu.edu.tw/p/412-1165-20979.php?Lang=zh-tw",
        "schedule_images": None,
        "info_vars": ["towardNandaInfo", "towardMainCampusInfo"],
        "schedule_vars": [
            "weekdayBusScheduleTowardNanda",
            "weekendBusScheduleTowardNanda",
            "weekdayBusScheduleTowardMainCampus",
            "weekendBusScheduleTowardMainCampus",
        ],
    },
}

# 公告關鍵字配置
SCHEDULE_IMAGE_KEYWORDS = {
    "main": ["校本部", "校園公車", "時刻表"],
    "nanda": ["南大", "區間車", "時刻表"],
}


class BusInfo(scrapy.Item):
    """公車資訊 Item"""

    type = scrapy.Field()
    route_type = scrapy.Field()
    item_name = scrapy.Field()
    data = scrapy.Field()


class BusesSpider(scrapy.Spider):
    """清華大學公車資訊爬蟲"""

    name = "nthu_buses"
    allowed_domains = ["affairs.site.nthu.edu.tw"]
    custom_settings = {
        "ITEM_PIPELINES": {
            "nthu_scraper.spiders.nthu_buses.BusPipeline": 1,
        },
    }

    async def start(self):
        """初始化並發送請求"""
        self._load_schedule_image_links()
        for bus_type, config in BUS_CONFIG.items():
            yield scrapy.Request(
                url=config["url"],
                callback=self.parse,
                meta={"bus_type": bus_type},
            )

    def _load_schedule_image_links(self):
        """從公告 JSON 載入時刻表圖片連結"""
        announcements = load_json(ANNOUNCEMENTS_JSON_PATH)
        if not announcements:
            self.logger.warning("無法載入公告資料，跳過圖片連結提取")
            return

        for announcement in announcements:
            if (
                announcement.get("department") == "事務組"
                and announcement.get("language") == "zh-tw"
                and announcement.get("title") == "最新公告"
            ):
                self._extract_image_links(announcement.get("articles", []))
                break

    def _extract_image_links(self, articles: List[Dict[str, Any]]):
        """從文章列表中提取圖片連結"""
        for article in articles:
            title = article.get("title", "")
            link = article.get("link", "")

            for bus_type, keywords in SCHEDULE_IMAGE_KEYWORDS.items():
                if all(kw in title for kw in keywords):
                    if BUS_CONFIG[bus_type]["schedule_images"] is None:
                        BUS_CONFIG[bus_type]["schedule_images"] = link
                        self.logger.info(f"找到 {bus_type} 時刻表圖片連結: {link}")

    def parse(self, response):
        """解析公車資訊頁面"""
        bus_type = response.meta["bus_type"]
        config = BUS_CONFIG[bus_type]
        page_text = response.text

        # 解析路線資訊
        for var_name in config["info_vars"]:
            info_data = self._parse_info_variable(var_name, page_text)
            if info_data:
                yield BusInfo(
                    type="info",
                    route_type=bus_type,
                    item_name=var_name,
                    data=info_data,
                )

        # 解析時刻表
        for var_name in config["schedule_vars"]:
            schedule_data = self._parse_schedule_variable(var_name, page_text)
            if schedule_data:
                yield BusInfo(
                    type="schedule",
                    route_type=bus_type,
                    item_name=var_name,
                    data=schedule_data,
                )

        # 請求時刻表圖片
        if config["schedule_images"]:
            yield scrapy.Request(
                url=config["schedule_images"],
                callback=self.parse_images,
                meta={"bus_type": bus_type},
            )

    def _extract_js_value(self, page_text: str, var_name: str) -> Optional[str]:
        pattern = rf"const {re.escape(var_name)}\s*=\s*"
        match = re.search(pattern, page_text)
        if not match:
            self.logger.warning(f"找不到變數: {var_name}")
            return None

        start = match.end()
        length = len(page_text)
        while start < length and page_text[start].isspace():
            start += 1

        if start >= length:
            self.logger.warning(f"變數 {var_name} 沒有內容")
            return None

        opening = page_text[start]
        closing_map = {"{": "}", "[": "]"}
        closing = closing_map.get(opening)
        if not closing:
            self.logger.warning(f"變數 {var_name} 的起始符號不受支援: {opening}")
            return None

        depth = 0
        in_string = False
        string_char = ""
        escape = False

        for idx in range(start, length):
            char = page_text[idx]
            if in_string:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == string_char:
                    in_string = False
                continue

            if char in ('"', "'", "`"):
                in_string = True
                string_char = char
            elif char == opening:
                depth += 1
            elif char == closing:
                depth -= 1
                if depth == 0:
                    return page_text[start : idx + 1]

        self.logger.error(f"找不到變數 {var_name} 的結束符號")
        return None

    def _prepare_literal(self, js_value: str) -> str:
        literal = js_value.strip().rstrip(";")
        literal = literal.replace("\r", " ").replace("\n", " ").replace("\t", " ")
        literal = re.sub(
            r'(?<!["\'])\b([A-Za-z_]\w*)\b\s*:',
            r'"\1":',
            literal,
        )
        literal = re.sub(r'""(\w+)"":', r'"\1":', literal)
        literal = re.sub(r",\s*]", "]", literal)
        literal = re.sub(r",\s*}", "}", literal)
        literal = re.sub(r"\btrue\b", "True", literal, flags=re.IGNORECASE)
        literal = re.sub(r"\bfalse\b", "False", literal, flags=re.IGNORECASE)
        literal = re.sub(r"\bnull\b", "None", literal, flags=re.IGNORECASE)
        return literal

    def _parse_info_variable(
        self, var_name: str, page_text: str
    ) -> Optional[Dict[str, Any]]:
        """
        解析 JavaScript 變數 (物件型態)

        Args:
            var_name: 變數名稱
            page_text: 網頁內容

        Returns:
            解析後的字典資料
        """
        js_obj = self._extract_js_value(page_text, var_name)
        if not js_obj:
            return None

        literal = self._prepare_literal(js_obj)

        try:
            data = ast.literal_eval(literal)
        except (SyntaxError, ValueError) as e:
            self.logger.error(f"解析 {var_name} 失敗: {e}")
            self.logger.debug(f"JSON 內容: {literal[:500]}")
            return None

        # 清理 HTML 標籤
        for key in ["route", "routeEN"]:
            if key in data:
                data[key] = self._strip_html_tags(data[key])

        return data

    def _parse_schedule_variable(
        self, var_name: str, page_text: str
    ) -> Optional[List[Dict[str, Any]]]:
        """
        解析 JavaScript 變數 (陣列型態)

        Args:
            var_name: 變數名稱
            page_text: 網頁內容

        Returns:
            解析後的列表資料
        """
        js_array = self._extract_js_value(page_text, var_name)
        if not js_array:
            return None

        literal = self._prepare_literal(js_array)

        try:
            data = ast.literal_eval(literal)
        except (SyntaxError, ValueError) as e:
            self.logger.error(f"解析 {var_name} 失敗: {e}")
            self.logger.debug(f"JSON 內容: {literal[:500]}")
            return None

        # 標準化欄位名稱並過濾空時間
        standardized_data = []
        for item in data:
            if not item.get("time"):
                continue

            # 標準化欄位名稱
            standardized_item = {
                "time": item.get("time", ""),
                "description": item.get("description", ""),
            }

            # 處理不同的欄位名稱變體
            if "line" in item:
                standardized_item["line"] = item["line"]
            if "depStop" in item or "dep_stop" in item:
                standardized_item["dep_stop"] = item.get(
                    "depStop", item.get("dep_stop", "")
                )

            # 根據路線類型添加標識
            if "line" in standardized_item:
                standardized_item["route"] = "南大區間車"
            else:
                standardized_item["route"] = "校園公車"

            standardized_data.append(standardized_item)

        return standardized_data

    def _strip_html_tags(self, text: str) -> str:
        """移除 HTML 標籤"""
        selector = scrapy.Selector(text=text)
        return " ".join(selector.xpath("//text()").getall())

    def parse_images(self, response):
        """解析圖片頁面並下載圖片"""
        bus_type = response.meta["bus_type"]
        image_links = response.css("div.main div.meditor img::attr(src)").getall()

        if not image_links:
            self.logger.warning(f"在 {bus_type} 頁面找不到圖片")
            return

        image_folder = BUSES_FOLDER / "images"
        image_folder.mkdir(parents=True, exist_ok=True)

        absolute_links = []
        for idx, link in enumerate(image_links):
            abs_link = response.urljoin(link)
            absolute_links.append(abs_link)

            # 下載圖片
            yield scrapy.Request(
                url=abs_link,
                callback=self.save_image,
                meta={
                    "bus_type": bus_type,
                    "index": idx,
                    "image_path": image_folder / f"{bus_type}_{idx}.jpg",
                },
            )

        # 儲存圖片連結列表
        yield BusInfo(
            type="images",
            route_type=bus_type,
            item_name=f"{bus_type}_schedule_images",
            data=absolute_links,
        )

    def save_image(self, response):
        """儲存圖片"""
        image_path = response.meta["image_path"]
        with open(image_path, "wb") as f:
            f.write(response.body)
        self.logger.info(f"成功下載圖片: {image_path.name}")


class BusPipeline:
    """公車資料 Pipeline"""

    def open_spider(self, spider):
        """初始化"""
        BUSES_FOLDER.mkdir(parents=True, exist_ok=True)
        self.bus_data = {}

    def process_item(self, item, spider):
        """處理 Item"""
        if not isinstance(item, BusInfo):
            return item

        item_name = item["item_name"]
        self.bus_data[item_name] = item["data"]

        # 儲存個別檔案
        file_path = BUSES_FOLDER / f"{item_name}.json"
        save_json(item["data"], file_path)
        spider.logger.info(f'儲存 {item["route_type"]}/{item_name} 到 {file_path}')

        return item

    def close_spider(self, spider):
        """儲存合併的資料"""
        save_json(self.bus_data, BUSES_JSON_PATH)
        spider.logger.info(f"成功儲存所有公車資料到 {BUSES_JSON_PATH}")
