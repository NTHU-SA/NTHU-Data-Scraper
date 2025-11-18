"""清華大學公告爬蟲 - 公告內容爬蟲"""

from typing import List, Optional
from pathlib import Path
import re
import scrapy

from nthu_scraper.utils.constants import (
    ANNOUNCEMENTS_FOLDER,
    ANNOUNCEMENTS_JSON_PATH,
    ANNOUNCEMENTS_LIST_PATH,
)
from nthu_scraper.utils.file_utils import load_json, save_json


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
        data = load_json(ANNOUNCEMENTS_LIST_PATH)
        if not data:
            self.logger.warning("無法載入公告列表，請先執行 nthu_announcements_list")
            return []
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
                meta={
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
            link=response.url,
            language=response.meta["language"],
            department=response.meta["department"],
            articles=articles,
        )

    def _extract_articles(self, response) -> List[dict]:
        """提取公告文章列表"""
        articles = []
        container = response.css("#pageptlist")

        # 嘗試不同的選擇器
        announcement_items = container.css(".row.listBS")
        if not announcement_items:
            announcement_items = container.css("tr")

        for item in announcement_items:
            article = self._parse_article_item(item, response)
            if article and article.get("title"):
                articles.append(article)

        return articles

    def _parse_article_item(self, item, response) -> Optional[dict]:
        """解析單個公告項目"""
        # 提取標題和連結
        link_elem = item.css(".mtitle a")
        if not link_elem:
            return None

        title = link_elem.css("::text").get()
        if title:
            title = title.strip().replace('"', "")

        href = link_elem.css("::attr(href)").get()
        link = response.urljoin(href) if href else None

        # 提取日期
        date = item.css(".mdate::text").get()
        if not date:
            date = item.css(".d-txt::text").get()
        if date:
            date = date.strip()

        return {
            "title": title,
            "link": link,
            "date": date,
        }


class AnnouncementItemPipeline:
    """公告內容 Pipeline"""

    def open_spider(self, spider):
        """初始化"""
        self.collected_data = []
        ANNOUNCEMENTS_FOLDER.mkdir(parents=True, exist_ok=True)

    def process_item(self, item, spider):
        """處理 Item"""
        if not isinstance(item, AnnouncementItem):
            return item

        self.collected_data.append(dict(item))
        self._save_individual_item(item)
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
        # 按連結排序
        self.collected_data.sort(key=lambda x: x["link"])

        save_json(self.collected_data, ANNOUNCEMENTS_JSON_PATH)
        spider.logger.info(
            f"成功儲存 {len(self.collected_data)} 個公告到 announcements.json"
        )
