import json
from pathlib import Path
from typing import Dict

import scrapy

from nthu_scraper.utils.constants import DATA_FOLDER
from nthu_scraper.utils.file_utils import save_json

# --- 全域參數設定 ---
OUTPUT_PATH = DATA_FOLDER / "maps"
COMBINED_JSON_FILE = DATA_FOLDER / "maps.json"

MAP_URLS = {
    "MainZH": "https://campusmap.cc.nthu.edu.tw/",
    "MainEN": "https://campusmap.cc.nthu.edu.tw/en",
    "NandaZH": "https://campusmap.cc.nthu.edu.tw/sd",
    "NandaEN": "https://campusmap.cc.nthu.edu.tw/sden",
}


# --- 資料結構定義 ---
class MapItem(scrapy.Item):
    """
    地圖資料 Item
    """

    map_type = scrapy.Field()  # 地圖類型 (MainZH, MainEN, NandaZH, NandaEN)
    data = scrapy.Field()


class MapSpider(scrapy.Spider):
    """
    清華大學地圖資訊爬蟲
    """

    name = "nthu_maps"
    allowed_domains = ["campusmap.cc.nthu.edu.tw"]
    start_urls = list(MAP_URLS.values())  # 從 MAP_URLS 取值作為起始網址
    custom_settings = {
        "ITEM_PIPELINES": {"nthu_scraper.spiders.nthu_maps.JsonMapPipeline": 1},
    }

    def parse(self, response):
        """
        解析地圖資訊頁面，提取地圖座標資料。
        """
        map_type = ""
        # 比對網址以確認地圖類型
        response_url = response.url.rstrip("/")
        for name, url in MAP_URLS.items():
            if url.rstrip("/") == response_url:
                map_type = name
                break

        if not map_type:
            self.logger.error(f"無法識別的地圖網址: {response.url}")
            return

        map_data = self.parse_html(
            response
        )  # Changed argument from response.text to response
        if map_data:
            yield MapItem(map_type=map_type, data=map_data)
        else:
            self.logger.error(f"❎ 未能解析到 {map_type} 的地圖資料")

    def parse_html(self, response) -> Dict[str, Dict[str, str]]:
        """
        解析 HTML 並提取地圖座標資料，使用 Scrapy selectors

        Args:
            response (scrapy.http.Response): Scrapy response object

        Returns:
            Dict[str, Dict[str, str]]: 以地點名稱為 key，經緯度資料（latitude, longitude）為 value 的字典
        """
        options = response.css("option")
        map_data = {}
        for option in options:
            value = option.xpath("@value").get()
            if not value:
                continue
            coords = [coord.strip() for coord in value.split(",")]
            if len(coords) == 2:
                location = {"latitude": coords[0], "longitude": coords[1]}
                location_name = option.xpath("normalize-space(text())").get()
                map_data[location_name] = location
        return map_data


class JsonMapPipeline:
    """
    Scrapy Pipeline，用於將爬取的 MapItem 儲存為 JSON 檔案。
    """

    def open_spider(self, spider):
        """
        Spider 開啟時執行，建立必要的資料夾。
        """
        OUTPUT_PATH.mkdir(parents=True, exist_ok=True)
        self.all_map_data = {}

    def process_item(self, item, spider):
        """
        處理每一個 MapItem，儲存地圖資料到 JSON 檔案。
        """
        if isinstance(item, MapItem):
            item_dict = dict(item)
            map_type = item_dict["map_type"]
            map_data = item_dict["data"]
            map_data = dict(sorted(map_data.items()))  # 對地點名稱排序

            self.all_map_data[map_type] = map_data  # 收集所有地圖資料

            file_path = OUTPUT_PATH / f"{map_type}.json"
            if save_json(map_data, file_path):
                spider.logger.info(
                    f'✅ 成功儲存 {map_type} 的地圖座標資料至 "{file_path}"'
                )
            else:
                spider.logger.error(f"❌ 儲存檔案 {file_path} 失敗")
        return item

    def close_spider(self, spider):
        """
        Spider 關閉時執行，將所有地圖資料合併儲存為 JSON 檔案。
        """
        # Sort keys before saving
        sorted_data = dict(sorted(self.all_map_data.items()))
        if save_json(sorted_data, COMBINED_JSON_FILE):
            spider.logger.info(f"✅ 成功儲存地圖資料至 {COMBINED_JSON_FILE}")
        else:
            spider.logger.error(f"❌ 儲存地圖資料失敗 {COMBINED_JSON_FILE}")
