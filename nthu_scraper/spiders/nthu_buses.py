import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import scrapy

# --- 全域參數設定 ---
DATA_FOLDER = Path(os.getenv("DATA_FOLDER", "temp"))
OUTPUT_FOLDER = DATA_FOLDER / "buses"
COMBINED_JSON_FILE = DATA_FOLDER / "buses.json"
IMAGE_FOLDER = OUTPUT_FOLDER / "images"

BUS_URL: Dict[str, Dict[str, Any]] = {
    "校本部公車": {
        "url": "https://affairs.site.nthu.edu.tw/p/412-1165-20978.php?Lang=zh-tw",
        "info": ["towardTSMCBuildingInfo", "towardMainGateInfo"],
        "schedule": [
            "weekdayBusScheduleTowardTSMCBuilding",  # 往台積館平日時刻表
            "weekendBusScheduleTowardTSMCBuilding",  # 往台積館假日時刻表
            "weekdayBusScheduleTowardMainGate",  # 往校門口平日時刻表
            "weekendBusScheduleTowardMainGate",  # 往校門口假日時刻表
        ],
    },
    "南大區間車": {
        "url": "https://affairs.site.nthu.edu.tw/p/412-1165-20979.php?Lang=zh-tw",
        "info": ["towardMainCampusInfo", "towardSouthCampusInfo"],
        "schedule": [
            "weekdayBusScheduleTowardMainCampus",  # 往校本部平日時刻表
            "weekendBusScheduleTowardMainCampus",  # 往校本部假日時刻表
            "weekdayBusScheduleTowardSouthCampus",  # 往南大平日時刻表
            "weekendBusScheduleTowardSouthCampus",  # 往南大假日時刻表
        ],
    },
}

# 公告頁面關鍵字設定
BUS_ANNOUCEMENT_URL = "https://affairs.site.nthu.edu.tw/p/403-1165-127-1.php"
MAIN_ROUTE_IMAGE_KEYWORD = ["校本部", "校園公車"]
NANDA_ROUTE_IMAGE_KEYWORD = ["南大", "區間車"]
SCHEDULE_IMAGE_KEYWORD = ["時刻表"]

API_URL = "https://api.nthusa.tw/scrapers/rpage/announcements/"


# --- 資料結構定義 ---
class BusInfo(scrapy.Item):
    """
    公車資訊資料結構。
    """

    type = scrapy.Field()  # 資訊類型 (info, schedule, images)
    route_type = scrapy.Field()  # 路線類型 (校本部公車, 南大區間車)
    item_name = scrapy.Field()  # 資訊項目名稱 (例如: towardTSMCBuildingInfo)
    data = scrapy.Field()  # 資訊內容 (字典或列表)


