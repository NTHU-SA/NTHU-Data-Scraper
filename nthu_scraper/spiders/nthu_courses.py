"""Download only the current official course feed."""

from pathlib import Path
from typing import Any

import scrapy

from nthu_scraper.course_data import (
    SOURCE_BY_ID,
    decode_json,
    group_courses,
    publish_sources,
)
from nthu_scraper.utils.constants import COURSES_FOLDER
from nthu_scraper.utils.crawl_safety import WholeDatasetSpider
from nthu_scraper.utils.file_utils import save_json
from nthu_scraper.utils.url_utils import normalize_http_url

COURSE_DATA_URL = {"latest": SOURCE_BY_ID["latest"].url}


class CoursesSpider(WholeDatasetSpider):
    name = "nthu_courses"
    allowed_domains = ["www.ccxp.nthu.edu.tw"]
    custom_settings = {"ROBOTSTXT_OBEY": False}

    def __init__(self, *args, mode: str = "latest", **kwargs):
        super().__init__(*args, **kwargs)
        if mode != "latest":
            raise ValueError(
                "Course spider only downloads latest; use "
                "'python -m nthu_scraper.course_tool' for import or rebuild"
            )

    async def start(self):
        yield scrapy.Request(
            normalize_http_url(COURSE_DATA_URL["latest"]),
            meta={"data_type": "latest"},
            errback=self.handle_request_error,
        )

    def handle_request_error(self, failure):
        super().handle_request_error(failure)
        raise ValueError(
            f"Course download failed: {failure.request.url}"
        ) from failure.value

    def parse(self, response):
        if response.meta.get("data_type", "latest") != "latest":
            raise ValueError("Course spider only accepts the latest feed")
        try:
            group_courses(decode_json(response.body))
            publish_sources({"latest": response.body}, COURSES_FOLDER)
        except (ValueError, OSError, TypeError) as error:
            self.logger.error("Course refresh failed: %s", error)
            raise

    def split_course_data(
        self, data: list[dict[str, Any]], output_folder: Path
    ) -> None:
        semesters = group_courses(data)
        output_folder.mkdir(parents=True, exist_ok=True)
        for semester, courses in semesters.items():
            save_json(courses, output_folder / f"{semester}.json", ensure_dir=False)
