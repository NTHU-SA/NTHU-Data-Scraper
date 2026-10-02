import pytest
import scrapy
from scrapy import Selector

from nthu_scraper.parsers import ParseError
from nthu_scraper.parsers.announcements import (
    normalize_announcement_text,
    normalize_list_url,
    parse_articles,
    parse_list_page,
    parse_more_links,
)
from nthu_scraper.spiders import nthu_announcements_item as item_spider
from nthu_scraper.spiders import nthu_announcements_list as list_spider
from nthu_scraper.storage import read_json, write_json_atomic


def test_rows_contract(fixture_text, html_response):
    page = html_response(fixture_text("announcements", "rows.html"))
    assert parse_articles(page, page.url).articles == [
        {
            "title": "開學公告",
            "link": "https://example.test/article/1",
            "date": "2026-09-01",
        },
        {"title": "活動", "link": "https://example.test/article/2", "date": None},
    ]
    assert parse_list_page(page) == {"title": "校園公告", "has_content": True}


def test_fallback_table_contract(fixture_text, html_response):
    page = html_response(fixture_text("announcements", "table.html"))
    assert parse_articles(page, page.url).articles == [
        {
            "title": "圖書館公告",
            "link": "https://example.test/p/article.php?id=3",
            "date": "2026/09/02",
        }
    ]
    assert parse_list_page(page) == {"title": "Table notices", "has_content": True}


def test_more_links(fixture_text):
    page = Selector(text=fixture_text("announcements", "rows.html"))
    assert parse_more_links(page, "http://dept.site.nthu.edu.tw/", "en") == [
        "https://dept.site.nthu.edu.tw/p/list.php?Lang=en&page=2",
        "https://dept.site.nthu.edu.tw/news?Lang=en",
    ]
    assert (
        parse_more_links(Selector(text="<p>No lists</p>"), "https://example.test", "en")
        == []
    )


def test_more_links_repair_spaces_and_skip_invalid_siblings(caplog):
    page = Selector(
        text='<p class="more"><a href="/news page">Good</a>'
        '<a href="javascript:alert(1)">Bad</a></p>'
    )
    assert parse_more_links(page, "https://dept.site.nthu.edu.tw/", "en") == [
        "https://dept.site.nthu.edu.tw/news%20page?Lang=en"
    ]
    assert "Skipping invalid announcement list URL" in caplog.text


@pytest.mark.parametrize(
    "url,expected",
    [
        (
            " http://dept.site.nthu.edu.tw/p?Lang=en ",
            "https://dept.site.nthu.edu.tw/p?Lang=en",
        ),
        ("//dept.site.nthu.edu.tw/", "https://dept.site.nthu.edu.tw/"),
        ("https://dept.site.nthu.edu.tw/", "https://dept.site.nthu.edu.tw/"),
        ("https://example.test/", None),
        ("", None),
        ("/relative", None),
    ],
)
def test_url_normalization(url, expected):
    assert normalize_list_url(url) == expected


def test_empty_container(fixture_text):
    page = Selector(text=fixture_text("announcements", "empty.html"))
    result = parse_articles(page, "https://example.test")
    assert result.articles == []
    assert result.rejected_count == 0
    assert parse_list_page(page) == {"title": "Announcements", "has_content": False}


@pytest.mark.parametrize(
    "html",
    [
        "<html>Unavailable</html>",
        '<div id="pageptlist"><section>Redesigned</section></div>',
        '<div id="pageptlist"><div class="row listBS">Missing anchor</div></div>',
        '<div id="pageptlist"><div class="row listBS"><div class="mtitle"><a href="/a"> </a></div></div></div>',
        '<div id="pageptlist"><div class="row listBS"><div class="mtitle"><a>No href</a></div></div></div>',
    ],
)
def test_broken_articles_raise(html):
    with pytest.raises(ParseError):
        parse_articles(Selector(text=html), "https://example.test")


def test_missing_list_container_raises():
    with pytest.raises(ParseError):
        parse_list_page(Selector(text="<title>Unavailable</title>"))


