import json
import re

import requests
from loguru import logger

headers = {
    "accept": "*/*",
    "accept-encoding": "gzip, deflate, br",
    "accept-language": "zh-TW,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6,zh-CN;q=0.5",
    "dnt": "1",
    "host": "ddfm.site.nthu.edu.tw",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
}


def parse_html(res_text) -> json:
    dining_data = re.search(
        r"const restaurantsData = (\[.*?) {2}renderTabs", res_text, re.S
    )
    if dining_data is not None:
        dining_data = dining_data.group(1)
    else:
        return []
    dining_data = dining_data.replace("'", '"')
    dining_data = dining_data.replace("\n", "")
    dining_data = re.sub(r",[ ]+?\]", "]", dining_data)  # remove trailing comma
    dining_data = json.loads(dining_data)
    return dining_data


def scrape_dining(path):
    # 餐廳及服務性廠商
    # 總務處經營管理組　Division of Dining and Facilities Management
    url = "https://ddfm.site.nthu.edu.tw/p/404-1494-256455.php?Lang=zh-tw"
    response = requests.get(url, headers=headers)
    response.encoding = "utf-8"
    res_text = response.text
    logger.info("已取得餐廳及服務性廠商的資料")
    dining_data = parse_html(res_text)
    logger.debug(dining_data)
    logger.info(f'儲存餐廳及服務性廠商的資料到 "{path}"')
    with open(path, "w", encoding="utf-8") as f:
        json.dump(dining_data, f, ensure_ascii=False, indent=4)


if __name__ == "__main__":
    scrape_dining("json/dining.json")
