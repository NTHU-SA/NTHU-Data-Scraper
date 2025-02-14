import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup
from loguru import logger
from requests.adapters import HTTPAdapter, Retry

# --- 全域參數設定 ---
DATA_FOLDER = os.getenv("DATA_FOLDER", "temp")
OUTPUT_FOLDER = Path(DATA_FOLDER + "/buses")

HEADERS: Dict[str, str] = {
    "accept": "*/*",
    "accept-encoding": "gzip, deflate, br",
    "accept-language": "zh-TW,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6,zh-CN;q=0.5",
    "dnt": "1",
    "host": "affairs.site.nthu.edu.tw",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
}

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

BUS_ANNOUCEMENT_URL = "https://affairs.site.nthu.edu.tw/p/403-1165-127-1.php"
BUS_ANNOUCEMENT_ROUTE_IMAGE_KEYWORD = {
    "main": ("校園公車"),
    "nanda": ("南大", "區間車"),
}
BUS_ANNOUCEMENT_SCHEDULE_IMAGE_KEYWORD = "時刻表"
API_URL = "https://api.nthusa.tw/scrapers/rpage/announcements/"

# 設定 requests session 與 retry 機制
session = requests.Session()
retries = Retry(
    total=5,  # 重試 5 次
    backoff_factor=1,  # 指數退避：1秒、2秒、4秒...
    status_forcelist=[500, 502, 503, 504, 408],
)
session.mount("https://", HTTPAdapter(max_retries=retries))


def parse_campus_info(variable_string: str, res_text: str) -> Optional[Dict[str, Any]]:
    """
    從網頁原始碼中解析指定變數（物件型資料），並處理部分欄位中 HTML 標籤。

    參數:
        variable_string (str): 要解析的變數名稱
        res_text (str): 網頁原始碼內容

    回傳:
        dict 或 None: 解析後的資料，若解析失敗則回傳 None
    """
    regex_pattern = r"const " + re.escape(variable_string) + r" = (\{.*?\})"
    data_match = re.search(regex_pattern, res_text, re.S)
    if data_match is None:
        logger.error(f"❎ 找不到變數 {variable_string} 的資料")
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
        logger.error(f"❎ 解析 {variable_string} JSON 失敗: {e}")
        return None

    # 使用 BeautifulSoup 移除 route 與 routeEN 中的 <span> 標籤
    for key in ["route", "routeEN"]:
        if key in data_dict and (
            "<span" in data_dict[key] or "</span>" in data_dict[key]
        ):
            soup = BeautifulSoup(data_dict[key], "html.parser")
            data_dict[key] = soup.get_text(separator=" ")
    return data_dict


def parse_bus_schedule(
    variable_string: str, res_text: str
) -> Optional[List[Dict[str, Any]]]:
    """
    從網頁原始碼中解析指定變數（陣列型資料），並處理部分欄位資料。

    參數:
        variable_string (str): 要解析的變數名稱
        res_text (str): 網頁原始碼內容

    回傳:
        list 或 None: 解析後的陣列資料，若解析失敗則回傳 None
    """
    regex_pattern = r"const " + re.escape(variable_string) + r" = (\[.*?\])"
    data_match = re.search(regex_pattern, res_text, re.S)
    if data_match is None:
        logger.error(f"❎ 找不到變數 {variable_string} 的資料")
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
        logger.error(f"解析 {variable_string} JSON 失敗: {e}")
        return None

    # 移除 time 欄位為空的項目
    data_list = [item for item in data_list if item.get("time", "") != ""]

    # 根據第一筆資料判斷路線屬性
    route_str = "校園公車" if data_list and "line" in data_list[0] else "南大區間車"
    for item in data_list:
        item["route"] = route_str
    return data_list


def save_json_data(file_path: Path, data: Any, desc: str) -> None:
    try:
        with file_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        logger.success(f'✅ 儲存 {desc} 的資料到 "{file_path}"')
    except IOError as e:
        logger.error(f"❎ 儲存檔案失敗 {file_path}: {e}")


