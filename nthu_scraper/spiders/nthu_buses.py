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
    "main": {
        "url": "https://affairs.site.nthu.edu.tw/p/412-1165-20978.php?Lang=zh-tw",
        "schedule_images": None,  # 初始為 None，後續會從公告 JSON 取得
        "info": ["towardTSMCBuildingInfo", "towardMainGateInfo"],
        "schedule": [
            "weekdayBusScheduleTowardTSMCBuilding",  # 往台積館平日時刻表
            "weekendBusScheduleTowardTSMCBuilding",  # 往台積館假日時刻表
            "weekdayBusScheduleTowardMainGate",  # 往校門口平日時刻表
            "weekendBusScheduleTowardMainGate",  # 往校門口假日時刻表
        ],
    },
    "nanda": {
        "url": "https://affairs.site.nthu.edu.tw/p/412-1165-20979.php?Lang=zh-tw",
        "schedule_images": None,  # 初始為 None，後續會從公告 JSON 取得
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
MAIN_ROUTE_IMAGE_KEYWORD = ["校本部", "校園公車"]
NANDA_ROUTE_IMAGE_KEYWORD = ["南大", "區間車"]
SCHEDULE_IMAGE_KEYWORD = ["時刻表"]

ANNOUNCEMENT_JSON_PATH = DATA_FOLDER / "announcements.json"


def load_announcement_json(file_path: Path) -> Optional[Dict[str, Any]]:
    """
    載入公告 JSON 檔案。

    Args:
        file_path (Path): 公告 JSON 檔案路徑。

    Returns:
        Optional[Dict[str, Any]]: 若成功載入則返回公告 JSON 資料，否則返回 None。
    """
    if not file_path.exists():
        print(
            f"警告：公告 JSON 檔案 '{file_path}' 不存在。請確保已生成公告 JSON 檔案。"
        )
        return None
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            # 尋找符合條件的公告資料 (假設公告 JSON 結構是列表)
            for item in data:
                if (
                    item.get("department") == "事務組"
                    and item.get("language") == "zh-tw"
                    and item.get("title") == "最新公告"
                ):
                    return item
            return None  # 找不到符合條件的公告資料
    except json.JSONDecodeError as e:
        print(f"錯誤：公告 JSON 檔案解析失敗 '{file_path}': {e}")
        return None


def check_keyword_in_title(title: str, keywords: List[str]) -> bool:
    """
    檢查標題是否包含關鍵字列表中的任一關鍵字。

    Args:
        title (str): 要檢查的標題。
        keywords (List[str]): 關鍵字列表。

    Returns:
        bool: 若標題包含任一關鍵字則返回 True，否則返回 False。
    """
    for keyword in keywords:
        if keyword in title:
            return True
    return False


def get_schedule_image_links(announcements: Dict[str, Any]) -> None:
    """
    從公告資料中提取校本部公車和南大區間車的時刻表圖片公告連結，並更新 BUS_URL 全域變數。

    Args:
        announcements (Dict[str, Any]): 公告 JSON 資料。
    """
    if not announcements or "articles" not in announcements:
        print("警告：公告資料不完整或無文章列表，無法提取時刻表圖片連結。")
        return

    articles = announcements["articles"]
    for article in articles:
        if not check_keyword_in_title(article["title"], SCHEDULE_IMAGE_KEYWORD):
            continue

        # 僅在連結尚未設定時更新校本部公車連結
        if BUS_URL["main"]["schedule_images"] is None and check_keyword_in_title(
            article["title"], MAIN_ROUTE_IMAGE_KEYWORD
        ):
            BUS_URL["main"]["schedule_images"] = article["link"]
            print(f"✅ 校本部公車時刻表連結: {article['link']}")

        # 僅在連結尚未設定時更新南大區間車連結
        if BUS_URL["nanda"]["schedule_images"] is None and check_keyword_in_title(
            article["title"], NANDA_ROUTE_IMAGE_KEYWORD
        ):
            BUS_URL["nanda"]["schedule_images"] = article["link"]
            print(f"✅ 南大區間車時刻表連結: {article['link']}")

        # 如果兩種連結都已設定，可以提前結束迴圈
        if (
            BUS_URL["main"]["schedule_images"] is not None
            and BUS_URL["nanda"]["schedule_images"] is not None
        ):
            break


# --- 資料結構定義 ---
class BusInfo(scrapy.Item):
    """
    公車資訊資料結構。

    Attributes:
        type (scrapy.Field): 資訊類型 (info, schedule, images)。
        route_type (scrapy.Field): 路線類型 (校本部公車, 南大區間車)。
        item_name (scrapy.Field): 資訊項目名稱 (例如: towardTSMCBuildingInfo)。
        data (scrapy.Field): 資訊內容 (字典或列表)。
    """

    type = scrapy.Field()  # 資訊類型 (info, schedule, images)
    route_type = scrapy.Field()  # 路線類型 (校本部公車, 南大區間車)
    item_name = scrapy.Field()  # 資訊項目名稱 (例如: towardTSMCBuildingInfo)
    data = scrapy.Field()  # 資訊內容 (字典或列表)


class BusesSpider(scrapy.Spider):
    """
    清華大學公車資訊爬蟲。

    負責爬取校本部公車和南大區間車的資訊，包含路線資訊、時刻表文字資料和時刻表圖片。

    Attributes:
        name (str): 爬蟲名稱，用於 Scrapy 框架識別。
        allowed_domains (List[str]): 允許爬取的網域名稱列表。
        start_urls (List[str]): 爬蟲起始 URL 列表，包含校本部公車和南大區間車的資訊頁面。
        custom_settings (Dict[str, Any]): 爬蟲自訂設定，指定使用的 Item Pipeline。
    """

    name = "nthu_buses"
    allowed_domains = ["affairs.site.nthu.edu.tw"]
    start_urls = [BUS_URL["main"]["url"], BUS_URL["nanda"]["url"]]
    custom_settings = {
        "ITEM_PIPELINES": {"nthu_scraper.spiders.nthu_buses.JsonBusPipeline": 1},
    }

    def start_requests(self):
        """
        覆寫 start_requests 方法，在爬取公車資訊頁面之前先處理公告 JSON 和時刻表圖片連結。

        Yields:
            scrapy.Request: 對每個公車資訊頁面發送請求。
        """
        announcement_data = load_announcement_json(ANNOUNCEMENT_JSON_PATH)
        if announcement_data:
            get_schedule_image_links(announcement_data)
            for bus_name, bus_config in BUS_URL.items():
                yield scrapy.Request(
                    url=bus_config["url"],
                    callback=self.parse,
                    meta={"bus_type": bus_name},  # 傳遞 bus_type 到 parse 方法
                )
        else:
            self.logger.error("❌ 無法載入公告 JSON 資料，請檢查公告 JSON 檔案。")
            # 如果無法載入公告，仍然爬取基本的公車資訊和時刻表文字 (不包含圖片)
            for bus_name, bus_config in BUS_URL.items():
                yield scrapy.Request(
                    url=bus_config["url"],
                    callback=self.parse,
                    meta={"bus_type": bus_name},  # 傳遞 bus_type 到 parse 方法
                )

    def parse(self, response):
        """
        解析公車資訊頁面，抓取公車資訊、時刻表文字資料和請求時刻表圖片公告頁面。

        Args:
            response (scrapy.http.Response): 下載器返回的回應物件。

        Yields:
            BusInfo: 包含公車資訊的 Item 物件。
            scrapy.Request: 針對時刻表圖片公告頁面發送請求。
        """
        bus_type = response.meta["bus_type"]
        bus_data = BUS_URL[bus_type]

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

        # 請求時刻表圖片公告頁面
        if bus_data["schedule_images"]:
            yield scrapy.Request(
                url=bus_data["schedule_images"],
                callback=self.parse_image_page,
                meta={"bus_type": bus_type},  # 傳遞 bus_type 到圖片頁面解析函式
            )
        else:
            self.logger.warning(f"⚠️  {bus_type} 缺少時刻表圖片公告連結，跳過圖片抓取。")

    def parse_campus_info(
        self, variable_string: str, res_text: str
    ) -> Optional[Dict[str, Any]]:
        """
        從網頁原始碼中解析指定變數（物件型資料），並處理部分欄位中 HTML 標籤。

        Args:
            variable_string (str): 要解析的變數名稱。
            res_text (str): 網頁原始碼內容。

        Returns:
            Optional[Dict[str, Any]]: 解析後的資料，若解析失敗則回傳 None。
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
            variable_string (str): 要解析的變數名稱。
            res_text (str): 網頁原始碼內容。

        Returns:
            Optional[List[Dict[str, Any]]]: 解析後的陣列資料，若解析失敗則回傳 None。
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

    def parse_image_page(self, response):
        """
        解析圖片公告頁面，提取圖片連結並產生 BusInfo Item。

        Args:
            response (scrapy.http.Response): 圖片公告頁面回應物件。

        Yields:
            BusInfo: 包含圖片資訊的 Item 物件。
            scrapy.Request: 發送圖片下載請求。
        """
        bus_type = response.meta["bus_type"]
        image_links = response.css("div.main div.meditor img::attr(src)").getall()
        if not image_links:
            self.logger.warning(f"❎ 在 {bus_type} 公車公告中找不到圖片。")
            return

        absolute_image_links = []
        for index, link in enumerate(image_links):
            absolute_link = response.urljoin(link)  # 使用 urljoin 確保連結為絕對路徑
            absolute_image_links.append(absolute_link)
            image_path = IMAGE_FOLDER / f"{bus_type}_{index}.jpg"
            image_path.parent.mkdir(parents=True, exist_ok=True)  # 確保資料夾存在

            # 使用 scrapy.Request 發送圖片下載請求，並處理回應
            yield scrapy.Request(
                url=absolute_link,
                meta={
                    "image_path": image_path,
                    "index": index,
                    "bus_type": bus_type,  # 傳遞 bus_type 到 save_image
                },
                callback=self.save_image,  # 指定 callback 函式來處理下載完成的回應
            )

        bus_info_item = BusInfo(
            type="images",
            route_type=bus_type,
            item_name=f"{bus_type}_schedule_images",
            data=absolute_image_links,
        )
        yield bus_info_item

    def save_image(self, response):
        """
        Scrapy callback 函式，用於儲存下載的圖片。

        Args:
            response (scrapy.http.Response): 圖片下載回應物件。

        """
        image_path = response.meta["image_path"]
        index = response.meta["index"]
        bus_type = response.meta["bus_type"]

        with open(image_path, "wb") as f:
            f.write(response.body)
        self.logger.info(
            f"✅ 成功下載 {bus_type} 圖片 {index}: {response.url} -> {image_path}"
        )


class JsonBusPipeline:
    """
    Scrapy Pipeline，用於將爬取的 BusInfo Item 儲存為 JSON 檔案。

    負責將不同類型的公車資訊 (info, schedule, images) 分別儲存成 JSON 檔案，
    並在爬蟲結束時將所有資料合併儲存為一個總 JSON 檔案。

    Attributes:
        bus_data (Dict[str, Any]): 儲存所有爬取到的公車資料的字典。
    """

    def open_spider(self, spider):
        """
        Spider 開啟時執行，建立必要的資料夾並初始化 bus_data 字典。

        Args:
            spider (scrapy.Spider): 開啟的爬蟲物件。
        """
        OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)
        self.bus_data = {}

    def process_item(self, item, spider):
        """
        處理每一個 BusInfo Item，儲存公車資訊到 JSON 檔案。

        Args:
            item (BusInfo): 爬蟲產生的 BusInfo Item。
            spider (scrapy.Spider): 產生 Item 的爬蟲物件。

        Returns:
            BusInfo: 傳遞 Item 給下一個 Pipeline 或 Scrapy 引擎。
        """
        if not isinstance(item, BusInfo):
            return item  # 如果不是 BusInfo Item 則直接放行

        item_dict = dict(item)  # 將 Item 轉換成字典方便處理
        route_type = item_dict["route_type"]
        item_name = item_dict["item_name"]

        if route_type not in self.bus_data:
            self.bus_data[route_type] = {}
        self.bus_data[route_type][item_name] = item_dict["data"]

        file_path = OUTPUT_FOLDER / f"{item_name}.json"  # 儲存檔案名稱改為 item_name
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(item_dict["data"], f, ensure_ascii=False, indent=4)

        spider.logger.info(
            f'✅ 成功儲存 {item_dict["route_type"]} 的 {item_dict["item_name"]} 資料至 "{file_path}"'
        )
        return item

    def close_spider(self, spider):
        """
        Spider 關閉時執行，將所有公車資料合併儲存為 JSON 檔案。

        Args:
            spider (scrapy.Spider): 關閉的爬蟲物件。
        """
        with open(COMBINED_JSON_FILE, "w", encoding="utf-8") as f:
            json.dump(self.bus_data, f, ensure_ascii=False, indent=4, sort_keys=True)
        spider.logger.info(f'✅ 成功儲存公車資料至 "{COMBINED_JSON_FILE}"')