@pytest.mark.parametrize("content", ["Unavailable", "<section>Redesigned</section>"])
def test_redesigned_list_is_not_empty(content):
    page = Selector(text=f'<div id="pageptlist">{content}</div>')
    with pytest.raises(ParseError):
        parse_articles(page, "https://example.test")
    with pytest.raises(ParseError):
        parse_list_page(page)


def test_whitespace_title_falls_back():
    page = Selector(
        text='<title>Fallback</title><h2 class="title"> </h2><div id="pageptlist"></div>'
    )
    assert parse_list_page(page)["title"] == "Fallback"


def test_list_title_uses_announcement_module(fixture_text):
    page = Selector(text=fixture_text("announcements", "search_module.html"))
    assert parse_list_page(page) == {"title": "NEWS", "has_content": True}


def test_alumni_list_title_uses_current_page_breadcrumb(fixture_text, html_response):
    page = html_response(
        fixture_text("announcements", "alumni.html"),
        url="https://alumni.site.nthu.edu.tw/p/403-1346-4272-1.php?Lang=zh-tw",
    )
    assert parse_list_page(page) == {"title": "最新消息", "has_content": True}


@pytest.mark.parametrize(
    "breadcrumb",
    [
        '<li class="active"> News <span>- Events</span> </li>',
        '<li><a aria-current="page"> News <span>- Events</span> </a></li>',
    ],
)
def test_breadcrumb_title_preserves_nested_text_and_hyphens(breadcrumb):
    page = Selector(
        text='<title>News - Events - Site</title><div class="module module-path">'
        f'<ol class="breadcrumb"><li>Home</li>{breadcrumb}</ol></div>'
        '<div id="pageptlist"></div>'
    )
    assert parse_list_page(page)["title"] == "News - Events"


@pytest.mark.parametrize(
    "heading",
    [
        '<div class="module"><header><h2 class="mt-title">Notices</h2></header>'
        '<div id="pageptlist"></div></div>',
        '<h1 class="section-title">Notices</h1><div id="pageptlist"></div>',
    ],
)
def test_list_heading_takes_priority_over_breadcrumb(heading):
    page = Selector(
        text='<title>Site</title><div class="module module-path">'
        '<ol class="breadcrumb"><li class="active">Category</li></ol></div>'
        f"{heading}"
    )
    assert parse_list_page(page)["title"] == "Notices"


@pytest.mark.parametrize(
    "breadcrumb",
    [
        '<li class="active"> <span> </span> </li>',
        "<li>Home</li>",
    ],
)
def test_unusable_breadcrumb_falls_back_to_document_title(breadcrumb):
    page = Selector(
        text='<title>News - Events</title><div class="module module-path">'
        f'<ol class="breadcrumb">{breadcrumb}</ol></div>'
        '<div id="pageptlist"></div>'
    )
    assert parse_list_page(page)["title"] == "News - Events"


def test_list_title_fallback_ignores_search_and_article_titles():
    page = Selector(
        text='<title>News</title><div class="module">'
        '<h2 class="section-title">Search</h2></div>'
        '<div id="pageptlist"><div class="row listBS">'
        '<div class="mtitle"><a href="/article"><h2 class="section-title">'
        "Article</h2></a></div></div></div>"
    )
    assert parse_list_page(page)["title"] == "News"


def test_list_with_no_usable_title_raises():
    with pytest.raises(ParseError, match="no usable list title"):
        parse_list_page(Selector(text='<div id="pageptlist"></div>'))


@pytest.mark.parametrize("heading", ["", " \t\n ", "<span> </span>"])
def test_empty_module_title_falls_back(heading):
    page = Selector(
        text=f'<title>News</title><div class="module">'
        f'<header><h2 class="mt-title">{heading}</h2></header>'
        '<div id="pageptlist"></div></div>'
    )
    assert parse_list_page(page)["title"] == "News"


