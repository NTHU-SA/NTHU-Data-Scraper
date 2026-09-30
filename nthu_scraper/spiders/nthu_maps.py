import scrapy

from nthu_scraper.parsers import ParseError
from nthu_scraper.parsers.maps import parse_map_options
from nthu_scraper.utils.constants import MAPS_FOLDER, MAPS_JSON_PATH
from nthu_scraper.utils.crawl_safety import log_source_failure
from nthu_scraper.utils.file_utils import load_json, save_json
from nthu_scraper.utils.url_utils import normalize_http_url

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
        "ITEM_PIPELINES": {"nthu_scraper.spiders.nthu_maps.MapPipeline": 1},
    }

    async def start(self):
        for map_type, url in MAP_URLS.items():
            yield scrapy.Request(
                normalize_http_url(url),
                meta={"map_type": map_type},
                errback=log_source_failure,
            )

    def parse(self, response):
        """
        解析地圖資訊頁面，提取地圖座標資料。
        """
        map_type = response.meta.get("map_type", "")
        # 比對網址以確認地圖類型
        response_url = response.url.rstrip("/")
        for name, url in MAP_URLS.items():
            if url.rstrip("/") == response_url:
                map_type = name
                break

        if not map_type:
            self.logger.error(f"無法識別的地圖網址: {response.url}")
            return

        try:
            map_data = parse_map_options(response)
        except ParseError as error:
            self.logger.warning("Invalid map source; retaining %s: %s", map_type, error)
            return
        if map_data:
            yield MapItem(map_type=map_type, data=map_data)
        else:
            self.logger.error(f"❎ 未能解析到 {map_type} 的地圖資料")


class MapPipeline:
    """
    Scrapy Pipeline，用於將爬取的 MapItem 儲存為 JSON 檔案。
    """

    def open_spider(self, spider):
        """
        Spider 開啟時執行，建立必要的資料夾。
        """
        MAPS_FOLDER.mkdir(parents=True, exist_ok=True)
        previous = load_json(MAPS_JSON_PATH)
        self.all_map_data = previous if previous is not None else {}
        if not isinstance(self.all_map_data, dict):
            raise ValueError("Expected maps.json to contain an object")
        self.refreshed_types = set()

    def process_item(self, item, spider):
        """
        處理每一個 MapItem，儲存地圖資料到 JSON 檔案。
        """
        if isinstance(item, MapItem):
            item_dict = dict(item)
            map_type = item_dict["map_type"]
            map_data = item_dict["data"]
            if not map_data:
                spider.logger.warning("Empty map refresh; retaining %s", map_type)
                return item
            map_data = dict(sorted(map_data.items()))  # 對地點名稱排序

            file_path = MAPS_FOLDER / f"{map_type}.json"
            save_json(map_data, file_path)
            self.all_map_data[map_type] = map_data
            self.refreshed_types.add(map_type)
            spider.logger.info(f'✅ 成功儲存 {map_type} 的地圖座標資料至 "{file_path}"')
        return item

    def close_spider(self, spider):
        """
        Spider 關閉時執行，將所有地圖資料合併儲存為 JSON 檔案。
        """
        # Sort keys before saving
        sorted_data = dict(sorted(self.all_map_data.items()))
        for map_type in MAP_URLS.keys() - self.refreshed_types:
            spider.logger.warning(
                "Map type not refreshed; retaining baseline if present: %s", map_type
            )
        save_json(sorted_data, MAPS_JSON_PATH)
        spider.logger.info(f"✅ 成功儲存地圖資料至 {MAPS_JSON_PATH}")
