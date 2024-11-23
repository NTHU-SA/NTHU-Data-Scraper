import json
import os
import re
import threading
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from loguru import logger

headers = {
    "accept": "*/*",
    "accept-encoding": "gzip, deflate, br",
    "accept-language": "zh-TW,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6,zh-CN;q=0.5",
    "dnt": "1",
    "host": "newsletter.cc.nthu.edu.tw",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
}

FILE_FOLDER = "json/newsletters/"
LIST_FILE = "json/newsletters_list.json"
URL_PREFIX = "https://newsletter.cc.nthu.edu.tw"  # 計算機與通訊中心 學習科技組維護


def parse_newsletter_list_html(res_text: str) -> list:
    soup = BeautifulSoup(res_text, "html.parser")
    gallery = soup.find("div", {"class": "gallery"})
    newsletter_list = []
    for li in gallery.find_all("li"):
        h3 = li.find("h3")
        if h3 is not None:
            a = h3.find("a")
            name = a.text.strip()
            link = a["href"]
            table = h3.find("table")
            if table:
                rows = table.find_all("tr")
                print(rows)
                table_data = {}
                for row in rows:
                    elements = row.find_all(["td", "th"])  # 有些是 th，有些是 td
                    if len(elements) == 2:
                        table_data[elements[0].text.strip()] = elements[1].text.strip()
            newsletter_list.append(
                {
                    "name": name,
                    "link": link,
                    "table": table_data,
                }
            )
    return newsletter_list


def scrape_newsletters_list(path=LIST_FILE) -> list:
    url = URL_PREFIX + "/nthu-list/search.html"
    logger.info(f"取得 {url} 的 response")
    response = requests.get(url, headers=headers)
    response.encoding = "big5"  # 指定編碼為 big5
    newsletter_list = parse_newsletter_list_html(response.text)
    logger.debug(newsletter_list)
    logger.info(f'儲存 newsletter 的資料到 "{path}"')
    with open(path, "w", encoding="utf-8") as f:
        json.dump(newsletter_list, f, ensure_ascii=False, indent=4)


def parse_selected_newsletter(res_text: str) -> list:
    soup = BeautifulSoup(res_text, "html.parser")
    content = soup.find("div", {"id": "acyarchivelisting"})
    if content is None:
        return []
    table = content.find("table", {"class": "contentpane"})
    newsletter_list = []
    for archive_row in table.find_all("div", {"class": "archiveRow"}):
        text = None
        link = None
        date = None
        a = archive_row.find("a")
        if a is not None:
            onclick = a.get("onclick")  # 獲取連結
            match = re.search(r"openpopup\('(.*?)',", onclick)
            if match:
                link = URL_PREFIX + match.group(1)
            text = a.text  # 獲取內文
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
            }  # 前後空格是為了避免誤判
            date = date.replace("Sent on ", "")
            for zh_month, en_month in month_mapping.items():
                date = date.replace(zh_month, en_month)
            date = datetime.strptime(date, "%d %b %Y").strftime("%Y-%m-%d")
        newsletter_list.append(
            {
                "title": text,
                "link": link,
                "date": date,
            }
        )
    return newsletter_list


def scrape_selected_newsletter(url: str, name: str):
    try:
        logger.info(f"取得 {url} 的 response")
        response = requests.get(url, headers=headers)
        response.encoding = "utf-8"
        newsletter_list = parse_selected_newsletter(response.text)
        logger.debug(newsletter_list)
        path = FILE_FOLDER + name.replace("/", "-") + ".json"
        logger.info(f'儲存「{name}」的資料到 "{path}"')
        with open(path, "w", encoding="utf-8") as f:
            json.dump(newsletter_list, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"{name} 無法抓取 ({url})，錯誤為 {e}")


def scrape_all_newsletters():
    os.makedirs(FILE_FOLDER, exist_ok=True)
    scrape_newsletters_list()
    with open(LIST_FILE, "r", encoding="utf-8") as f:
        newsletters = json.load(f)
    threads = []
    for newsletter in newsletters:
        t = threading.Thread(
            target=scrape_selected_newsletter,
            args=(
                newsletter["link"],
                newsletter["name"],
            ),
        )
        threads.append(t)
        t.start()
    for t in threads:
        t.join()


scrape_all_newsletters()
