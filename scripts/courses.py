import json
import os
from pathlib import Path
from typing import Any, Dict, List

import requests
from loguru import logger
from requests.adapters import HTTPAdapter, Retry

# --- 全域參數設定 ---
DATA_FOLDER = os.getenv("DATA_FOLDER", "temp")
OUTPUT_PATH = Path(DATA_FOLDER + "/courses")

COURSE_DATA_URL: Dict[str, str] = {
    "lastest": "https://www.ccxp.nthu.edu.tw/ccxp/INQUIRE/JH/OPENDATA/open_course_data.json",
    "11120-11220": "https://curricul.site.nthu.edu.tw/var/file/208/1208/img/474/11120-11220JSON.json",
    "10910-11110": "https://curricul.site.nthu.edu.tw/var/file/208/1208/img/474/unicode_1091_1111.json",
    "10820": "https://www.ccxp.nthu.edu.tw/ccxp/INQUIRE/JH/OPENDATA/open_course_data_10820.json",
}

# 設定 requests session 與 retry 機制
session = requests.Session()
retries = Retry(
    total=5,  # 重試 5 次
    backoff_factor=1,  # 指數退避：1秒、2秒、4秒...
    status_forcelist=[500, 502, 503, 504, 408],
)
session.mount("https://", HTTPAdapter(max_retries=retries))


def get_json_data_from_url(url: str, file_path: Path) -> None:
    """
    從指定 URL 取得 JSON 資料，處理特殊格式後儲存到檔案中。

    參數:
        url (str): 資料來源 URL
        file_path (Path): 儲存 JSON 資料的檔案路徑
    """
    data: Any = None
    try:
        response = session.get(url)
        response.raise_for_status()
        data = response.json()
        logger.success(f"取得資料成功: {url}")
        if isinstance(data, list):
            logger.info(f"資料筆數: {len(data)}")
        elif isinstance(data, dict):
            logger.info(f"資料包含 {len(data)} 個 key")
    except requests.RequestException as e:
        logger.error(f"取得資料失敗: {e}")

    # 處理特殊格式：若資料為 dict 且包含 "工作表1"，則取出其中內容
    if isinstance(data, dict) and "工作表1" in data:
        data = data["工作表1"]
        logger.warning(f"發現特殊格式，取出 '工作表1' 資料並儲存至: {file_path}")
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with file_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.success(f"成功儲存資料至: {file_path}")
    except IOError as e:
        logger.error(f"寫入檔案時發生錯誤: {e}")


def split_course_data(file_path: Path, output_folder: Path) -> None:
    """
    從指定的 JSON 檔案中讀取課程資料，依據科號前 5 碼分學期，並分別儲存到 output_folder 中。

    參數:
        file_path (Path): 包含課程資料的 JSON 檔案路徑
        output_folder (Path): 分學期資料要儲存的資料夾
    """
    try:
        with file_path.open("r", encoding="utf-8") as f:
            data: List[Dict[str, Any]] = json.load(f)
    except IOError as e:
        logger.error(f"讀取檔案時發生錯誤: {e}")
        return

    semesters: Dict[str, List[Dict[str, Any]]] = {}
    for course in data:
        course_id = course.get("科號", "")
        semester = course_id[:5]
        if len(semester) != 5:
            logger.error(f"科號格式錯誤: {course}")
            continue
        if semester not in semesters:
            logger.info(f"新增學期: {semester}")
            semesters[semester] = []
        semesters[semester].append(course)

    output_folder.mkdir(parents=True, exist_ok=True)
    for semester, courses in semesters.items():
        semester_file = output_folder / f"{semester}.json"
        try:
            with semester_file.open("w", encoding="utf-8") as f:
                json.dump(courses, f, ensure_ascii=False, indent=2)
            logger.info(f"儲存學期 {semester} 資料至: {semester_file}")
        except IOError as e:
            logger.error(f"寫入檔案 {semester_file} 時發生錯誤: {e}")


if __name__ == "__main__":
    # 建立主資料夾
    OUTPUT_PATH.mkdir(parents=True, exist_ok=True)

    # 獲取最新課程資料並儲存
    latest_file = OUTPUT_PATH / "lastest.json"
    get_json_data_from_url(COURSE_DATA_URL["lastest"], latest_file)

    # 依據最新課程資料分學期儲存資料
    semesters_folder = OUTPUT_PATH / "semesters"
    split_course_data(latest_file, semesters_folder)

    # 若需要獲取全部課程資料，可參考以下範例：
    # for key, url in COURSE_DATA_URL.items():
    #    file = OUTPUT_PATH / f"{key}.json"
    #    get_json_data_from_url(url, file)
    #    split_course_data(file, OUTPUT_PATH / "semesters")
