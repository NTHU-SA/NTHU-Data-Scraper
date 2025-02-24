import json
import os
from pathlib import Path
from typing import Any, Dict, List

import scrapy

# 全域參數設定
DATA_FOLDER = Path(os.getenv("DATA_FOLDER", "temp"))
OUTPUT_FOLDER = DATA_FOLDER / "courses"
COURSE_DATA_URL: Dict[str, str] = {
    "latest": "https://www.ccxp.nthu.edu.tw/ccxp/INQUIRE/JH/OPENDATA/open_course_data.json",
    "11120-11220": "https://curricul.site.nthu.edu.tw/var/file/208/1208/img/474/11120-11220JSON.json",
    "10910-11110": "https://curricul.site.nthu.edu.tw/var/file/208/1208/img/474/unicode_1091_1111.json",
    "10820": "https://www.ccxp.nthu.edu.tw/ccxp/INQUIRE/JH/OPENDATA/open_course_data_10820.json",
}


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
        for course in data:
            course_id = course.get("科號", "")
            semester = course_id[:5]
            if len(semester) != 5:
                self.logger.error(f"❎ 科號格式錯誤: {course}")
                continue
            if semester not in semesters:
                self.logger.info(f"✅ 新增學期: {semester}")
                semesters[semester] = []
            semesters[semester].append(course)

        output_folder.mkdir(parents=True, exist_ok=True)
        for semester, courses in semesters.items():
            semester_file = output_folder / f"{semester}.json"
            try:
                with semester_file.open("w", encoding="utf-8") as f:
                    json.dump(courses, f, ensure_ascii=False, indent=2)
                self.logger.info(f"✅ 儲存學期 {semester} 資料至: {semester_file}")
            except IOError as e:
                self.logger.error(f"❎ 寫入 {semester} 檔案錯誤: {e}")
