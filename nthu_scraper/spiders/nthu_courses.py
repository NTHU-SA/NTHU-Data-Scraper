import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List

import scrapy

# --- 全域參數設定 ---
DATA_FOLDER = Path(os.getenv("DATA_FOLDER", "temp"))
OUTPUT_FOLDER = DATA_FOLDER / "courses"
LATEST_JSON = DATA_FOLDER / "courses.json"
COURSE_DATA_URL: Dict[str, str] = {
    "latest": "https://www.ccxp.nthu.edu.tw/ccxp/INQUIRE/JH/OPENDATA/open_course_data.json",
    "11120-11220": "https://curricul.site.nthu.edu.tw/var/file/208/1208/img/474/11120-11220JSON.json",
    "10910-11110": "https://curricul.site.nthu.edu.tw/var/file/208/1208/img/474/unicode_1091_1111.json",
    "10820": "https://www.ccxp.nthu.edu.tw/ccxp/INQUIRE/JH/OPENDATA/open_course_data_10820.json",
}


# --- 輔助函式 ---
def _split_classroom_time(classroom_time: str) -> Dict[str, str]:
    """
    將教室與上課時間字串分割為教室與上課時間。

    Args:
        classroom_time (str): 教室與上課時間字串。

    Returns:
        Dict[str, str]: 教室與上課時間。
    """
    parts = classroom_time.split("\t")
    if len(parts) > 1:
        data = {"classroom": parts[0], "time": parts[1]}
    else:
        data = {
            "classroom": classroom_time,
            "time": "",
        }  # 當分割失敗時，教室設為原字串，時間設為空字串
    return data


def _strip_data_str(data: str) -> str:
    """
    移除字串中的空白字元。

    Args:
        data (str): 要處理的字串。

    Returns:
        str: 移除空白字元後的字串。
    """
    data = data.replace("<BR>", " ").replace("<br>", " ")  # 移除 HTML 標籤
    data = data.replace("\t", " ").replace("\n", " ")  # 移除換行與 Tab 字元
    return data.strip()


# --- 課程資料 ---
@dataclass
class CoursesData:
    id: str  # 科號
    chinese_title: str  # 中文課名
    english_title: str  # 英文課名
    credit: str  # 學分數
    size_limit: str  # 人限
    student_count: str  # 總人數
    lecturer: str  # 授課教師
    language: str  # 授課語言
    class_room_and_time: str  # 教室與上課時間
    classroom: str  # 教室
    time: str  # 時間
    note: str  # 備註
    suspend: str  # 停開註記
    limit_note: str  # 課程限制說明
    freshman_reservation: str  # 新生保留人數
    object: str  # 開課對象
    ge_type: str  # 通識對象
    ge_category: str  # 通識分類
    prerequisite: str  # 擋修說明
    expertise: str  # 第一二專長對應
    program: str  # 學分學程對應
    no_extra_selection: str  # 不可加簽說明
    required_optional_note: str  # 必選修說明

    # 定義各個欄位可能出現的關鍵字（同義字）
    FIELD_MAPPING = {
        "id": ["科號"],
        "chinese_title": ["課程中文名稱", "中文課名"],
        "english_title": ["課程英文名稱", "英文課名"],
        "credit": ["學分數", "學分"],
        "time": ["上課時間"],
        "classroom": ["教室"],
        "class_room_and_time": ["教室與上課時間"],
        "lecturer": ["授課教師", "教師姓名", "教師"],
        "size_limit": ["人限"],
        "student_count": ["總人數"],
        "language": ["授課語言"],
        "note": ["備註", "備註欄"],
        "suspend": ["停開註記"],
        "limit_note": ["課程限制說明"],
        "freshman_reservation": ["新生保留人數"],
        "object": ["開課對象", "選課限制條件"],
        "ge_type": ["通識對象"],
        "ge_category": ["通識分類", "通識類別"],
        "prerequisite": ["擋修說明"],
        "expertise": ["第一二專長對應"],
        "program": ["學分學程對應"],
        "no_extra_selection": ["不可加簽說明"],
        "required_optional_note": ["必選修說明", "此課程已列入之系所班別"],
    }

    @classmethod
    def from_dict(cls, init_data: dict):
        """
        根據 FIELD_MAPPING 從原始資料中找出對應的欄位資料，
        若找不到則給空字串。
        """
        data = {}

        # 處理教室與上課時間 (優先處理分開的欄位，若沒有再處理合併的欄位)
        if init_data.get("教室與上課時間"):  # 處理分開的欄位
            classroom_time_data = _split_classroom_time(init_data["教室與上課時間"])
            data["classroom"] = classroom_time_data.get("classroom", "")
            data["time"] = classroom_time_data.get("time", "").replace("\n", "")

        for canonical_field, keywords in cls.FIELD_MAPPING.items():
            found_key = None
            for key in keywords:
                if key in init_data:
                    found_key = key
                    break
            if found_key:
                data_string = str(init_data[found_key])
                data_string = _strip_data_str(data_string)
                data[canonical_field] = data_string
            else:
                if canonical_field not in data:
                    data[canonical_field] = ""

        # 移除不必要的 keys，避免 dataclass 建立錯誤
        keys_to_remove = []
        for key in data.keys():
            if key not in CoursesData.__dataclass_fields__:
                keys_to_remove.append(key)
        for key in keys_to_remove:
            del data[key]

        return cls(**data)

    def __repr__(self) -> str:
        return str(self.__dict__)


