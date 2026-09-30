import pytest
from scrapy import Selector

from nthu_scraper.parsers import ParseError
from nthu_scraper.parsers.announcements import (
    normalize_list_url,
    parse_articles,
    parse_list_page,
    parse_more_links,
)
from nthu_scraper.spiders import nthu_announcements_item as item_spider
from nthu_scraper.spiders import nthu_announcements_list as list_spider


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


def test_item_callback_uses_authoritative_metadata(
    monkeypatch, fixture_text, html_response
):
    monkeypatch.setattr(
        item_spider.AnnouncementsItemSpider, "_load_announcement_list", lambda self: []
    )
    spider = item_spider.AnnouncementsItemSpider()
    page = html_response(
        fixture_text("announcements", "rows.html"),
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


def test_list_spider_without_chromium(monkeypatch, fixture_text, html_response):
    monkeypatch.setattr(
        list_spider.AnnouncementsListSpider, "_load_department_urls", lambda self: {}
    )
    monkeypatch.setattr(
        list_spider.AnnouncementsListSpider, "_load_existing_links", lambda self: set()
    )
    spider = list_spider.AnnouncementsListSpider()
    page = html_response(
        fixture_text("announcements", "rows.html"),
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
        "title": "校園公告",
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
