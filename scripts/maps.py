import json
from pathlib import Path
from typing import Dict

import requests
from bs4 import BeautifulSoup
from config import JSON_FOLDER
from loguru import logger
from requests.adapters import HTTPAdapter, Retry

# --- 全域參數設定 ---
OUTPUT_PATH = Path(JSON_FOLDER) / "maps"

HEADERS = {
    "accept": "*/*",
    "accept-encoding": "gzip, deflate, br",
    "accept-language": "zh-TW,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6,zh-CN;q=0.5",
    "dnt": "1",
    "host": "campusmap.cc.nthu.edu.tw",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
}

MAP_URLS = {
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
    status_forcelist=[500, 502, 503, 504, 408],
)
session.mount("https://", HTTPAdapter(max_retries=retries))


def parse_html(res_text: str) -> Dict[str, Dict[str, str]]:
    """
    解析 HTML 並提取地圖座標資料

    參數:
        res_text (str): HTML 原始字串

    回傳:
        dict: 以地點名稱為 key，經緯度資料（latitude, longitude）為 value 的字典
    """
    soup = BeautifulSoup(res_text, "html.parser")
    options = soup.find_all("option")
    map_data = {}
    for option in options:
        if not option.get("value"):
            continue
        # 將經緯度分離並去除不必要的空白
        coords = [coord.strip() for coord in option["value"].split(",")]
        if len(coords) == 2:  # 確保有經緯度
            location = {"latitude": coords[0], "longitude": coords[1]}
            map_data[option.text.strip()] = location
    return map_data


def scrape_map(path: Path) -> None:
    """
    依據 MAP_URLS 中的 URL 抓取並儲存對應的地圖座標資料

    參數:
        path (Path): 儲存 JSON 資料的資料夾路徑
    """
    path.mkdir(parents=True, exist_ok=True)
    for name, url in MAP_URLS.items():
        try:
            response = session.get(url, headers=HEADERS, timeout=10)
            response.raise_for_status()
            logger.info(f"已取得 {name} 的資料")
            map_data = parse_html(response.text)
            logger.debug(map_data)
            file_path = path / f"{name}.json"
            logger.info(f'儲存 {name} 的資料到 "{file_path}"')
            with file_path.open("w", encoding="utf-8") as f:
                json.dump(map_data, f, ensure_ascii=False, indent=4)
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ 爬取 {name} 失敗: {e}")


if __name__ == "__main__":
    scrape_map(OUTPUT_PATH)
