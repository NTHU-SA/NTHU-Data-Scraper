import json
import os
import re
from pathlib import Path
from typing import Any, List

import requests
from loguru import logger
from requests.adapters import HTTPAdapter, Retry

# --- 全域參數設定 ---
DATA_FOLDER = os.getenv("DATA_FOLDER", "temp")
OUTPUT_PATH = Path(DATA_FOLDER + "/dining.json")

HEADERS = {
    "accept": "*/*",
    "accept-encoding": "gzip, deflate, br",
    "accept-language": "zh-TW,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6,zh-CN;q=0.5",
    "dnt": "1",
    "host": "ddfm.site.nthu.edu.tw",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
}

# 建立 requests session 並設定 retry 機制
session = requests.Session()
retries = Retry(
    total=5,  # 總共重試 5 次
    backoff_factor=1,  # 指數退避：1 秒、2 秒、4 秒...
    status_forcelist=[500, 502, 503, 504, 408],
)
session.mount("https://", HTTPAdapter(max_retries=retries))

# 預先編譯正規表達式（改善效能與可讀性）
DINING_REGEX = re.compile(r"const restaurantsData = (\[.*?)(?:\s+renderTabs)", re.S)


def parse_html(res_text: str) -> List[Any]:
    """
    解析網頁原始碼，提取餐廳資料（JSON 格式）。
    若無法找到資料則回傳空列表。

    參數:
        res_text (str): 原始 HTML 內容

    回傳:
        List[Any]: 解析出的餐廳資料列表
    """
    match = DINING_REGEX.search(res_text)
    if match is None:
        logger.error("找不到餐廳資料的內容")
        return []

    dining_data = match.group(1)
    # 將單引號換成雙引號，並移除換行符號
    dining_data = dining_data.replace("'", '"').replace("\n", "")
    # 移除多餘的逗號，例如 "..., ]" 變成 "...]"
    dining_data = re.sub(r",[ ]+?\]", "]", dining_data)
    try:
        data = json.loads(dining_data)
        return data
    except json.JSONDecodeError as e:
        logger.error(f"JSON 解碼錯誤: {e}")
        return []


def scrape_dining(path: Path) -> None:
    """
    爬取餐廳及服務性廠商的資料，並儲存到指定的 JSON 檔案中。

    參數:
        path (Path): 儲存結果的檔案路徑
    """
    url = "https://ddfm.site.nthu.edu.tw/p/404-1494-256455.php?Lang=zh-tw"
    try:
        logger.info(f"正在從 {url} 獲取資料")
        response = session.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()  # 若 HTTP 狀態碼不為 200，則拋出異常
        response.encoding = "utf-8"
        logger.success("成功取得餐廳及服務性廠商的資料")
    except requests.RequestException as e:
        logger.error(f"爬取資料時發生錯誤: {e}")
        return

    dining_data = parse_html(response.text)
    if not dining_data:
        logger.error("未能解析到任何餐廳資料，將不進行儲存")
        return

    logger.debug(dining_data)
    try:
        with path.open("w", encoding="utf-8") as f:
            json.dump(dining_data, f, ensure_ascii=False, indent=4)
        logger.success(f'成功將餐廳資料儲存到 "{path}"')
    except IOError as e:
        logger.error(f"寫入檔案時發生錯誤: {e}")


if __name__ == "__main__":
    scrape_dining(OUTPUT_PATH)
