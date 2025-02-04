import json
import os
import re

import requests
from bs4 import BeautifulSoup
from loguru import logger
from requests.adapters import HTTPAdapter, Retry

FILE_PATH = "json/buses/"

# 設定 requests session 與 retry 機制
session = requests.Session()
retries = Retry(
    total=5,  # 重試 5 次
    backoff_factor=1,  # 指數退避：1秒、2秒、4秒...
    status_forcelist=[500, 502, 503, 504, 408],
)
session.mount("https://", HTTPAdapter(max_retries=retries))

headers = {
    "accept": "*/*",
    "accept-encoding": "gzip, deflate, br",
    "accept-language": "zh-TW,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6,zh-CN;q=0.5",
    "dnt": "1",
    "host": "affairs.site.nthu.edu.tw",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
}

bus_url = {
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


def parse_campus_info(variable_string: str, res_text: str) -> dict:
    """
    從網頁原始碼中解析指定變數（物件型資料），並處理部分欄位中 HTML 標籤。
    """
    regex_pattern = r"const " + re.escape(variable_string) + r" = (\{.*?\})"
    data_match = re.search(regex_pattern, res_text, re.S)
    if data_match is not None:
        data = data_match.group(1)
    else:
        logger.error(f"找不到變數 {variable_string} 的資料")
        return None

    # 使用替換技巧處理引號問題
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
        logger.error(f"解析 {variable_string} JSON 失敗: {e}")
        return None

    # 使用 BeautifulSoup 移除 route 與 routeEN 中的 <span> 標籤
    for key in ["route", "routeEN"]:
        if key in data_dict and (
            "<span" in data_dict[key] or "</span>" in data_dict[key]
        ):
            soup = BeautifulSoup(data_dict[key], "html.parser")
            data_dict[key] = soup.get_text(separator=" ")
    return data_dict


def parse_bus_schedule(variable_string: str, res_text: str) -> list:
    """
    從網頁原始碼中解析指定變數（陣列型資料），並處理部分欄位資料。
    """
    regex_pattern = r"const " + re.escape(variable_string) + r" = (\[.*?\])"
    data_match = re.search(regex_pattern, res_text, re.S)
    if data_match is not None:
        data = data_match.group(1)
    else:
        logger.error(f"找不到變數 {variable_string} 的資料")
        return None

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


def scrape_buses(path):
    """
    爬取校本部公車與南大區間車的相關資料，並將資料儲存為 JSON 檔案。
    """
    os.makedirs(path, exist_ok=True)
    for name, data in bus_url.items():
        try:
            response = session.get(data["url"], headers=headers, timeout=10)
            response.raise_for_status()
            res_text = response.text
            logger.info(f"成功取得 {name} 的資料")
        except requests.RequestException as e:
            logger.error(f"取得 {name} 資料失敗: {e}")
            continue

        # 處理 info 資料
        for info in data["info"]:
            info_data = parse_campus_info(info, res_text)
            if info_data is not None:
                file_path = os.path.join(path, f"{info}.json")
                logger.info(f'儲存 {info} 的資料到 "{file_path}"')
                logger.debug(info_data)
                try:
                    with open(file_path, "w", encoding="utf-8") as f:
                        json.dump(info_data, f, ensure_ascii=False, indent=4)
                except IOError as e:
                    logger.error(f"儲存檔案失敗 {file_path}: {e}")
            else:
                logger.error(f"解析 {info} 資料失敗")

        # 處理 schedule 資料
        for schedule in data["schedule"]:
            schedule_data = parse_bus_schedule(schedule, res_text)
            if schedule_data is not None:
                file_path = os.path.join(path, f"{schedule}.json")
                logger.info(f'儲存 {schedule} 的資料到 "{file_path}"')
                logger.debug(schedule_data)
                try:
                    with open(file_path, "w", encoding="utf-8") as f:
                        json.dump(schedule_data, f, ensure_ascii=False, indent=4)
                except IOError as e:
                    logger.error(f"儲存檔案失敗 {file_path}: {e}")
            else:
                logger.error(f"解析 {schedule} 資料失敗")


if __name__ == "__main__":
    scrape_buses(FILE_PATH)