@pytest.mark.parametrize(
    "separator", ["\x0b", "\x0c", "\x1f", "\x7f", "\x85", "\xa0", "\u3000"]
)
def test_announcement_text_normalizes_controls_and_unicode_whitespace(separator):
    assert (
        normalize_announcement_text(f"{separator}News{separator}  Items{separator}")
        == "News Items"
    )
    assert normalize_announcement_text("清華【公告】—NEWS") == "清華【公告】—NEWS"
    assert normalize_announcement_text(r"literal\u000b") == r"literal\u000b"


def test_title_and_date_normalization():
    page = Selector(
        text='<title>  News\x0b Items </title><div id="pageptlist">'
        '<div class="row listBS"><div class="mtitle">'
        '<a href="/article"> "\x0bNew <span>article</span>\xa0title" </a></div>'
        '<span class="mdate">\x0b 2026/10/03 \x0c</span></div></div>'
    )
    assert parse_list_page(page)["title"] == "News Items"
    assert parse_articles(page, "https://example.test").articles == [
        {
            "title": "New article title",
            "link": "https://example.test/article",
            "date": "2026/10/03",
        }
    ]


@pytest.mark.parametrize("fixture", ["rows.html", "alumni.html", "search_module.html"])
def test_item_callback_preserves_authoritative_source_title_and_metadata(
    monkeypatch, fixture_text, html_response, fixture
):
    monkeypatch.setattr(
        item_spider.AnnouncementsItemSpider, "_load_announcement_list", lambda self: []
    )
    spider = item_spider.AnnouncementsItemSpider()
    page = html_response(
        fixture_text("announcements", fixture),
        meta={
            "title": "Source",
            "source_link": "https://example.test/original",
            "department": "Dept",
            "language": "en",
        },
    )
    (item,) = spider.parse(page)
    assert dict(item) == {
        "title": "Source",
        "link": "https://example.test/original",
        "department": "Dept",
        "language": "en",
        "articles": parse_articles(page, page.url).articles,
    }


@pytest.mark.parametrize("custom", [False, True])
def test_item_title_comes_only_from_source_even_without_page_title(
    monkeypatch, html_response, custom
):
    monkeypatch.setattr(
        item_spider.AnnouncementsItemSpider, "_load_announcement_list", lambda self: []
    )
    source_link = (
        list_spider.CUSTOM_ANNOUNCEMENT_SOURCES[0]["link"]
        if custom
        else "https://example.test/list"
    )
    page = html_response(
        '<div id="pageptlist"><div class="row listBS">'
        '<div class="mtitle"><a href="/article">Article</a></div></div></div>',
        meta={
            "title": "Old\x0b title",
            "source_link": source_link,
            "department": "Dept",
            "language": "en",
        },
    )
    (item,) = item_spider.AnnouncementsItemSpider().parse(page)
    assert item["title"] == "Old\x0b title"


@pytest.mark.parametrize("title", [None, "", " \t\n ", 123, "\x00", "News\x00Items"])
def test_item_spider_rejects_unusable_authoritative_title(tmp_path, monkeypatch, title):
    path = tmp_path / "announcements_list.json"
    monkeypatch.setattr(item_spider, "ANNOUNCEMENTS_LIST_PATH", path)
    write_json_atomic([{"title": title, "link": "https://example.test/list"}], path)
    with pytest.raises(ValueError, match="Invalid authoritative announcements_list"):
        item_spider.AnnouncementsItemSpider()


