"""清華大學公車資訊爬蟲"""

from types import MappingProxyType
from typing import Any

import scrapy

from nthu_scraper.parsers import ParseError
from nthu_scraper.parsers.buses import parse_info_variable, parse_schedule_variable
from nthu_scraper.utils.constants import (
    ANNOUNCEMENTS_JSON_PATH,
    BUSES_FOLDER,
    BUSES_JSON_PATH,
)
from nthu_scraper.utils.crawl_safety import log_source_failure
from nthu_scraper.utils.file_utils import load_json, save_json
from nthu_scraper.utils.url_utils import InvalidHttpUrl, normalize_http_url

# 公車路線配置
BUS_CONFIG = MappingProxyType(
    {
        "main": MappingProxyType(
            {
                "url": "https://affairs.site.nthu.edu.tw/p/412-1165-20978.php?Lang=zh-tw",
                "info_vars": ("towardTSMCBuildingInfo", "towardMainGateInfo"),
                "schedule_vars": (
                    "weekdayBusScheduleTowardTSMCBuilding",
                    "weekendBusScheduleTowardTSMCBuilding",
                    "weekdayBusScheduleTowardMainGate",
                    "weekendBusScheduleTowardMainGate",
                ),
            }
        ),
        "nanda": MappingProxyType(
            {
                "url": "https://affairs.site.nthu.edu.tw/p/412-1165-20979.php?Lang=zh-tw",
                "info_vars": ("towardNandaInfo", "towardMainCampusInfo"),
                "schedule_vars": (
                    "weekdayBusScheduleTowardNanda",
                    "weekendBusScheduleTowardNanda",
                    "weekdayBusScheduleTowardMainCampus",
                    "weekendBusScheduleTowardMainCampus",
                ),
            }
        ),
    }
)

# 公告關鍵字配置
SCHEDULE_IMAGE_KEYWORDS = {
    "main": ["校園公車", "時刻表"],
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.schedule_image_urls: dict[str, str] = {}

    async def start(self):
        """初始化並發送請求"""
        self._load_schedule_image_links()
        for bus_type, config in BUS_CONFIG.items():
            yield scrapy.Request(
                url=normalize_http_url(config["url"]),
                callback=self.parse,
                errback=log_source_failure,
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
                announcement.get("department") == "總務處事務組"
                and announcement.get("language") == "zh-tw"
                and announcement.get("title") == "校園公車暨巡迴公車公告"
            ):
                self._extract_image_links(announcement.get("articles", []))
                break

    def _extract_image_links(self, articles: list[dict[str, Any]]):
        """從文章列表中提取圖片連結"""
        for article in articles:
            title = article.get("title", "")
            link = article.get("link", "")

            for bus_type, keywords in SCHEDULE_IMAGE_KEYWORDS.items():
                if all(kw in title for kw in keywords):
                    if bus_type not in self.schedule_image_urls:
                        try:
                            normalized = normalize_http_url(link)
                        except InvalidHttpUrl as error:
                            self.logger.warning(
                                "Skipping invalid bus announcement URL %r: %s",
                                link,
                                error,
                            )
                            continue
                        self.schedule_image_urls[bus_type] = normalized
                        self.logger.info(
                            f"找到 {bus_type} 時刻表圖片連結: {normalized}"
                        )

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
        if self.schedule_image_urls.get(bus_type):
            yield scrapy.Request(
                url=self.schedule_image_urls[bus_type],
                callback=self.parse_images,
                errback=log_source_failure,
                meta={"bus_type": bus_type},
            )

    def _parse_info_variable(
        self, var_name: str, page_text: str
    ) -> dict[str, Any] | None:
        try:
            return parse_info_variable(var_name, page_text)
        except ParseError as error:
            self.logger.warning(
                "Invalid bus component; retaining %s: %s", var_name, error
            )
            return None

    def _parse_schedule_variable(
        self, var_name: str, page_text: str
    ) -> list[dict[str, Any]] | None:
        try:
            return parse_schedule_variable(var_name, page_text)
        except ParseError as error:
            self.logger.warning(
                "Invalid bus component; retaining %s: %s", var_name, error
            )
            return None

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
            try:
                abs_link = normalize_http_url(link, base_url=response.url)
            except InvalidHttpUrl as error:
                self.logger.warning(
                    "Skipping invalid bus image URL: source=%s link=%r: %s",
                    response.url,
                    link,
                    error,
                )
                continue
            absolute_links.append(abs_link)

            # 下載圖片
            yield scrapy.Request(
                url=abs_link,
                callback=self.save_image,
                errback=log_source_failure,
                meta={
                    "bus_type": bus_type,
                    "index": idx,
                    "image_path": image_folder / f"{bus_type}_{idx}.jpg",
                },
            )

        # 儲存圖片連結列表
        if absolute_links:
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
        previous = load_json(BUSES_JSON_PATH)
        self.bus_data = previous if previous is not None else {}
        if not isinstance(self.bus_data, dict):
            raise ValueError("Expected buses.json to contain an object")
        self.refreshed_keys = set()

    def process_item(self, item, spider):
        """處理 Item"""
        if not isinstance(item, BusInfo):
            return item

        item_name = item["item_name"]
        if not item["data"]:
            spider.logger.warning("Empty bus component; retaining %s", item_name)
            return item

        # 儲存個別檔案
        file_path = BUSES_FOLDER / f"{item_name}.json"
        save_json(item["data"], file_path)
        self.bus_data[item_name] = item["data"]
        self.refreshed_keys.add(item_name)
        spider.logger.info(f"儲存 {item['route_type']}/{item_name} 到 {file_path}")

        return item

    def close_spider(self, spider):
        """儲存合併的資料"""
        for key in self.bus_data.keys() - self.refreshed_keys:
            spider.logger.warning("Retaining previous bus component: %s", key)
        save_json(self.bus_data, BUSES_JSON_PATH)
        spider.logger.info(f"成功儲存所有公車資料到 {BUSES_JSON_PATH}")