def scrape_buses(path: Path) -> Dict[str, Dict]:
    """
    爬取校本部公車與南大區間車的相關資料，並將資料儲存為 JSON 檔案。
    """
    path.mkdir(parents=True, exist_ok=True)
    all_data = {}
    for name, data in BUS_URL.items():
        logger.info(f"🔗 正在處理：{data['url']}")
        try:
            response = session.get(data["url"], headers=HEADERS, timeout=10)
            response.raise_for_status()
            res_text = response.text
            logger.success(f"✅ 成功取得 {name} 的資料")
        except requests.RequestException as e:
            logger.error(f"❎ 取得 {name} 資料失敗: {e}")
            continue

        # 處理 info 與 schedule 資料
        for key, parser in [
            ("info", parse_campus_info),
            ("schedule", parse_bus_schedule),
        ]:
            for item in data[key]:
                parsed_data = parser(item, res_text)
                if parsed_data is not None:
                    logger.debug(parsed_data)
                    file_path = path / f"{item}.json"
                    all_data[item] = parsed_data
                    save_json_data(file_path, parsed_data, item)
                else:
                    logger.error(f"解析 {item} 資料失敗")
    return all_data


def combine_bus_data(data, path: Path) -> None:
    """
    結合公車與南大區間車的資料，並儲存為 JSON 檔案。

    參數:
        data (Dict[str, Any]): 公車與南大區間車的資料
        path (Path): 資料儲存的資料夾路徑
    """
    with (path / "buses.json").open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    logger.success(f'✅ 成功將公車與南大區間車的資料儲存到 "{path / "buses.json"}"')


def title_matches(title: str, groups: tuple) -> bool:
    """檢查 title 是否同時包含 groups 裡每組關鍵字的任一關鍵字"""
    return all(
        any(keyword in title for keyword in BUS_ANNOUCEMENT_IMAGE_KEYWORD[group])
        for group in groups
    )


def extract_image_links(announcement_url: str) -> list:
    """
    從公告頁面中提取圖片連結。

    參數:
        announcement_url (str): 公告頁面的 URL

    返回:
        list: 圖片連結列表，如果提取失敗則返回空列表
    """
    image_links = []
    try:
        response = session.get(announcement_url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        main_content = soup.find("div", class_="main")
        if main_content:
            meditor_content = main_content.find("div", class_="meditor")
            if meditor_content:
                images = meditor_content.find_all("img")
                for image in images:
                    image_url = image.get("src", "")
                    if image_url:
                        # 確保圖片連結是絕對路徑
                        image_url = (
                            "https://affairs.site.nthu.edu.tw" + image_url
                            if not image_url.startswith("http")
                            else image_url
                        )
                        image_links.append(image_url)
            else:
                logger.warning(f"❎ 在 {announcement_url} 中找不到 .meditor 元素")
        else:
            logger.warning(f"❎ 在 {announcement_url} 中找不到 .main 元素")
    except requests.RequestException as e:
        logger.error(f"❎ 提取圖片連結失敗: {e}")
    except AttributeError as e:
        logger.error(f"❎ 解析 HTML 失敗: {e}，網頁結構可能已變更")
    return image_links


def download_image(url: str, img_path: Path) -> bool:
    try:
        response = session.get(url, timeout=10)
        response.raise_for_status()
        # 確保目的資料夾存在
        img_path.parent.mkdir(parents=True, exist_ok=True)
        img_path.write_bytes(response.content)
        logger.success(f"✅ 成功下載圖片至: {img_path}")
        return True
    except requests.RequestException as e:
        logger.error(f"❎ 下載圖片失敗: {e}")
        return False


def scrape_bus_images(url: str, path: Path) -> None:
    # 確保圖片存放路徑存在
    path.mkdir(parents=True, exist_ok=True)

    # 取得公告頁面
    response = session.get(f"{API_URL}{url}", timeout=10)
    announcements = response.json()

    announcement_links = {}
    for item in announcements:
        title = item.get("title", "")
        # 先判斷是否包含時刻表關鍵字
        if not any(kw in title for kw in BUS_ANNOUCEMENT_SCHEDULE_IMAGE_KEYWORD):
            continue
        # 判斷路由關鍵字
        for key, keywords in BUS_ANNOUCEMENT_ROUTE_IMAGE_KEYWORD.items():
            if key not in announcement_links and any(kw in title for kw in keywords):
                announcement_links[key] = item.get("link", "")

    for key, announcement_url in announcement_links.items():
        image_urls = extract_image_links(announcement_url)
        if not image_urls:
            logger.warning(f"❎ 在 {key} 公告中找不到圖片。")
            continue
        for idx, image_url in enumerate(image_urls):
            image_path = path / f"{key}_{idx}.jpg"
            logger.info(f"🔗 正在下載圖片：{image_url}")
            download_image(image_url, image_path)


if __name__ == "__main__":
    all_data = scrape_buses(OUTPUT_FOLDER)
    combine_bus_data(all_data, Path(DATA_FOLDER))
    scrape_bus_images(
        BUS_ANNOUCEMENT_URL,
        OUTPUT_FOLDER / "images",
    )
