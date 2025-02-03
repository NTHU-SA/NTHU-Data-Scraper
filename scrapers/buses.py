import json
import os
import re

import requests
from bs4 import BeautifulSoup
from loguru import logger


def parse_campus_info(variable_string: str, res_text: str) -> json:
    regex_pattern = r"const " + variable_string + r" = (\{.*?\})"
    data = re.search(regex_pattern, res_text, re.S)
    if data is not None:
        data = data.group(1)
    else:
        return None
    data = data.replace("'", "|")
    data = data.replace('"', '\\"')
    data = data.replace("|", '"')
    data = data.replace("\n", "")
    data = data.replace("direction", '"direction"')
    data = data.replace("duration", '"duration"')
    data = data.replace("route", '"route"', 1)
    data = data.replace("routeEN", '"routeEN"')
    data = json.loads(data)
    # 使用 BeautifulSoup 移除 route 和 routeEN 中的 span
    # 原始: <span style=\"color: #F44336;\">(紅線)</span> 台積館 → <span style=\"color: #F44336;\">南門停車場</span>...
    for key in ["route", "routeEN"]:
        if key in data and ("<span" in data[key] or "</span>" in data[key]):
            soup = BeautifulSoup(data[key], "html.parser")
            data[key] = soup.get_text(separator=" ")
    return data


def parse_bus_schedule(variable_string: str, res_text: str) -> json:
    regex_pattern = r"const " + variable_string + r" = (\[.*?\])"
    data = re.search(regex_pattern, res_text, re.S)
    if data is not None:
        data = data.group(1)
    else:
        return None
    data = data.replace("'", '"')
    data = data.replace("\n", "")
    data = data.replace("time", '"time"')
    data = data.replace("description", '"description"')
    data = data.replace("depStop", '"dep_stop"')
    data = data.replace("line", '"line"')
    data = re.sub(r",[ ]+?\]", "]", data)  # remove trailing comma
    data = json.loads(data)
    data = [i for i in data if i["time"] != ""]  # remove empty time
    for i in data:
        i["route"] = "校園公車" if "line" in data[0] else "南大區間車"
    return data


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
}  # 總務處事務組　Division of Physical Facility


def scrape_buses(path):
    os.makedirs(path, exist_ok=True)
    for name, data in bus_url.items():
        res_text = requests.get(data["url"], headers=headers).text
        logger.info(f"已取得 {name} 的資料")
        for info in data["info"]:
            info_data = parse_campus_info(info, res_text)
            logger.debug(info_data)
            if info_data is not None:
                file_path = path + info + ".json"
                logger.info(f'儲存 {info} 的資料到 "{file_path}"')
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(info_data, f, ensure_ascii=False, indent=4)
        for schedule in data["schedule"]:
            schedule_data = parse_bus_schedule(schedule, res_text)
            logger.debug(schedule_data)
            if schedule_data is not None:
                file_path = path + schedule + ".json"
                logger.info(f'儲存 {schedule} 的資料到 "{file_path}"')
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(schedule_data, f, ensure_ascii=False, indent=4)


if __name__ == "__main__":
    scrape_buses("json/buses/")
