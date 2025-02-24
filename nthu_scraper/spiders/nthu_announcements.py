import json
import os
import re
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import scrapy

# --- 全域參數設定 ---
DATA_FOLDER = Path(os.getenv("DATA_FOLDER", "temp"))
COMBINED_JSON_FILE = DATA_FOLDER / "announcements.json"

DIRECTORIES_PATH = Path("data/directories.json")  # 單位資料 JSON 檔案的路徑

LANGUAGES = ["zh-tw", "en"]  # 支援的語言列表
LANGUAGE_QUERY_PARAM = "Lang"  # 語言查詢參數名
RPAGE_DOMAIN_SUFFIX = "site.nthu.edu.tw"  # Rpage 網域後綴

other_data = {
    "清華公佈欄": {
        "zh-tw": "https://bulletin.site.nthu.edu.tw/?Lang=zh-tw",
        "en": "https://bulletin.site.nthu.edu.tw/?Lang=en",
    },
    "國立清華大學學生會": {
        "zh-tw": "https://nthusa.site.nthu.edu.tw/?Lang=zh-tw",
    },
}


class AnnouncementItem(scrapy.Item):
    """
    公告資訊 Item。

    此 Item 儲存每個公告的名稱、連結、語言、所屬單位和文章列表。

    Attributes:
        title (scrapy.Field): 公告類別標題 (例如：最新公告, 學術活動)。
        link (scrapy.Field): 公告列表頁面連結。
        language (scrapy.Field): 公告語言。
        department (scrapy.Field): 所屬單位名稱。
        articles (scrapy.Field): 公告文章列表，包含 AnnouncementArticle 物件。
    """

    title = scrapy.Field()
    link = scrapy.Field()
    language = scrapy.Field()
    department = scrapy.Field()
    articles = scrapy.Field()


class AnnouncementArticle(scrapy.Item):
    """
    公告文章資訊 Item。

    此 Item 儲存從公告網頁上爬取到的單篇公告文章資訊，包含標題、連結、日期等。

    Attributes:
        title (scrapy.Field): 公告文章標題。
        link (scrapy.Field): 公告文章連結。
        date (scrapy.Field): 公告發布日期。
    """

    title = scrapy.Field()
    link = scrapy.Field()
    date = scrapy.Field()


def _update_url_lang_param(url: str, language: str) -> str:
    """
    更新網址的語言查詢參數。

    Args:
        url: 網址字串。
        language: 語言代碼。

    Returns:
        更新語言參數後的網址字串。
    """
    parsed_url = urlparse(url)
    query_params = parse_qs(parsed_url.query)
    query_params[LANGUAGE_QUERY_PARAM] = [language]
    new_query = urlencode(query_params, doseq=True)
    return urlunparse(parsed_url._replace(query=new_query))


def build_lang_urls(original_url: str) -> dict[str, str] | None:
    """
    為給定的原始 URL 建立包含不同語言版本的 URL 字典。

    如果原始 URL 不屬於 Rpage 網域，則回傳 None。

    Args:
        original_url: 原始網址字串。

    Returns:
        一個字典，鍵為語言代碼 (如 "zh-tw", "en")，值為對應語言版本的 URL。
        如果 URL 不屬於 Rpage 網域，則回傳 None。
    """
    parsed_url = urlparse(original_url)
    if not parsed_url.hostname or not parsed_url.hostname.endswith(RPAGE_DOMAIN_SUFFIX):
        return None

    lang_urls = {}
    for lang in LANGUAGES:
        lang_urls[lang] = _update_url_lang_param(original_url, lang)
    return lang_urls


def load_rpage_urls_from_directories(
    directories_path: Path,
) -> dict[str, dict[str, str]]:
    """
    從 JSON 檔案讀取單位資料並建立 Rpage URL 字典。

    Args:
        directories_path: 單位資料 JSON 檔案的路徑。

    Returns:
        一個字典，鍵為單位名稱，值為包含各語言版本 URL 的字典。
        如果載入或處理過程中發生錯誤，則回傳空字典。
    """
    rpage_urls = {}
    with open(directories_path, "r", encoding="UTF-8") as f:
        directories = json.load(f)

    for department in directories:
        try:
            dept_name = department["name"]
            department_url = department["details"]["contact"]["網頁"]
        except KeyError:
            print(f"單位【{department.get('name', '未知')}】缺少必要資訊，跳過。")
            continue
        lang_urls = build_lang_urls(department_url)
        if dept_name and lang_urls:
            rpage_urls[dept_name] = lang_urls
    return rpage_urls


