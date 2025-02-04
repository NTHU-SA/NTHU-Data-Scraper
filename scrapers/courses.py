import json

import requests
from loguru import logger

folder = "json/courses"

course_data_url = {
    "lastest": "https://www.ccxp.nthu.edu.tw/ccxp/INQUIRE/JH/OPENDATA/open_course_data.json",
    "11120-11220": "https://curricul.site.nthu.edu.tw/var/file/208/1208/img/474/11120-11220JSON.json",
    "10910-11110": "https://curricul.site.nthu.edu.tw/var/file/208/1208/img/474/unicode_1091_1111.json",
    "10820": "https://www.ccxp.nthu.edu.tw/ccxp/INQUIRE/JH/OPENDATA/open_course_data_10820.json",
}


def get_json_data_from_url(url, file_name):
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        logger.info(f"取得資料成功: {url}")
        logger.info(f"資料筆數: {len(data)}")
        logger.info(f"已儲存至: {file_name}")
    except requests.RequestException as e:
        logger.error(f"取得資料失敗: {e}")
    if isinstance(data, dict) and "工作表1" in data:
        # 有一個奇怪的格式，把工作表1的資料取出來
        # 11120-11220.json
        data = data["工作表1"]
        logger.warning(f"工作表:{file_name}")
    with open(file_name, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def split_course_data(path, output_folder="json/courses/semesters"):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    semesters = {}
    for course in data:
        course_id = course["科號"]
        semester = course_id[:5]
        if len(semester) != 5:
            logger.error(f"科號格式錯誤: {course}")
            continue
        if semester not in semesters:
            logger.info(f"新增學期: {semester}")
            semesters[semester] = []
        semesters[semester].append(course)
    for semester, courses in semesters.items():
        with open(f"{output_folder}/{semester}.json", "w", encoding="utf-8") as f:
            json.dump(courses, f, ensure_ascii=False, indent=2)


for key, value in course_data_url.items():
    get_json_data_from_url(value, f"{folder}/{key}.json")
    split_course_data(f"{folder}/{key}.json")
