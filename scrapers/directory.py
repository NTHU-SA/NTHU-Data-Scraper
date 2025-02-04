import json
import os
import threading

import requests
from bs4 import BeautifulSoup
from loguru import logger
from requests.adapters import HTTPAdapter, Retry

BASE_URL = "https://tel.net.nthu.edu.tw/nthusearch/"
JSON_EXTENSION = ".json"

# Define folder paths
TEMP_FOLDER = "temp/directory"
DEPT_FOLDER = os.path.join(TEMP_FOLDER, "dept")
COMBINED_FOLDER = os.path.join(TEMP_FOLDER, "combined")
DEPT_FILE_NAME = "json/directory.json"

headers = {
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
    status_forcelist=[500, 502, 503, 504, 408],  # 針對這些 HTTP 錯誤碼進行重試
)
session.mount("https://", HTTPAdapter(max_retries=retries))


def get_response(url):
    try:
        logger.info(f"Fetching {url}")
        response = session.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        response.encoding = "utf-8"
        return response.text
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ 爬取 {url} 失敗: {e}")
        return ""


def scrape_all_dept_url():
    text = get_response(f"{BASE_URL}index.php")
    if not text:
        return []

    soup = BeautifulSoup(text, "html.parser")
    departments = []
    for match in soup.select("li a"):
        url = BASE_URL + match.get("href", "")
        name = match.text.strip()
        if url and name:
            departments.append({"name": name, "url": url})

    os.makedirs(TEMP_FOLDER, exist_ok=True)
    with open(
        os.path.join(TEMP_FOLDER, "departments.json"), "w", encoding="utf-8"
    ) as f:
        json.dump(departments, f, ensure_ascii=False, indent=4)
    return departments


def get_dept_details(url):
    text = get_response(url)
    if not text:
        return {}

    soup = BeautifulSoup(text, "html.parser")
    departments = []
    contact, people = {}, []

    story_left = soup.select_one("div.story_left")
    if story_left:
        departments = [
            {"name": link.text.strip(), "url": BASE_URL + link.get("href", "")}
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


def parse_contact_table(table):
    contact = {}
    for row in table.select("tr"):
        cols = row.select("td")
        if len(cols) >= 2:
            key, value = cols[0].text.strip(), cols[1].text.strip()
            if link := cols[1].select_one("a"):
                href = link.get("href", "")
                value = href.replace("mailto:", "") if "mailto:" in href else href
            contact[key] = value
    return contact


def parse_people_table(table):
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


def save_dept_details(dept):
    os.makedirs(DEPT_FOLDER, exist_ok=True)
    filename = os.path.join(DEPT_FOLDER, f"{dept['name'].replace('/', '_')}.json")
    result = get_dept_details(dept["url"])
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=4)


def get_all_dept_details(departments):
    threads = [
        threading.Thread(target=save_dept_details, args=(dept,)) for dept in departments
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


def combine_json():
    os.makedirs(COMBINED_FOLDER, exist_ok=True)
    combined_data = []
    for file in os.listdir(COMBINED_FOLDER):
        if file.endswith(JSON_EXTENSION):
            with open(os.path.join(COMBINED_FOLDER, file), "r", encoding="utf-8") as f:
                data = json.load(f)
            combined_data.append({"name": os.path.splitext(file)[0], "details": data})
    with open(DEPT_FILE_NAME, "w", encoding="utf-8") as f:
        json.dump(combined_data, f, ensure_ascii=False, indent=4)


def scrape_newsletter():
    os.makedirs(TEMP_FOLDER, exist_ok=True)
    os.makedirs(DEPT_FOLDER, exist_ok=True)
    os.makedirs(COMBINED_FOLDER, exist_ok=True)

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