class CoursesSpider(scrapy.Spider):
    """
    清華大學課程資訊爬蟲
    """

    name = "nthu_courses"
    allowed_domains = ["www.ccxp.nthu.edu.tw", "curricul.site.nthu.edu.tw"]
    custom_settings = {
        "ROBOTSTXT_OBEY": False,
    }

    def start_requests(self):
        # 逐筆建立 Request 並傳入 data_type 到 meta 中
        for data_type, url in COURSE_DATA_URL.items():
            yield scrapy.Request(url=url, meta={"data_type": data_type})

    def parse(self, response):
        """
        處理 JSON 課程資料，儲存原始資料，再依科號分學期儲存檔案。
        """
        try:
            data: Any = response.json()
        except Exception as e:
            self.logger.error(f"❎ JSON 解析失敗: {e}")
            return

        data_type = response.meta.get("data_type", "")
        self.logger.info(f"✅ 成功取得資料 ({data_type}): {response.url}")

        # 處理特殊格式：若資料包含 "工作表1"，則取其內容
        if isinstance(data, dict) and "工作表1" in data:
            self.logger.warning(f'⚠️ 在【{data_type}】發現特殊格式，取出 "工作表1" 資料')
            data = data["工作表1"]

        # 儲存原始 JSON 資料
        OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)
        file_name = f"{data_type}.json" if data_type else "latest.json"
        output_file = OUTPUT_FOLDER / file_name
        try:
            with output_file.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.logger.info(f"✅ 原始資料已儲存至: {output_file}")
        except IOError as e:
            self.logger.error(f"❎ 儲存原始資料錯誤: {e}")

        if data_type == "latest":
            with LATEST_JSON.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.logger.info(f"✅ 更新最新課程資料至: {LATEST_JSON}")

        # 呼叫分檔方法處理課程資料 (僅當資料為列表時)
        semesters_folder = OUTPUT_FOLDER / "semesters"
        if isinstance(data, list):
            self.split_course_data(data, semesters_folder)
        else:
            self.logger.error("❎ 資料格式非列表，無法分檔")

    def split_course_data(
        self, data: List[Dict[str, Any]], output_folder: Path
    ) -> None:
        """
        根據科號前 5 碼（學期）將課程資料分割並儲存至各 JSON 檔案中。

        Args:
            data: 課程資料列表。
            output_folder: 儲存分檔資料的資料夾。
        """
        semesters: Dict[str, List[Dict[str, Any]]] = {}

        for course_dict in data:
            course_data = CoursesData.from_dict(course_dict)
            course_id = course_data.id
            semester = course_id[:5]
            if len(semester) != 5:
                self.logger.error(f"❎ 科號格式錯誤: {course_dict}")
                continue
            if semester not in semesters:
                self.logger.info(f"✅ 新增學期: {semester}")
                semesters[semester] = []
            semesters[semester].append(asdict(course_data))

        output_folder.mkdir(parents=True, exist_ok=True)
        for semester, courses in semesters.items():
            semester_file = output_folder / f"{semester}.json"
            try:
                with semester_file.open("w", encoding="utf-8") as f:
                    json.dump(courses, f, ensure_ascii=False, indent=2)
                self.logger.info(f"✅ 儲存學期 {semester} 資料至: {semester_file}")
            except IOError as e:
                self.logger.error(f"❎ 寫入 {semester} 檔案錯誤: {e}")
