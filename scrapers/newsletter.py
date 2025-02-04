import json
import os
import re
import threading
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from loguru import logger
from requests.adapters import HTTPAdapter, Retry

headers = {
    "accept": "*/*",
    "accept-encoding": "gzip, deflate, br",
    "accept-language": "zh-TW,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6,zh-CN;q=0.5",
    "dnt": "1",
    "host": "newsletter.cc.nthu.edu.tw",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
}

FILE_PATH = "json/newsletters/"
LIST_FILE = "json/newsletters_list.json"
URL_PREFIX = "https://newsletter.cc.nthu.edu.tw"

# 設定 requests session，增加 retry 機制
session = requests.Session()
retries = Retry(
    total=5,  # 總共重試 5 次
    backoff_factor=1,  # 指數退避（1 秒、2 秒、4 秒…）
    status_forcelist=[500, 502, 503, 504, 408],  # 針對這些 HTTP 錯誤碼進行重試
)
session.mount("https://", HTTPAdapter(max_retries=retries))


def parse_newsletter_list_html(res_text: str) -> list:
    """解析電子報列表頁面，取得各電子報的名稱與連結"""
    soup = BeautifulSoup(res_text, "html.parser")
    gallery = soup.find("div", {"class": "gallery"})
    newsletter_list = []

    if not gallery:
        logger.error("找不到電子報列表")
        return []

    for li in gallery.find_all("li"):
        h3 = li.find("h3")
        if h3 is not None:
            a = h3.find("a")
            name = a.text.strip()
            link = a["href"]
            table = h3.find("table")

            table_data = {}
            if table:
                for row in table.find_all("tr"):
                    elements = row.find_all(["td", "th"])  # 有些是 th，有些是 td
                    if len(elements) == 2:
                        table_data[elements[0].text.strip()] = elements[1].text.strip()

            newsletter_list.append({"name": name, "link": link, "table": table_data})

    return newsletter_list


def scrape_newsletters_list(path=LIST_FILE) -> list:
    """爬取電子報清單並存入 JSON 檔案"""
    url = URL_PREFIX + "/nthu-list/search.html"
    logger.info(f"取得 {url} 的 response")
    try:
        response = session.get(url, headers=headers, timeout=10)  # 設定 10 秒超時
        response.encoding = "big5"
        newsletter_list = parse_newsletter_list_html(response.text)
        logger.debug(newsletter_list)

        logger.info(f'儲存 newsletter 的資料到 "{path}"')
        with open(path, "w", encoding="utf-8") as f:
            json.dump(newsletter_list, f, ensure_ascii=False, indent=4)

    except requests.exceptions.RequestException as e:
        logger.error(f"無法爬取電子報清單: {e}")
        return []  # 返回空列表，避免後續發生錯誤

    return newsletter_list


def parse_selected_newsletter(res_text: str) -> list:
    """解析選定的電子報頁面，提取文章標題、連結和日期"""
    soup = BeautifulSoup(res_text, "html.parser")
    content = soup.find("div", {"id": "acyarchivelisting"})
    if content is None:
        return []

    table = content.find("table", {"class": "contentpane"})
    newsletter_list = []

    for archive_row in table.find_all("div", {"class": "archiveRow"}):
        text, link, date = None, None, None

        a = archive_row.find("a")
        if a is not None:
            onclick = a.get("onclick")
            match = re.search(r"openpopup\('(.*?)',", onclick)
            if match:
                link = URL_PREFIX + match.group(1)
            text = a.text.strip()

        date_span = archive_row.find("span", {"class": "sentondate"})
        if date_span is not None:
            date = date_span.text.strip()
            month_mapping = {
                " 一月 ": " Jan ",
                " 二月 ": " Feb ",
                " 三月 ": " Mar ",
                " 四月 ": " Apr ",
                " 五月 ": " May ",
                " 六月 ": " Jun ",
                " 七月 ": " Jul ",
                " 八月 ": " Aug ",
                " 九月 ": " Sep ",
                " 十月 ": " Oct ",
                " 十一月 ": " Nov ",
                " 十二月 ": " Dec ",
            }
            date = date.replace("Sent on ", "")
            for zh_month, en_month in month_mapping.items():
                date = date.replace(zh_month, en_month)
            try:
                date = datetime.strptime(date, "%d %b %Y").strftime("%Y-%m-%d")
            except ValueError:
                logger.error(f"日期解析錯誤: {date}")
                date = None

        newsletter_list.append({"title": text, "link": link, "date": date})

    return newsletter_list


def scrape_selected_newsletter(url: str, name: str):
    """爬取指定的電子報內容"""
    try:
        logger.info(f"取得 {url} 的 response")
        response = session.get(url, headers=headers, timeout=10)
        response.encoding = "utf-8"
        newsletter_list = parse_selected_newsletter(response.text)
        logger.debug(newsletter_list)

        if not newsletter_list:
            logger.warning(f"❗ 沒有獲取到任何內容: {name}")

        path = os.path.join(FILE_PATH, name.replace("/", "-") + ".json")
        logger.info(f'儲存「{name}」的資料到 "{path}"')

        with open(path, "w", encoding="utf-8") as f:
            json.dump(newsletter_list, f, ensure_ascii=False, indent=4)

    except requests.exceptions.RequestException as e:
        logger.error(f"無法抓取 {name} ({url})，錯誤為 {e}")


def scrape_all_newsletters(file_folder):
    """爬取所有電子報（多執行緒）"""
    os.makedirs(file_folder, exist_ok=True)
    newsletters = scrape_newsletters_list()

    if not newsletters:
        logger.error("❌ 無法獲取電子報清單，結束爬取")
        return

    threads = []
    for newsletter in newsletters:
        t = threading.Thread(
            target=scrape_selected_newsletter,
            args=(newsletter["link"], newsletter["name"]),
        )
        threads.append(t)
        t.start()

    for t in threads:
        t.join()


if __name__ == "__main__":
    scrape_all_newsletters(FILE_PATH)
