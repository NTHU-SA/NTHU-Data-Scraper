import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import requests
from bs4 import BeautifulSoup
from loguru import logger
from requests.adapters import HTTPAdapter, Retry

# --- 全域參數設定 ---
HEADERS = {
    "accept": "*/*",
    "accept-encoding": "gzip, deflate, br",
    "accept-language": "zh-TW,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6,zh-CN;q=0.5",
    "dnt": "1",
    "host": "newsletter.cc.nthu.edu.tw",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
}

OUTPUT_PATH = Path("data/static/newsletters")
LIST_OUTPUT_PATH = Path("data/static/newsletters_list.json")
URL_PREFIX = "https://newsletter.cc.nthu.edu.tw"

# 設定 requests session，增加 retry 機制
session = requests.Session()
retries = Retry(
    total=5,  # 總共重試 5 次
    backoff_factor=1,  # 指數退避（1 秒、2 秒、4 秒…）
    status_forcelist=[500, 502, 503, 504, 408],
)
session.mount("https://", HTTPAdapter(max_retries=retries))


def parse_newsletter_list_html(res_text: str) -> List[Dict[str, Any]]:
    """
    解析電子報列表頁面，取得各電子報的名稱、連結與表格資料
    """
    soup = BeautifulSoup(res_text, "html.parser")
    gallery = soup.find("div", {"class": "gallery"})
    newsletter_list = []

    if gallery is None:
        logger.error("找不到電子報列表")
        return []

    for li in gallery.find_all("li"):
        h3 = li.find("h3")
        if h3:
            a = h3.find("a")
            if not a:
                continue
            name = a.text.strip()
            link = a["href"]
            table_data = {}
            table = h3.find("table")
            if table:
                for row in table.find_all("tr"):
                    elements = row.find_all(["td", "th"])  # 考慮到可能有 th 與 td
                    if len(elements) == 2:
                        key = elements[0].text.strip()
                        value = elements[1].text.strip()
                        table_data[key] = value
            newsletter_list.append({"name": name, "link": link, "table": table_data})

    return newsletter_list


def scrape_newsletters_list(path: Path = LIST_OUTPUT_PATH) -> List[Dict[str, Any]]:
    """
    爬取電子報清單並存入 JSON 檔案，返回電子報列表
    """
    url = URL_PREFIX + "/nthu-list/search.html"
    logger.info(f"取得 {url} 的 response")
    try:
        response = session.get(url, headers=HEADERS, timeout=10)
        response.encoding = "big5"
        newsletter_list = parse_newsletter_list_html(response.text)
        logger.debug(newsletter_list)

        path.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f'儲存 newsletter 的資料到 "{path}"')
        with path.open("w", encoding="utf-8") as f:
            json.dump(newsletter_list, f, ensure_ascii=False, indent=4)

    except requests.exceptions.RequestException as e:
        logger.error(f"無法爬取電子報清單: {e}")
        return []

    return newsletter_list


def parse_selected_newsletter(res_text: str) -> List[Dict[str, Any]]:
    """
    解析選定的電子報頁面，提取文章標題、連結和日期
    """
    soup = BeautifulSoup(res_text, "html.parser")
    content = soup.find("div", {"id": "acyarchivelisting"})
    if content is None:
        return []

    table = content.find("table", {"class": "contentpane"})
    if table is None:
        return []

    newsletter_list = []
    for archive_row in table.find_all("div", {"class": "archiveRow"}):
        title, link, date_str = None, None, None

        a = archive_row.find("a")
        if a:
            onclick = a.get("onclick", "")
            match = re.search(r"openpopup\('(.*?)',", onclick)
            if match:
                link = URL_PREFIX + match.group(1)
            title = a.text.strip()

        date_span = archive_row.find("span", {"class": "sentondate"})
        if date_span:
            date_str = date_span.text.strip()
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
            date_str = date_str.replace("Sent on ", "")
            for zh_month, en_month in month_mapping.items():
                date_str = date_str.replace(zh_month, en_month)
            try:
                date_str = datetime.strptime(date_str, "%d %b %Y").strftime("%Y-%m-%d")
            except ValueError:
                logger.error(f"日期解析錯誤: {date_str}")
                date_str = None

        newsletter_list.append({"title": title, "link": link, "date": date_str})

    return newsletter_list


def scrape_selected_newsletter(url: str, name: str) -> None:
    """
    爬取指定電子報的內容並儲存為 JSON 檔案
    """
    try:
        logger.info(f"取得 {url} 的 response")
        response = session.get(url, headers=HEADERS, timeout=10)
        response.encoding = "utf-8"
        newsletter_articles = parse_selected_newsletter(response.text)
        logger.debug(newsletter_articles)

        if not newsletter_articles:
            logger.warning(f"❗ 沒有獲取到任何內容: {name}")

        safe_name = name.replace("/", "-")
        file_path = OUTPUT_PATH / f"{safe_name}.json"
        OUTPUT_PATH.mkdir(parents=True, exist_ok=True)
        logger.info(f'儲存「{name}」的資料到 "{file_path}"')
        with file_path.open("w", encoding="utf-8") as f:
            json.dump(newsletter_articles, f, ensure_ascii=False, indent=4)

    except requests.exceptions.RequestException as e:
        logger.error(f"無法抓取 {name} ({url})，錯誤為 {e}")


def scrape_all_newsletters(file_folder: Path) -> None:
    """
    爬取所有電子報（使用多執行緒）
    """
    file_folder.mkdir(parents=True, exist_ok=True)
    newsletters = scrape_newsletters_list()

    if not newsletters:
        logger.error("❌ 無法獲取電子報清單，結束爬取")
        return

    # 使用 ThreadPoolExecutor 替代手動建立 threading.Thread
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [
            executor.submit(
                scrape_selected_newsletter, newsletter["link"], newsletter["name"]
            )
            for newsletter in newsletters
        ]
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                logger.error(f"爬取電子報時發生錯誤: {e}")


if __name__ == "__main__":
    scrape_all_newsletters(OUTPUT_PATH)
