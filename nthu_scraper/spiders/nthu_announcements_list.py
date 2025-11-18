"""清華大學公告爬蟲 - 公告列表爬蟲"""

import re
from typing import Dict

import scrapy
from scrapy_playwright.page import PageMethod

from nthu_scraper.utils.constants import (
    ANNOUNCEMENTS_LIST_PATH,
    DIRECTORY_PATH,
    LANGUAGES,
    RPAGE_DOMAIN_SUFFIX,
)
from nthu_scraper.utils.file_utils import load_json, save_json
from nthu_scraper.utils.url_utils import (
    build_multi_lang_urls,
    check_domain_suffix,
    update_url_query_param,
    force_https,
)

# 其他公告來源
OTHER_SOURCES = {
    "清華公佈欄": {
        "zh-tw": "https://bulletin.site.nthu.edu.tw/?Lang=zh-tw",
        "en": "https://bulletin.site.nthu.edu.tw/?Lang=en",
    },
    "國立清華大學學生會": {
        "zh-tw": "https://nthusa.site.nthu.edu.tw/?Lang=zh-tw",
    },
}

CUSTOM_ANNOUNCEMENT_SOURCES = [
    # 可在此添加自訂的公告來源
    {
        "title": "校園公車暨巡迴公車公告",
        "link": "https://affairs.site.nthu.edu.tw/p/403-1165-1065-1.php?Lang=zh-tw",
        "language": "zh-tw",
        "department": "總務處事務組",
    },
    {
        "title": "校園公車暨巡迴公車公告",
        "link": "https://affairs.site.nthu.edu.tw/p/403-1165-1065-1.php?Lang=en",
        "language": "en",
        "department": "總務處事務組",
    },
]


class AnnouncementListItem(scrapy.Item):
    """公告列表 Item"""

    title = scrapy.Field()
    link = scrapy.Field()
    language = scrapy.Field()
    department = scrapy.Field()