class NTHUBusSpider(scrapy.Spider):
    """
    清華大學公車資訊爬蟲。
    """

    name = "nthu_buses"
    allowed_domains = ["affairs.site.nthu.edu.tw", "api.nthusa.tw"]
    start_urls = [BUS_URL["校本部公車"]["url"], BUS_URL["南大區間車"]["url"]]
    custom_settings = {
        "LOG_LEVEL": "INFO",
        "ITEM_PIPELINES": {"nthu_scraper.spiders.nthu_buses.JsonBusPipeline": 1},
    }

    def parse(self, response):
        """
        解析公車資訊頁面，抓取公車資訊與時刻表。

        Args:
            response (scrapy.http.Response): 下載器返回的回應物件。

        Yields:
            scrapy.Request: 針對公告頁面發送請求，以抓取圖片連結。
            BusInfo: 包含公車資訊的 Item 物件。
        """
        bus_type = ""
        for name, data in BUS_URL.items():
            if data["url"] == response.url:
                bus_type = name
                bus_data = data
                break

        if not bus_type:
            self.logger.error(f"無法識別的網址: {response.url}")
            return

        res_text = response.text

        # 解析 info 資料
        for item_name in bus_data["info"]:
            info_data = self.parse_campus_info(item_name, res_text)
            if info_data:
                bus_info_item = BusInfo(
                    type="info",
                    route_type=bus_type,
                    item_name=item_name,
                    data=info_data,
                )
                yield bus_info_item

        # 解析 schedule 資料
        for item_name in bus_data["schedule"]:
            schedule_data = self.parse_bus_schedule(item_name, res_text)
            if schedule_data:
                bus_info_item = BusInfo(
                    type="schedule",
                    route_type=bus_type,
                    item_name=item_name,
                    data=schedule_data,
                )
                yield bus_info_item

        # 發送請求抓取圖片
        yield scrapy.Request(
            url=f"{API_URL}{BUS_ANNOUCEMENT_URL}",
            callback=self.parse_announcement_page,
            meta={"bus_type": bus_type},
        )

    def parse_campus_info(
        self, variable_string: str, res_text: str
    ) -> Optional[Dict[str, Any]]:
        """
        從網頁原始碼中解析指定變數（物件型資料），並處理部分欄位中 HTML 標籤。

        Args:
            variable_string (str): 要解析的變數名稱
            res_text (str): 網頁原始碼內容

        Returns:
            Optional[Dict[str, Any]]: 解析後的資料，若解析失敗則回傳 None
        """
        regex_pattern = r"const " + re.escape(variable_string) + r" = (\{.*?\})"
        data_match = re.search(regex_pattern, res_text, re.S)
        if not data_match:
            self.logger.error(f"❎ 找不到變數 {variable_string} 的資料")
            return None

        data = data_match.group(1)
        # 使用替換技巧處理引號問題：先將單引號暫存為其他符號，再統一換成雙引號
        data = data.replace("'", "|")
        data = data.replace('"', '\\"')
        data = data.replace("|", '"')
        data = data.replace("\n", "")
        data = data.replace("direction", '"direction"')
        data = data.replace("duration", '"duration"')
        data = data.replace("route", '"route"', 1)  # 僅替換第一個出現的 route
        data = data.replace("routeEN", '"routeEN"')

        try:
            data_dict = json.loads(data)
        except json.JSONDecodeError as e:
            self.logger.error(f"❎ 解析 {variable_string} JSON 失敗: {e}")
            return None

        # 使用 Scrapy Selector 移除 route 與 routeEN 中的 <span> 標籤
        for key in ["route", "routeEN"]:
            if key in data_dict and (
                "<span" in data_dict[key] or "</span>" in data_dict[key]
            ):
                data_dict[key] = (
                    scrapy.Selector(text=data_dict[key]).xpath("//text()").getall()
                )
                data_dict[key] = " ".join(data_dict[key])  # 將 text list 合併成字串
        return data_dict

    def parse_bus_schedule(
        self, variable_string: str, res_text: str
    ) -> Optional[List[Dict[str, Any]]]:
        """
        從網頁原始碼中解析指定變數（陣列型資料），並處理部分欄位資料。

        Args:
            variable_string (str): 要解析的變數名稱
            res_text (str): 網頁原始碼內容

        Returns:
            Optional[List[Dict[str, Any]]]: 解析後的陣列資料，若解析失敗則回傳 None
        """
        regex_pattern = r"const " + re.escape(variable_string) + r" = (\[.*?\])"
        data_match = re.search(regex_pattern, res_text, re.S)
        if not data_match:
            self.logger.error(f"❎ 找不到變數 {variable_string} 的資料")
            return None

        data = data_match.group(1)
        data = data.replace("'", '"')
        data = data.replace("\n", "")
        data = data.replace("time", '"time"')
        data = data.replace("description", '"description"')
        data = data.replace("depStop", '"dep_stop"')
        data = data.replace("line", '"line"')
        data = re.sub(r",[ ]+?\]", "]", data)  # 移除多餘的逗號

        try:
            data_list = json.loads(data)
        except json.JSONDecodeError as e:
            self.logger.error(f"解析 {variable_string} JSON 失敗: {e}")
            return None

        # 移除 time 欄位為空的項目
        data_list = [item for item in data_list if item.get("time", "") != ""]

        # 根據第一筆資料判斷路線屬性
        route_str = "校園公車" if data_list and "line" in data_list[0] else "南大區間車"
        for item in data_list:
            item["route"] = route_str
        return data_list

    def parse_announcement_page(self, response):
        """
        解析公告頁面，抓取圖片連結並下載。

        Args:
            response (scrapy.http.Response): 公告頁面回應物件。

        Yields:
            BusInfo: 包含圖片資訊的 Item 物件。
        """
        bus_type = response.meta["bus_type"]
        announcements = json.loads(response.text)
        announcement_links = {"main": "", "nanda": ""}
        for item in announcements:
            title = item.get("title", "")
            # 先判斷是否包含時刻表關鍵字
            if not self.check_keyword_in_title(title, SCHEDULE_IMAGE_KEYWORD):
                continue
            # 判斷校本部公車
            if (
                self.check_keyword_in_title(title, MAIN_ROUTE_IMAGE_KEYWORD)
                and not announcement_links["main"]
            ):
                announcement_links["main"] = item.get("link", "")
            # 判斷南大區間車
            if (
                self.check_keyword_in_title(title, NANDA_ROUTE_IMAGE_KEYWORD)
                and not announcement_links["nanda"]
            ):
                announcement_links["nanda"] = item.get("link", "")
        self.logger.info("✅ 成功抓取含有公車圖片的公告")
        self.logger.debug(announcement_links)

        for key, announcement_url in announcement_links.items():
            if announcement_url:  # 避免空 URL 造成錯誤
                yield scrapy.Request(
                    url=announcement_url,
                    callback=self.parse_image_page,
                    meta={"bus_type": bus_type, "image_type": key},
                )

    def parse_image_page(self, response):
        """
        解析圖片公告頁面，提取圖片連結並產生 BusInfo Item。
        ...
        """
        bus_type = response.meta["bus_type"]
        image_type = response.meta["image_type"]
        image_links = response.css("div.main div.meditor img::attr(src)").getall()
        if not image_links:
            self.logger.warning(f"❎ 在 {image_type} 公告中找不到圖片。")
            return

        absolute_image_links = []
        for index, link in enumerate(image_links):
            absolute_link = response.urljoin(link)  # 使用 urljoin 確保連結為絕對路徑
            absolute_image_links.append(absolute_link)
            image_path = IMAGE_FOLDER / f"{image_type}_{index}.jpg"
            image_path.parent.mkdir(parents=True, exist_ok=True)  # 確保資料夾存在

            # 使用 scrapy.Request 發送圖片下載請求，並處理回應
            yield scrapy.Request(
                url=absolute_link,
                meta={
                    "image_path": image_path,
                    "image_type": image_type,
                    "index": index,
                },
                callback=self.save_image,  # 指定 callback 函式來處理下載完成的回應
            )

        bus_info_item = BusInfo(
            type="images",
            route_type=bus_type,
            item_name=f"{image_type}_images",
            data=absolute_image_links,
        )
        yield bus_info_item

    def save_image(self, response):
        """
        Scrapy callback 函式，用於儲存下載的圖片。
        """
        image_path = response.meta["image_path"]
        image_type = response.meta["image_type"]
        index = response.meta["index"]

        with open(image_path, "wb") as f:
            f.write(response.body)
        self.logger.info(
            f"✅ 成功下載 {image_type} 圖片 {index}: {response.url} -> {image_path}"
        )

    def check_keyword_in_title(self, title: str, keywords: List[str]) -> bool:
        """
        檢查標題是否包含關鍵字列表中的任一關鍵字。

        Args:
            title (str): 要檢查的標題
            keywords (List[str]): 關鍵字列表

        Returns:
            bool: 若標題包含任一關鍵字則返回 True，否則返回 False
        """
        for keyword in keywords:
            if keyword in title:
                return True
        return False


