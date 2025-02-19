import json
import os
import re
from pathlib import Path
from typing import Any, List

import scrapy

# --- 全域參數設定 ---
DATA_FOLDER = Path(os.getenv("DATA_FOLDER", "temp"))
OUTPUT_PATH = DATA_FOLDER / "dining.json"

# 預先編譯正規表達式（改善效能與可讀性）
DINING_REGEX = re.compile(r"const restaurantsData = (\[.*?)(?:\s+renderTabs)", re.S)


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
    start_urls = ["https://ddfm.site.nthu.edu.tw/p/404-1494-256455.php?Lang=zh-tw"]
    custom_settings = {
        "LOG_LEVEL": "INFO",
        "ITEM_PIPELINES": {"nthu_scraper.spiders.nthu_dining.JsonDiningPipeline": 1},
    }

    def parse(self, response):
        """
        解析餐廳資訊頁面，提取餐廳資料。
        """
        res_text = response.text
        dining_data = self.parse_html(res_text)

        if dining_data:
            yield DiningItem(data=dining_data)
        else:
            self.logger.error("❎ 未能解析到任何餐廳資料")

    def parse_html(self, res_text: str) -> List[Any]:
        """
        解析網頁原始碼，提取餐廳資料（JSON 格式）。
        若無法找到資料則回傳空列表。

        Args:
            res_text (str): 原始 HTML 內容

        Returns:
            List[Any]: 解析出的餐廳資料列表
        """
        match = DINING_REGEX.search(res_text)
        if match is None:
            self.logger.error("❎ 找不到餐廳資料的內容")
            return []

        dining_data = match.group(1)
        # 將單引號換成雙引號，並移除換行符號
        dining_data = dining_data.replace("'", '"').replace("\n", "")
        # 移除多餘的逗號，例如 "..., ]" 變成 "...]"
        dining_data = re.sub(r",[ ]+?\]", "]", dining_data)
        try:
            data = json.loads(dining_data)
            return data
        except json.JSONDecodeError as e:
            self.logger.error(f"❎ JSON 解碼錯誤: {e}")
            return []


class JsonDiningPipeline:
    """
    Scrapy Pipeline，用於將爬取的 DiningItem 儲存為 JSON 檔案。
    """

    def open_spider(self, spider):
        """
        Spider 開啟時執行，建立必要的資料夾。
        """
        DATA_FOLDER.mkdir(parents=True, exist_ok=True)

    def process_item(self, item, spider):
        """
        處理每一個 DiningItem，儲存餐廳資料到 JSON 檔案。
        """
        if isinstance(item, DiningItem):
            with OUTPUT_PATH.open("w", encoding="utf-8") as f:
                json.dump(item["data"], f, ensure_ascii=False, indent=4)
            spider.logger.info(f'✅ 成功儲存餐廳資料至 "{OUTPUT_PATH}"')
        return item