class AnnouncementsListSpider(scrapy.Spider):
    """
    公告列表爬蟲

    負責遞迴爬取公告列表頁面，建立並更新 announcements_list.json
    """

    name = "nthu_announcements_list"
    custom_settings = {
        "ITEM_PIPELINES": {
            "nthu_scraper.spiders.nthu_announcements_list.AnnouncementListPipeline": 1,
        },
        # 啟用本模組內的 middleware，優先順序可調（數字越小越先執行）
        "DOWNLOADER_MIDDLEWARES": {
            "nthu_scraper.spiders.nthu_announcements_list.EnforceHTTPSMiddleware": 543,
        },
        "DOWNLOAD_HANDLERS": {
            "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
            "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
        },
        "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
        "PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT": 15_000,
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.department_urls = self._load_department_urls()
        self.existing_links = self._load_existing_links()
        self.requested_urls = set()

    def _load_department_urls(self) -> Dict[str, Dict[str, str]]:
        """從通訊錄載入單位 URL"""
        urls = {}
        directory = load_json(DIRECTORY_PATH)
        # directory = None
        if directory:
            for dept in directory:
                try:
                    if dept["parent_name"]:
                        dept_name = dept["parent_name"] + dept["name"]
                    else:
                        dept_name = dept["name"]
                    website = dept["details"]["contact"]["website"]
                    lang_urls = build_multi_lang_urls(website, LANGUAGES)
                    if lang_urls and check_domain_suffix(website, RPAGE_DOMAIN_SUFFIX):
                        urls[dept_name] = lang_urls
                except KeyError:
                    continue

        # 添加其他來源（OTHER_SOURCES 已改為 https）
        urls.update(OTHER_SOURCES)
        return urls

    def _load_existing_links(self) -> set:
        """載入現有的公告列表連結"""
        existing_data = load_json(ANNOUNCEMENTS_LIST_PATH)
        if existing_data:
            return {item["link"] for item in existing_data}
        return set()

    def _build_playwright_meta(self, meta: Dict) -> Dict:
        new_meta = meta.copy()
        new_meta.update(
            {
                "playwright": True,
                "playwright_page_methods": [
                    PageMethod("wait_for_load_state", "networkidle")
                ],
            }
        )
        return new_meta

    async def start(self):
        """發送初始請求"""
        for dept, lang_urls in self.department_urls.items():
            for lang, url in lang_urls.items():
                meta = {"department": dept, "language": lang, "base_url": url}
                request = self._build_request(url, self.parse, meta)
                if request:
                    yield request

    def _build_request(self, url, callback, meta):
        normalized_url = self._prepare_request_url(url)
        if not normalized_url:
            return None
        return scrapy.Request(
            normalized_url,
            callback=callback,
            meta=self._build_playwright_meta(meta.copy()),
        )

    def _prepare_request_url(self, url: str) -> str | None:
        if not url:
            return None
        normalized = force_https(url)
        if not normalized or not check_domain_suffix(normalized, RPAGE_DOMAIN_SUFFIX):
            return None
        if normalized in self.requested_urls:
            return None
        self.requested_urls.add(normalized)
        return normalized

    def parse(self, response):
        """解析主頁面"""
        # 解析 tab content 中的動態載入連結
        # yield from self._parse_tab_content(response)

        # 解析 "more" 連結
        yield from self._parse_more_links(response)

    def _parse_tab_content(self, response):
        """解析 tab content 中的公告連結"""
        # 有點忘記為啥有他了
        tab_panes = response.css("div.tab-pane")
        for tab in tab_panes:
            tab_text = tab.xpath("string(.)").get()
            tab_url_pattern = re.compile(r'\$\.\s*hajaxOpenUrl\(\s*["\']([^"\']+)')
            match = tab_url_pattern.search(tab_text or "")
            if not match:
                continue
            url = response.urljoin(match.group(1))
            url = update_url_query_param(url, "Lang", response.meta.get("language"))
            request = self._build_request(url, self.parse, response.meta.copy())
            if request:
                yield request

    def _parse_more_links(self, response):
        """解析 more 連結"""
        more_links = response.css("p.more a::attr(href)").getall()
        for link in more_links:
            abs_url = response.urljoin(link)
            abs_url = update_url_query_param(
                abs_url, "Lang", response.meta.get("language")
            )
            request = self._build_request(
                abs_url, self.parse_announcement_list, response.meta.copy()
            )
            if request:
                normalized_url = request.url
                if normalized_url not in self.existing_links:
                    self.logger.info(f"發現新公告列表: {normalized_url}")
                yield request

    def parse_announcement_list(self, response):
        """解析公告列表頁面"""
        # 提取標題
        title = response.css("[class*='title']::text").get()
        if not title or not title.strip():
            title = response.css("title::text").get()
        if title:
            title = title.strip()

        # 檢查是否有公告內容
        has_content = bool(response.css("#pageptlist .row.listBS, #pageptlist tr"))

        if not has_content:
            self.logger.warning(f"公告列表頁面無內容: {response.url}")
            return

        yield AnnouncementListItem(
            title=title,
            link=response.url,
            language=response.meta.get("language"),
            department=response.meta.get("department"),
        )


class AnnouncementListPipeline:
    """公告列表 Pipeline"""

    def open_spider(self, spider):
        """初始化"""
        self.collected_items = []
        self.existing_data = load_json(ANNOUNCEMENTS_LIST_PATH) or []
        self.existing_links = {item["link"] for item in self.existing_data}

    def process_item(self, item, spider):
        """處理 Item"""
        if not isinstance(item, AnnouncementListItem):
            return item

        link = item["link"]

        # 只添加新連結
        if link not in self.existing_links:
            self.collected_items.append(dict(item))
            self.existing_links.add(link)
            spider.logger.info(f"新增公告列表: {item['department']}/{item['title']}")

        return item

    def close_spider(self, spider):
        """儲存資料"""
        # 合併新舊資料
        all_items = self.existing_data + self.collected_items

        # 新增自訂公告來源
        for custom_item in CUSTOM_ANNOUNCEMENT_SOURCES:
            if custom_item["link"] not in self.existing_links:
                all_items.append(custom_item)
                spider.logger.info(
                    f"新增自訂公告列表: {custom_item['department']}/{custom_item['title']}"
                )

        # 檢查並移除空連結（可選：驗證連結是否仍然有效）
        # 這裡先保留所有連結，實際驗證需要額外的請求

        # 按連結排序
        all_items.sort(key=lambda x: x["link"])

        save_json(all_items, ANNOUNCEMENTS_LIST_PATH)
        spider.logger.info(
            f"儲存公告列表: 共 {len(all_items)} 筆 (新增 {len(self.collected_items)} 筆)"
        )


# 新增：在模組內定義 middleware，確保所有 outgoing request 強制為 https
class EnforceHTTPSMiddleware:
    """
    Downloader middleware：在 request 發出前強制把 URL 換成 https。
    若 URL 已是 https 或無需修改，則不做變動。
    """

    def process_request(self, request, spider):
        # 使用 utils.url_utils.force_https（spider 模組已匯入）或直接再 import
        new_url = force_https(request.url)
        if new_url and new_url != request.url:
            # return 一個新的 Request 物件，以便 Scrapy 使用新的 URL
            return request.replace(url=new_url)
