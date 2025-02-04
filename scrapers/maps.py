import json
import os

import requests
from bs4 import BeautifulSoup
from loguru import logger
from requests.adapters import HTTPAdapter, Retry

FILE_PATH = "json/maps/"

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

# 設定 requests session，增加 retry 機制
session = requests.Session()
retries = Retry(
    total=5,  # 總共重試 5 次
    backoff_factor=1,  # 指數退避（1 秒、2 秒、4 秒…）
    status_forcelist=[500, 502, 503, 504, 408],  # 針對這些 HTTP 錯誤碼進行重試
)
session.mount("https://", HTTPAdapter(max_retries=retries))


def parse_html(res_text) -> dict:
    """解析 HTML 並提取地圖座標資料"""
    soup = BeautifulSoup(res_text, "html.parser")
    options = soup.find_all("option")
    map_data = {}
    for option in options:
        if not option.get("value"):
            continue
        # 把經緯度分開並移除無謂的空格
        coords = [coord.strip() for coord in option["value"].split(",")]
        if len(coords) == 2:  # 確保有經緯度
            location = {"latitude": coords[0], "longitude": coords[1]}
            map_data[option.text.strip()] = location
    return map_data


def scrape_map(path):
    os.makedirs(path, exist_ok=True)
    for name, url in map_url.items():
        try:
            res = session.get(url, headers=headers, timeout=10)  # 設定 10 秒超時
            res.raise_for_status()  # 如果 HTTP 回應碼不是 200，拋出錯誤
            logger.info(f"已取得 {name} 的資料")
            map_data = parse_html(res.text)
            logger.debug(map_data)
            file_path = os.path.join(path, f"{name}.json")
            logger.info(f'儲存 {name} 的資料到 "{file_path}"')
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(map_data, f, ensure_ascii=False, indent=4)
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ 爬取 {name} 失敗: {e}")


if __name__ == "__main__":
    scrape_map(FILE_PATH)