class AnnouncementsSpider(scrapy.Spider):
    """
    爬取 Rpage 網頁公告的 Scrapy Spider。

    此 Spider 會針對設定的單位網址，爬取繁體中文和英文兩種語言版本的公告，
    並將公告標題和網址儲存下來。
    """

    name = "nthu_announcements"
    custom_settings = {
        "ITEM_PIPELINES": {"nthu_scraper.spiders.nthu_announcements.JsonPipeline": 1},
    }

    def __init__(self, *args, **kwargs):
        """
        初始化 Spider，載入單位網址。
        """
        super().__init__(*args, **kwargs)
        self.rpage_urls = {}
        # 從檔案載入
        self.rpage_urls = load_rpage_urls_from_directories(DIRECTORIES_PATH)
        # 加入其他資料
        self.rpage_urls.update(other_data)

    def start_requests(self):
        """
        Spider 的起始請求方法。

        為每個單位和語言版本建立 Scrapy Request，並指定 parse 方法作為回呼函數。
        """
        for dept, lang_urls in self.rpage_urls.items():
            for lang, url in lang_urls.items():
                yield scrapy.Request(
                    url,
                    callback=self.parse,
                    meta={
                        "department_name": dept,
                        "language": lang,
                        "original_url": url,
                    },
                )

    def parse(self, response):
        """
        解析網頁主頁的回呼函數。

        儲存網頁 HTML 內容，並尋找公告列表和 "more" 連結。

        Args:
            response: Scrapy Response 物件。
        """
        department = response.meta.get("department_name")
        language = response.meta.get("language")
        if response.css("div.tab-content"):
            self.logger.info(
                f"在 {department} ({language}) 找到 tab 模組: {response.url}"
            )
            yield from self.parse_tab_content(response, response.meta)

        yield from self.parse_more_links(response, response.meta)

    def parse_more_links(self, response, meta):
        """
        解析網頁中的 "more" 連結，並產生對應的 Scrapy Request。

        Args:
            response: Scrapy Response 物件。
            meta: 包含單位名稱和語言的字典。
        """
        department = response.meta.get("department_name")
        language = response.meta.get("language")
        more_links = response.css("p.more a")
        for a in more_links:
            relative_url = a.css("::attr(href)").get()
            if relative_url:
                self.logger.info(
                    f"在 {department} ({language}) 找到新的公告: {relative_url}"
                )
                absolute_url = response.urljoin(relative_url)
                # 更新動態載入的連結以包含語言查詢參數
                updated_url = _update_url_lang_param(absolute_url, meta.get("language"))
                if RPAGE_DOMAIN_SUFFIX in urlparse(updated_url).hostname:
                    new_meta = meta.copy()
                    new_meta["announcement_url"] = updated_url
                    yield scrapy.Request(
                        updated_url,
                        callback=self.parse_announcement_list,
                        meta=new_meta,
                    )

    def parse_tab_content(self, response, meta):
        """
        解析網頁中的 tab content，提取動態載入的公告連結。

        Args:
            response: Scrapy Response 物件。
            meta: 包含單位名稱和語言的字典。
        """
        tabpane = response.css("div.tab-pane")
        for tab in tabpane:
            tab_text = tab.xpath("string(.)").get()
            url_match = re.search(
                r"\$\.\s*hajaxOpenUrl\(\s*'([^']+)'", tab_text, re.DOTALL
            )
            if url_match:
                extracted_url = url_match.group(1)
                absolute_extracted_url = response.urljoin(extracted_url)
                # 更新動態載入的連結以包含語言查詢參數
                updated_extracted_url = _update_url_lang_param(
                    absolute_extracted_url, meta.get("language")
                )
                new_meta = meta.copy()
                # 再呼叫一次 parse，處理更多按鈕
                yield scrapy.Request(
                    updated_extracted_url,
                    callback=self.parse,
                    meta=new_meta,
                )

    def parse_announcement_list(self, response):
        """
        解析公告列表頁面，提取公告資訊並儲存。

        Args:
            response: Scrapy Response 物件。
        """
        announcement_item = AnnouncementItem()
        announcement_item["title"] = self.process_title(response)
        announcement_item["link"] = response.url
        announcement_item["language"] = response.meta.get("language")
        announcement_item["department"] = response.meta.get("department_name")
        announcement_item["articles"] = self.process_content(response)
        yield announcement_item

    def process_title(self, response):
        """
        從公告內頁提取公告標題。

        優先使用包含 "title" 字樣的 class，若找不到則使用網頁 title。

        Args:
            response: Scrapy Response 物件。

        Returns:
            公告標題字串，如果找不到標題則回傳 None。
        """
        title_div = response.css("[class*='title']::text").get()
        if title_div:
            title_div = title_div.strip()
            if title_div != "":
                return title_div

        head_title = response.css("title::text").get()
        if head_title:
            return head_title.strip()

        self.logger.warning(f"警告：在 {response.url} 找不到公告標題。")
        return None

    def process_content(self, response) -> list[AnnouncementArticle]:
        """
        解析公告列表頁面。

        此方法解析下載的公告列表頁面，使用 CSS selector 選取公告項目，
        並提取公告的標題、連結，最後產生 AnnouncementArticle。

        Args:
            response (scrapy.http.Response): 下載器返回的回應物件。

        Returns:
            list[AnnouncementArticle]: 包含解析出的公告文章資訊列表。
        """
        announcement_list_container = response.css("#pageptlist")
        announcements = announcement_list_container.css(
            ".row.listBS"
        )  # 選取每個公告的 row

        articles = []

        for announcement in announcements:
            article = AnnouncementArticle()
            # 提取標題
            link_selector = announcement.css(".mtitle a")  # 直接選取 mtitle 下的 a 標籤
            article["title"] = (
                link_selector.css("::text").get().strip() if link_selector else None
            )
            # 提取連結
            relative_link = (
                link_selector.css("::attr(href)").get() if link_selector else None
            )
            article["link"] = response.urljoin(relative_link) if relative_link else None
            # 提取日期
            date_selector = announcement.css(".mdate::text").get()
            article["date"] = self.process_date(date_selector)

            # 只有當文章有標題和單位時才加入列表
            if article.get("title"):
                articles.append(dict(article))

        return articles

    def process_date(self, date_text: str | None) -> str | None:
        """
        處理日期字串。

        此方法接收原始日期字串，移除前後空白並返回處理後的日期字串。
        若輸入為 None，則直接返回 None。

        Args:
            date_text (str | None): 原始日期字串。

        Returns:
            str | None: 處理後的日期字串，或 None。
        """
        if date_text is None:
            return None
        return date_text.strip()

    def process_link(self, link_selector, response) -> tuple[str | None, str | None]:
        """
        處理連結元素，提取標題與 href。

        此方法接收連結元素的 selector，提取連結文字作為標題，並提取 href 屬性作為連結。
        同時處理相對路徑，確保連結為絕對路徑。

        Args:
            link_selector: 連結元素的 CSS selector。
            response (scrapy.http.Response): 下載器返回的回應物件，用於處理相對路徑。

        Returns:
            tuple[str | None, str | None]: 包含標題和連結的 tuple。
        """
        title = link_selector.css("::text").get()
        href = link_selector.css("::attr(href)").get()

        if href:
            link = response.urljoin(href)
        else:
            link = None

        if title:
            title = title.strip() if title else None
            title = title.replace('"', "")  # 移除標題中的雙引號，避免 JSON 錯誤

        return title, link


