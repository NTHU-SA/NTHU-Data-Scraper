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
OUTPUT_PATH = Path(DATA_FOLDER + "/directories.json")

TEMP_FOLDER = Path("temp/directories")
TEMP_DEPT_FOLDER = TEMP_FOLDER / "dept"

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
    backoff_factor=1,  # 指數退避（1 秒、2 秒、4 秒…）
    status_forcelist=[500, 502, 503, 504, 408],
)
session.mount("https://", HTTPAdapter(max_retries=retries))


def get_response(url: str) -> str:
    """
    取得指定 URL 的回應文字內容
    """
    try:
        logger.info(f"Fetching {url}")
        response = session.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        response.encoding = "utf-8"
        return response.text
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ 爬取 {url} 失敗: {e}")
        return ""


def scrape_all_dept_url() -> List[Dict[str, str]]:
    """
    取得首頁所有系所的 URL 與名稱，並儲存至 temp/departments.json
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

    # 儲存系所清單至 temp/departments.json
    TEMP_FOLDER.mkdir(parents=True, exist_ok=True)
    departments_file = TEMP_FOLDER / "departments.json"
    with departments_file.open("w", encoding="utf-8") as f:
        json.dump(departments, f, ensure_ascii=False, indent=4)
    return departments


def parse_contact_table(table: Any) -> Dict[str, str]:
    """
    解析聯絡資訊表格
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
    解析人員資訊表格
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


def save_dept_details(dept: Dict[str, str]) -> None:
    """
    取得單一系所詳細資訊後存檔至 TEMP_DEPT_FOLDER/{dept_name}.json
    """
    TEMP_DEPT_FOLDER.mkdir(parents=True, exist_ok=True)
    # 將系所名稱中的 '/' 轉成 '_' 避免路徑問題
    safe_name = dept["name"].replace("/", "_")
    filename = TEMP_DEPT_FOLDER / f"{safe_name}.json"
    details = get_dept_details(dept["url"])
    with filename.open("w", encoding="utf-8") as f:
        json.dump(details, f, ensure_ascii=False, indent=4)
    logger.info(f"Saved details for department: {dept['name']}")


def get_all_dept_details(departments: List[Dict[str, str]]) -> None:
    """
    使用多執行緒並行取得所有系所詳細資料
    """
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_dept = {
            executor.submit(save_dept_details, dept): dept for dept in departments
        }
        for future in as_completed(future_to_dept):
            dept = future_to_dept[future]
            try:
                future.result()
            except Exception as exc:
                logger.error(f"❌ 系所 {dept['name']} 發生錯誤: {exc}")


def combine_json() -> None:
    """
    將所有系所的詳細 JSON 檔案合併成一個檔案，存放於 OUTPUT_PATH
    """
    combined_data = []
    # 改為從 TEMP_DEPT_FOLDER 讀取各系所資料
    if not TEMP_DEPT_FOLDER.exists():
        logger.error("系所資料資料夾不存在，請先執行抓取程序。")
        return

    for file in TEMP_DEPT_FOLDER.glob("*.json"):
        with file.open("r", encoding="utf-8") as f:
            data = json.load(f)
        combined_data.append({"name": file.stem, "details": data})

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(combined_data, f, ensure_ascii=False, indent=4)
    logger.info(f"Combined JSON saved to {OUTPUT_PATH}")


def scrape_newsletter() -> None:
    """
    主流程：
        1. 建立所需資料夾
        2. 抓取所有系所的 URL 清單
        3. 並行取得各系所詳細資訊
        4. 合併各系所 JSON 資料
    """
    for folder in [TEMP_FOLDER, TEMP_DEPT_FOLDER]:
        folder.mkdir(parents=True, exist_ok=True)

    logger.info("Scraping all department URLs...")
    departments = scrape_all_dept_url()
    if not departments:
        logger.error("No departments found. Exiting.")
        return

    logger.info("Fetching all department details using multithreading...")
    get_all_dept_details(departments)

    logger.info("Combining all department data...")
    combine_json()

    logger.info("Scraping completed!")


if __name__ == "__main__":
    scrape_newsletter()
    scrape_newsletter()
