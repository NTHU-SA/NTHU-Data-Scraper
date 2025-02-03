import json
import os
import threading

import requests
from bs4 import BeautifulSoup
from loguru import logger

BASE_URL = "https://tel.net.nthu.edu.tw/nthusearch/"
JSON_EXTENSION = ".json"

# Define folder paths
TEMP_FOLDER = "temp/directory"
DEPT_FOLDER = TEMP_FOLDER + "/dept"
COMBINED_FOLDER = TEMP_FOLDER + "/combined"
DEPT_FILE_NAME = "json/directory.json"

headers = {
    "accept": "*/*",
    "accept-encoding": "gzip, deflate, br",
    "accept-language": "zh-TW,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6,zh-CN;q=0.5",
    "dnt": "1",
    "host": "tel.net.nthu.edu.tw",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
}


def get_response(url) -> str:
    logger.info(f"取得 {url} 的 response")
    response = requests.get(url, headers=headers)
    response.encoding = "utf-8"
    return response.text


def scrape_all_dept_url() -> list:
    text = get_response(f"{BASE_URL}index.php")
    soup = BeautifulSoup(text, "html.parser")
    departments = []
    matches = soup.select("li a")
    for match in matches:
        url = BASE_URL + match.get("href")
        name = match.text.strip()
        departments.append({"name": name, "url": url})
    with open(f"{TEMP_FOLDER}/departments.json", "w", encoding="UTF-8") as f:
        json.dump(departments, f, ensure_ascii=False, indent=4)
    return departments


def get_dept_details(url) -> dict:
    text = get_response(url)
    soup = BeautifulSoup(text, "html.parser")
    departments = []
    try:
        story_left = soup.select_one("div.story_left")
        links = story_left.select("a") if story_left else []
        for link in links:
            dept_url = BASE_URL + link.get("href")
            name = link.text.strip()
            departments.append({"name": name, "url": dept_url})
        story_max = soup.select_one("div.story_max")
        tables = story_max.select("table") if story_max else []
        contact = {}
        people = []
        if tables:
            contact = parse_contact_table(tables[0])
            if len(tables) > 1:
                people = parse_people_table(tables[1])
    except Exception as e:
        logger.error(f"{url} 的 departments 失效，錯誤為 {e}")

    return {"departments": departments, "contact": contact, "people": people}


def parse_contact_table(table) -> dict:
    contact = {}
    rows = table.select("tr")
    for row in rows:
        cols = row.select("td")
        if len(cols) >= 2:
            key = cols[0].text.strip().replace("　", "")
            if key == "":
                continue
            value = cols[1].text.strip().replace(" ", "")
            if link := cols[1].select_one("a"):
                if href := link.get("href"):
                    value = (
                        href if "mailto:" not in href else href.replace("mailto:", "")
                    )
            contact[key] = value
    return contact


def parse_people_table(table) -> list:
    people = []
    rows = table.select("tr")
    if not rows:
        return people
    headers = []
    for th in rows[0].select("td"):
        headers.append(th.text.strip().replace("　", ""))
    for row in rows[1:]:
        cols = row.select("td")
        person = {}
        for i, col in enumerate(cols):
            text = col.text.strip().replace("\u3000", "")
            if link := col.select_one("a"):
                if href := link.get("href"):
                    text = href.replace("mailto:", "") if "mailto:" in href else href
            person[headers[i]] = text
        people.append(person)
    return people


def get_all_dept_details(departments):
    threads = []
    for dept in departments:
        t = threading.Thread(target=save_dept_details, args=(dept,))
        threads.append(t)
        t.start()
    for t in threads:
        t.join()