def test_list_pipeline_updates_titles_preserving_failed_and_custom_sources(
    tmp_path, monkeypatch
):
    path = tmp_path / "announcements_list.json"
    monkeypatch.setattr(list_spider, "ANNOUNCEMENTS_LIST_PATH", path)
    source = {
        "title": "Search",
        "link": "https://example.test/list",
        "department": "Dept",
        "language": "en",
    }
    untouched = {**source, "link": "https://example.test/failed", "title": "Retained"}
    custom = {**list_spider.CUSTOM_ANNOUNCEMENT_SOURCES[0], "title": "Wrong"}
    write_json_atomic([source, untouched, custom], path)
    spider = scrapy.Spider("test")
    pipeline = list_spider.AnnouncementListPipeline()
    pipeline.open_spider(spider)
    for title in ("NEWS", "NEWS", None):
        pipeline.process_item(
            list_spider.AnnouncementListItem({**source, "title": title}), spider
        )
    new = {**source, "link": "https://example.test/new", "title": "New"}
    pipeline.process_item(list_spider.AnnouncementListItem(new), spider)
    pipeline.process_item(
        list_spider.AnnouncementListItem({**new, "title": "Updated"}), spider
    )
    pipeline.close_spider(spider)
    result = {item["link"]: item for item in read_json(path)}
    assert result[source["link"]] == {**source, "title": "NEWS"}
    assert result[untouched["link"]] == untouched
    assert result[new["link"]] == {**new, "title": "Updated"}
    assert result[custom["link"]] == list_spider.CUSTOM_ANNOUNCEMENT_SOURCES[0]
    assert len(result) == 3 + len(list_spider.CUSTOM_ANNOUNCEMENT_SOURCES)


def test_content_refresh_leaves_source_list_unchanged(
    tmp_path, monkeypatch, fixture_text, html_response
):
    source_path = tmp_path / "announcements_list.json"
    aggregate_path = tmp_path / "announcements.json"
    folder = tmp_path / "announcements"
    monkeypatch.setattr(item_spider, "ANNOUNCEMENTS_LIST_PATH", source_path)
    monkeypatch.setattr(item_spider, "ANNOUNCEMENTS_JSON_PATH", aggregate_path)
    monkeypatch.setattr(item_spider, "ANNOUNCEMENTS_FOLDER", folder)
    source = {
        "title": "Search",
        "link": "https://example.test/list",
        "department": "Dept",
        "language": "en",
    }
    write_json_atomic([source], source_path)
    before = source_path.read_bytes()
    spider = item_spider.AnnouncementsItemSpider()
    pipeline = item_spider.AnnouncementItemPipeline()
    pipeline.open_spider(spider)
    page = html_response(
        fixture_text("announcements", "search_module.html"),
        meta={**source, "source_link": source["link"]},
    )
    (item,) = spider.parse(page)
    pipeline.process_item(item, spider)
    pipeline.close_spider(spider)
    assert source_path.read_bytes() == before
    (saved,) = read_json(aggregate_path)
    assert saved["title"] == source["title"]
    assert read_json(folder / "Dept" / "Search_en.json") == saved


@pytest.mark.parametrize(
    "fixture,expected_title",
    [("rows.html", "校園公告"), ("alumni.html", "最新消息")],
)
def test_list_spider_without_chromium(
    monkeypatch, fixture_text, html_response, fixture, expected_title
):
    monkeypatch.setattr(
        list_spider.AnnouncementsListSpider, "_load_department_urls", lambda self: {}
    )
    monkeypatch.setattr(
        list_spider.AnnouncementsListSpider, "_load_existing_links", lambda self: set()
    )
    spider = list_spider.AnnouncementsListSpider()
    page = html_response(
        fixture_text("announcements", fixture),
        url="https://dept.site.nthu.edu.tw/",
        meta={"language": "en", "department": "Dept"},
    )
    requests = list(spider.parse(page))
    assert [request.url for request in requests] == parse_more_links(
        page, page.url, "en"
    )
    assert all(request.meta["playwright"] for request in requests)
    assert list(spider.parse(page)) == []
    (item,) = spider.parse_announcement_list(page)
    assert dict(item) == {
        "title": expected_title,
        "link": page.url,
        "language": "en",
        "department": "Dept",
    }


def test_parser_implementation_errors_propagate(monkeypatch, html_response):
    monkeypatch.setattr(
        item_spider.AnnouncementsItemSpider, "_load_announcement_list", lambda self: []
    )

    def broken(*args):
        raise ValueError("implementation regression")

    monkeypatch.setattr(item_spider, "parse_articles", broken)
    with pytest.raises(ValueError, match="implementation regression"):
        list(
            item_spider.AnnouncementsItemSpider().parse(html_response("<html></html>"))
        )
