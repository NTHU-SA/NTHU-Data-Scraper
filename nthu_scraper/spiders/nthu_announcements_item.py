"""清華大學公告爬蟲 - 公告內容爬蟲"""

from typing import List
from pathlib import Path
import re
import scrapy

from nthu_scraper.utils.constants import (
    ANNOUNCEMENTS_FOLDER,
    ANNOUNCEMENTS_JSON_PATH,
    ANNOUNCEMENTS_LIST_PATH,
)
from nthu_scraper.utils.file_utils import load_json, save_json
from nthu_scraper.storage import read_json
from nthu_scraper.utils.crawl_safety import log_source_failure
from nthu_scraper.parsers import ParseError
from nthu_scraper.parsers.announcements import parse_articles


class AnnouncementItem(scrapy.Item):
    """公告 Item"""

    title = scrapy.Field()
    link = scrapy.Field()
    language = scrapy.Field()
    department = scrapy.Field()
    articles = scrapy.Field()


class AnnouncementArticle(scrapy.Item):
    """公告文章 Item"""

    title = scrapy.Field()
    link = scrapy.Field()
    date = scrapy.Field()


def _group_by_source_metadata(sources):
    groups = {}
    for source in sources:
        identity = tuple(source.get(key) for key in ("department", "title", "language"))
        if all(isinstance(value, str) and value.strip() for value in identity):
            groups.setdefault(identity, []).append(source)
    return groups


class AnnouncementsItemSpider(scrapy.Spider):
    """
    公告內容爬蟲

    從 announcements_list.json 讀取公告列表，爬取各公告頁面的文章內容
    """

    name = "nthu_announcements_item"
    custom_settings = {
        "ITEM_PIPELINES": {
            "nthu_scraper.spiders.nthu_announcements_item.AnnouncementItemPipeline": 1,
        },
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.announcement_list = self._load_announcement_list()

    def _load_announcement_list(self) -> List[dict]:
        """載入公告列表"""
        data = read_json(ANNOUNCEMENTS_LIST_PATH)
        if not isinstance(data, list) or any(
            not isinstance(source, dict) or not source.get("link") for source in data
        ):
            raise ValueError("Invalid authoritative announcements_list.json")
        return data

    async def start(self):
        """發送初始請求"""
        if not self.announcement_list:
            self.logger.error("公告列表為空，無法爬取")
            return

        for announcement in self.announcement_list:
            yield scrapy.Request(
                announcement["link"],
                callback=self.parse,
                errback=log_source_failure,
                meta={
                    "source_link": announcement["link"],
                    "title": announcement["title"],
                    "language": announcement["language"],
                    "department": announcement["department"],
                },
            )

    def parse(self, response):
        """解析公告頁面"""
        articles = self._extract_articles(response)

        if not articles:
            self.logger.warning(f"公告頁面無文章: {response.url}")
            return

        yield AnnouncementItem(
            title=response.meta["title"],
            link=response.meta["source_link"],
            language=response.meta["language"],
            department=response.meta["department"],
            articles=articles,
        )

    def _extract_articles(self, response) -> List[dict]:
        try:
            return parse_articles(response, response.url)
        except ParseError as error:
            self.logger.warning(
                "Incomplete announcement parse; retaining %s: %s", response.url, error
            )
            return []


class AnnouncementItemPipeline:
    """公告內容 Pipeline"""

    def open_spider(self, spider):
        """初始化"""
        self.collected_data = {}
        self.expected_links = {source["link"] for source in spider.announcement_list}
        previous = load_json(ANNOUNCEMENTS_JSON_PATH)
        if previous is not None and not isinstance(previous, list):
            raise ValueError("Expected announcements.json to contain a list")
        self.previous = {
            source["link"]: source for source in (previous if previous is not None else [])
        }
        self._restore_legacy_sources(spider)
        ANNOUNCEMENTS_FOLDER.mkdir(parents=True, exist_ok=True)

    def _restore_legacy_sources(self, spider):
        expected = _group_by_source_metadata(spider.announcement_list)
        legacy = _group_by_source_metadata(
            source for link, source in self.previous.items()
            if link not in self.expected_links
        )
        for identity, sources in expected.items():
            missing = [source for source in sources if source["link"] not in self.previous]
            candidates = legacy.get(identity, [])
            if not missing or not candidates:
                continue
            if len(sources) != 1 or len(candidates) != 1:
                raise ValueError(f"Ambiguous legacy announcement source: {identity!r}")
            link = missing[0]["link"]
            self.previous[link] = {**candidates[0], "link": link}
            spider.logger.warning(
                "Matched legacy announcement URL %s to authoritative source %s",
                candidates[0]["link"], link,
            )

    def process_item(self, item, spider):
        """處理 Item"""
        if not isinstance(item, AnnouncementItem):
            return item

        if not item.get("articles"):
            spider.logger.warning("Empty announcement refresh; retaining %s", item["link"])
            return item
        self._save_individual_item(item)
        self.collected_data[item["link"]] = dict(item)
        spider.logger.info(
            f'儲存公告: {item["department"]}/{item["title"]} '
            f'({len(item["articles"])} 篇文章)'
        )

        return item

    def _save_individual_item(self, item: AnnouncementItem) -> None:
        department = self._sanitize_path_component(
            item.get("department") or "未命名單位"
        )
        title = self._sanitize_path_component(item.get("title") or "未命名公告")
        language = self._sanitize_path_component(item.get("language") or "未知語言")

        dept_dir = ANNOUNCEMENTS_FOLDER / department
        dept_dir.mkdir(parents=True, exist_ok=True)

        file_path = dept_dir / f"{title}_{language}.json"
        save_json(dict(item), file_path)

    def _sanitize_path_component(self, value: str) -> str:
        sanitized = re.sub(r'[\\/:*?"<>|]', "_", value.strip())
        return sanitized or "unnnamed"

    def close_spider(self, spider):
        """儲存資料"""
        merged = []
        for link in sorted(self.expected_links):
            if link in self.collected_data:
                merged.append(self.collected_data[link])
            elif link in self.previous:
                spider.logger.warning("Retaining previous announcement source: %s", link)
                merged.append(self.previous[link])
            else:
                spider.logger.warning("No known-good announcement source: %s", link)
        save_json(merged, ANNOUNCEMENTS_JSON_PATH)
        spider.logger.info(
            f"成功儲存 {len(merged)} 個公告到 announcements.json"
        )