def save_dept_details(dept):
    result = get_dept_details(dept["url"])
    filename = f"{DEPT_FOLDER}/{dept['name'].replace('/', '_')}.json"
    with open(filename, "w", encoding="UTF-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=4)


def get_sub_dept_details():
    dept_files = [f for f in os.listdir(DEPT_FOLDER) if f.endswith(JSON_EXTENSION)]
    threads = []
    for dept_file in dept_files:
        t = threading.Thread(target=process_sub_dept, args=(dept_file,))
        threads.append(t)
        t.start()
    for t in threads:
        t.join()


def process_sub_dept(dept_file):
    with open(f"{DEPT_FOLDER}/{dept_file}", "r", encoding="UTF-8") as f:
        dept_data = json.load(f)
    departments = dept_data.get("departments", [])
    dept_name = os.path.splitext(dept_file)[0]
    dept_path = f"{DEPT_FOLDER}/{dept_name.replace('/', '_')}"
    if not os.path.isdir(dept_path):
        os.mkdir(dept_path)
    for sub_dept in departments:
        result = get_dept_details(sub_dept["url"])
        filename = f"{dept_path}/{sub_dept['name'].replace('/', '_')}.json"
        with open(filename, "w", encoding="UTF-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=4)


def combine_file():
    if not os.path.isdir(COMBINED_FOLDER):
        os.mkdir(COMBINED_FOLDER)
    files = [f for f in os.listdir(DEPT_FOLDER) if f.endswith(JSON_EXTENSION)]
    for dept_file in files:
        with open(f"{DEPT_FOLDER}/{dept_file}", "r", encoding="utf-8") as f:
            data = json.load(f)
        dept_name = os.path.splitext(dept_file)[0]
        dept_path = f"{DEPT_FOLDER}/{dept_name}"
        if not os.path.isdir(dept_path):
            continue
        dept_files = [df for df in os.listdir(dept_path) if df.endswith(JSON_EXTENSION)]
        for sub_file in dept_files:
            with open(f"{dept_path}/{sub_file}", "r", encoding="utf-8") as f:
                sub_data = json.load(f)
            for k in data.get("departments", []):
                if k["name"] == os.path.splitext(sub_file)[0]:
                    k["details"] = sub_data
        with open(f"{COMBINED_FOLDER}/{dept_file}", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)


def combine_json():
    files = [f for f in os.listdir(COMBINED_FOLDER) if f.endswith(JSON_EXTENSION)]
    final_data = []
    for file in files:
        with open(f"{COMBINED_FOLDER}/{file}", "r", encoding="utf-8") as f:
            data = json.load(f)
        dept_name = os.path.splitext(file)[0]
        temp_data = {"name": dept_name, "details": data}
        final_data.append(temp_data)
    with open(DEPT_FILE_NAME, "w", encoding="utf-8") as f:
        json.dump(final_data, f, ensure_ascii=False, indent=4)


def combine_contact():
    with open(f"{TEMP_FOLDER}/departments.json", "r", encoding="utf-8") as f:
        contact_data = json.load(f)
    with open(DEPT_FILE_NAME, "r", encoding="utf-8") as f:
        dept_data = json.load(f)
    for c in contact_data:
        for d in dept_data:
            if c["name"] == d["name"]:
                d["url"] = c["url"]
    with open(DEPT_FILE_NAME, "w", encoding="utf-8") as f:
        json.dump(dept_data, f, ensure_ascii=False, indent=4)


def scrape_newsletter():
    os.makedirs(TEMP_FOLDER, exist_ok=True)
    os.makedirs(DEPT_FOLDER, exist_ok=True)
    os.makedirs(COMBINED_FOLDER, exist_ok=True)
    logger.info("開始爬取所有系所網址")
    departments = scrape_all_dept_url()
    logger.debug(departments)
    logger.info("開始多執行緒爬取所有系所詳細資料")
    get_all_dept_details(departments)
    logger.info("開始多執行緒爬取所有子系所詳細資料")
    get_sub_dept_details()
    logger.info("開始合併所有系所資料")
    combine_file()
    logger.info("開始合併所有系所資料成一個檔案")
    combine_json()
    logger.info("開始合併聯絡資訊")
    combine_contact()
    logger.info("所有爬蟲工作完成!")


if __name__ == "__main__":
    scrape_newsletter()
