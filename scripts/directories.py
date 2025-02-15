import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List

import requests
from bs4 import BeautifulSoup
from loguru import logger
from requests.adapters import HTTPAdapter, Retry

# --- 全域參數設定 ---
DATA_FOLDER = os.getenv("DATA_FOLDER", "temp")
OUTPUT_PATH = Path(DATA_FOLDER) / "directories.json"

URL_PREFIX = "https://tel.net.nthu.edu.tw/nthusearch/"
HEADERS = {
    "accept": "*/*",
    "accept-encoding": "gzip, deflate, br",
    "accept-language": "zh-TW,zh;q=0.9,en;q=0.8",
    "dnt": "1",
    "host": "tel.net.nthu.edu.tw",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
}

# 設定 requests session，增加 retry 機制
session = requests.Session()
retries = Retry(
    total=5,  # 總共重試 5 次
    backoff_factor=1,  # 指數退避機制
    status_forcelist=[500, 502, 503, 504, 408],
)
session.mount("https://", HTTPAdapter(max_retries=retries))


def get_response(url: str) -> str:
    """
    取得指定 URL 的回應文字內容
    """
    try:
        logger.info(f"取得回應：{url}")
        response = session.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        response.encoding = "utf-8"
        return response.text
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ 爬取 {url} 失敗: {e}")
        return ""


def scrape_all_dept_url() -> List[Dict[str, str]]:
    """
    取得首頁所有系所的 URL 與名稱
    """
    text = get_response(f"{URL_PREFIX}index.php")
    if not text:
        return []

    soup = BeautifulSoup(text, "html.parser")
    departments = []
    for match in soup.select("li a"):
        href = match.get("href", "")
        name = match.text.strip()
        if href and name:
            dept_url = URL_PREFIX + href
            departments.append({"name": name, "url": dept_url})
    return departments


def parse_contact_table(table: Any) -> Dict[str, str]:
    """
    解析聯絡資訊表格，回傳聯絡資訊字典
    """
    contact = {}
    for row in table.select("tr"):
        cols = row.select("td")
        if len(cols) >= 2:
            key = cols[0].text.strip()
            value = cols[1].text.strip()
            link = cols[1].select_one("a")
            if link:
                href = link.get("href", "")
                value = href.replace("mailto:", "") if "mailto:" in href else href
            contact[key] = value
    return contact


def parse_people_table(table: Any) -> List[Dict[str, str]]:
    """
    解析人員資訊表格，回傳人員資料列表
    """
    people = []
    rows = table.select("tr")
    if rows:
        headers = [th.text.strip() for th in rows[0].select("td")]
        for row in rows[1:]:
            cols = row.select("td")
            person = {
                headers[i]: (
                    col.select_one("a").get("href", "").replace("mailto:", "")
                    if col.select_one("a")
                    else col.text.strip()
                )
                for i, col in enumerate(cols)
            }
            people.append(person)
    return people


def get_dept_details(url: str) -> Dict[str, Any]:
    """
    取得單一系所詳細資訊，包括下級部門、聯絡資訊及人員資料
    """
    text = get_response(url)
    if not text:
        return {}

    soup = BeautifulSoup(text, "html.parser")
    departments = []
    contact = {}
    people = []

    story_left = soup.select_one("div.story_left")
    if story_left:
        departments = [
            {"name": link.text.strip(), "url": URL_PREFIX + link.get("href", "")}
            for link in story_left.select("a")
            if link.text.strip()
        ]
    story_max = soup.select_one("div.story_max")
    if story_max:
        tables = story_max.select("table")
        if tables:
            contact = parse_contact_table(tables[0])
            if len(tables) > 1:
                people = parse_people_table(tables[1])
    return {"departments": departments, "contact": contact, "people": people}


def fetch_all_details(departments: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """
    利用多執行緒並行取得各系所的詳細資訊，
    回傳包含系所名稱與詳細資料的列表
    """
    results = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_dept = {
            executor.submit(get_dept_details, dept["url"]): dept for dept in departments
        }
        for future in as_completed(future_to_dept):
            dept = future_to_dept[future]
            try:
                details = future.result()
                results.append({"name": dept["name"], "details": details})
            except Exception as exc:
                logger.error(f"❌ 系所 {dept['name']} 發生錯誤: {exc}")
    return results


def save_directories_json(data: List[Dict[str, Any]]) -> None:
    """
    將所有系所資料儲存到一個 JSON 檔案中
    """
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4, sort_keys=True)
    logger.info(f"已儲存所有系所資料至 {OUTPUT_PATH}")


def scrape_directories() -> None:
    """
    主流程：
        1. 抓取所有系所 URL
        2. 並行取得各系所詳細資訊
        3. 將結果儲存至 directories.json 文件
    """
    logger.info("開始抓取系所 URL...")
    departments = scrape_all_dept_url()
    if not departments:
        logger.error("未取得任何系所資料，結束程式。")
        return

    logger.info("開始並行抓取各系所詳細資訊...")
    details_list = fetch_all_details(departments)

    logger.info("開始儲存至 JSON 文件...")
    save_directories_json(details_list)
    logger.info("抓取完成！")


if __name__ == "__main__":
    scrape_directories()