class JsonPipeline:
    """
    Scrapy Pipeline，用於將爬取的 Item 儲存為 JSON 檔案。
    同時會合併所有公告資料到一個總合檔案。
    """

    def open_spider(self, spider):
        """
        Spider 開啟時執行，建立必要的資料夾與初始化列表。
        """
        COMBINED_JSON_FILE.parent.mkdir(parents=True, exist_ok=True)
        self.combined_data = []  # 初始化為一個空的列表

    def process_item(self, item, spider):
        """
        處理每一個 Item，儲存公告資料到 JSON 檔案。

        Args:
            item (AnnouncementItem): 爬取到的公告資料
            spider (AnnouncementsSpider): 爬蟲實例

        Returns:
            AnnouncementItem: 處理後的 Item
        """
        serializable_item = dict(item)
        spider.logger.info(f"✅ 成功儲存【{item['department']}/{item['title']}】資料")
        spider.logger.debug(serializable_item)
        self.combined_data.append(serializable_item)

        return item

    def close_spider(self, spider):
        """
        Spider 關閉時執行，合併所有公告資料到 JSON 總合檔案。
        """
        sorted_data = self.combined_data

        with open(COMBINED_JSON_FILE, "w", encoding="utf-8") as f:
            json.dump(sorted_data, f, ensure_ascii=False, indent=4)  # 直接 dump 列表
        spider.logger.info(f'✅ 成功儲存所有公告資料至 "{COMBINED_JSON_FILE}"')
