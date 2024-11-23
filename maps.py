import json
import os

import requests
from bs4 import BeautifulSoup
from loguru import logger

headers = {
    "accept": "*/*",
    "accept-encoding": "gzip, deflate, br",
    "accept-language": "zh-TW,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6,zh-CN;q=0.5",
    "dnt": "1",
    "host": "campusmap.cc.nthu.edu.tw",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
}

map_url = {
    "MainZH": "https://campusmap.cc.nthu.edu.tw/",
    "MainEN": "https://campusmap.cc.nthu.edu.tw/en",
    "NandaZH": "https://campusmap.cc.nthu.edu.tw/sd",
    "NandaEN": "https://campusmap.cc.nthu.edu.tw/sden",
}


def parse_html(res_text) -> json:
    soup = BeautifulSoup(res_text, "html.parser")
    options = soup.find_all("option")
    map_data = {}
    for option in options:
        # 把經緯度分開並移除無謂的空格
        option["value"] = [coord.strip() for coord in option["value"].split(",")]
        location = {"latitude": option["value"][0], "longitude": option["value"][1]}
        map_data[option.text.strip()] = location
    return map_data


def scrape_map(path):
    os.makedirs(path, exist_ok=True)
    for name, url in map_url.items():
        res_text = requests.get(url).text
        logger.info(f"已取得 {name} 的資料")
        map_data = parse_html(res_text)
        logger.debug(map_data)
        file_path = path + name + ".json"
        logger.info(f'儲存 {name} 的資料到 "{file_path}"')
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(map_data, f, ensure_ascii=False, indent=4)


scrape_map("json/maps/")