class JsonBusPipeline:
    """
    Scrapy Pipeline，用於將爬取的 BusInfo Item 儲存為 JSON 檔案。
    """

    def open_spider(self, spider):
        """
        Spider 開啟時執行，建立必要的資料夾。
        """
        OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)
        self.bus_data = {}

    def process_item(self, item, spider):
        """
        處理每一個 BusInfo Item，儲存公車資訊到 JSON 檔案。
        """
        if not isinstance(item, BusInfo):
            return item  # 如果不是 BusInfo Item 則直接放行

        item_dict = dict(item)  # 將 Item 轉換成字典方便處理
        self.bus_data[item_dict["item_name"]] = item_dict["data"]

        file_path = OUTPUT_FOLDER / f"{item_dict["item_name"]}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(item_dict["data"], f, ensure_ascii=False, indent=4)

        spider.logger.info(
            f'✅ 成功儲存{item_dict["route_type"]}的資料至 "{file_path}"'
        )
        return item

    def close_spider(self, spider):
        """
        Spider 關閉時執行，將所有公車資料合併儲存為 JSON 檔案。
        """
        with open(COMBINED_JSON_FILE, "w", encoding="utf-8") as f:
            json.dump(self.bus_data, f, ensure_ascii=False, indent=4, sort_keys=True)
        spider.logger.info(f'✅ 成功儲存公車資料至 "{COMBINED_JSON_FILE}"')
