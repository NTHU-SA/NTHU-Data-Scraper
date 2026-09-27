import pytest
from scrapy import Selector

from nthu_scraper.parsers import ParseError
from nthu_scraper.parsers.newsletters import (
    convert_chinese_month_to_english,
    parse_archive_articles,
    parse_metadata_table,
    parse_newsletter_date,
    parse_newsletter_list,
    parse_popup_url,
)
from nthu_scraper.spiders.nthu_newsletters import NewsletterSpider


def test_list_contract(fixture_text):
    page = Selector(text=fixture_text("newsletters", "list.html"))
    assert parse_newsletter_list(page) == [
        {"name": "清華電子報", "link": "https://newsletter.cc.nthu.edu.tw/archive/1",
         "details": {"發行單位": "計通中心", "週期": "每月"}, "articles": []},
        {"name": "校園快訊", "link": "https://newsletter.cc.nthu.edu.tw/archive/2",
         "details": {}, "articles": []},
    ]


def test_archive_contract(fixture_text):
    page = Selector(text=fixture_text("newsletters", "archive.html"))
    assert parse_archive_articles(page) == [
        {"title": "第一期", "link": "https://newsletter.cc.nthu.edu.tw/nthu-list/archive/1.html", "date": "2026-09-01"},
        {"title": "第二期", "link": "https://newsletter.cc.nthu.edu.tw/nthu-list/archive/2.html", "date": "2026-10-12"},
        {"title": "未標日期"},
    ]


@pytest.mark.parametrize("month,english,number", [
    ("一月", "Jan", "01"), ("二月", "Feb", "02"), ("三月", "Mar", "03"),
    ("四月", "Apr", "04"), ("五月", "May", "05"), ("六月", "Jun", "06"),
    ("七月", "Jul", "07"), ("八月", "Aug", "08"), ("九月", "Sep", "09"),
    ("十月", "Oct", "10"), ("十一月", "Nov", "11"), ("十二月", "Dec", "12"),
])
def test_all_chinese_months(month, english, number):
    assert convert_chinese_month_to_english(f"01 {month} 2026") == f"01 {english} 2026"
    assert parse_newsletter_date(f" Sent on 01 {month} 2026 ") == f"2026-{number}-01"


@pytest.mark.parametrize("date", ["", "unknown", "31 Feb 2026", "01 十三月 2026"])
def test_invalid_dates_are_explicit(date):
    with pytest.raises(ParseError):
        parse_newsletter_date(date)


def test_popup_url():
    assert parse_popup_url("openpopup('/archive/1?lang=zh', 800)") == (
        "https://newsletter.cc.nthu.edu.tw/archive/1?lang=zh"
    )
    with pytest.raises(ParseError):
        parse_popup_url("unrecognized('/archive/1')")
    with pytest.raises(ParseError):
        parse_popup_url("openpopup('', 800)")


@pytest.mark.parametrize("raw,expected", [
    ("29 Feb 2024", "2024-02-29"), ("Sent on 1 SEP 2026", "2026-09-01"),
    ("1   oct   2026", "2026-10-01"),
])
def test_english_dates(raw, expected):
    assert parse_newsletter_date(raw) == expected


def test_empty_structures():
    assert parse_newsletter_list(Selector(text='<div class="gallery"><ul></ul></div>')) == []
    assert parse_metadata_table(Selector(text="<table></table>")) == {}
    assert parse_archive_articles(Selector(text='<div id="acyarchivelisting"><table class="contentpane"></table></div>')) == []
    assert parse_archive_articles(Selector(text='<div id="acyarchivelisting"><table class="contentpane"><tr><td></td></tr></table></div>')) == []


@pytest.mark.parametrize("html", [
    "<html>Unavailable</html>",
    '<div class="gallery"><section>Redesigned</section></div>',
    '<div class="gallery"><li>No heading</li></div>',
    '<div class="gallery"><li><h3><a>No href</a></h3></li></div>',
    '<div class="gallery"><li><h3><a href="/archive"> </a></h3></li></div>',
    '<div class="gallery"><li><h3><a href="/archive">Name</a></h3><table><tr><td>Key</td></tr></table></li></div>',
])
def test_missing_or_broken_list(html):
    with pytest.raises(ParseError):
        parse_newsletter_list(Selector(text=html))


@pytest.mark.parametrize("html", [
    "<html>Unavailable</html>", '<div id="acyarchivelisting"></div>',
    '<div id="acyarchivelisting"><table class="contentpane"><div class="archiveRow">No title</div></table></div>',
    '<div id="acyarchivelisting"><table class="contentpane"><tr><td>Redesigned</td></tr></table></div>',
    '<div id="acyarchivelisting"><table class="contentpane"><div class="archiveRow"><a onclick="broken()">Title</a></div></table></div>',
    '<div id="acyarchivelisting"><table class="contentpane"><div class="archiveRow"><a>Title</a><span class="sentondate">bad date</span></div></table></div>',
])
def test_missing_or_broken_archive(html):
    with pytest.raises(ParseError):
        parse_archive_articles(Selector(text=html))


def test_empty_metadata_values_remain_optional():
    table = Selector(text="<table><tr><td>Empty</td><td></td></tr><tr><td></td><td>Value</td></tr></table>")
    assert parse_metadata_table(table) == {}


def test_callbacks_without_network(fixture_text, html_response):
    spider = NewsletterSpider()
    page = html_response(fixture_text("newsletters", "list.html"))
    requests = list(spider.parse(page))
    assert len(requests) == 2
    assert list(spider.parse(page)) == []
    for request in requests:
        assert request.errback == spider.handle_request_error
        archive = html_response(fixture_text("newsletters", "archive.html"), url=request.url, meta=request.meta)
        item, = spider.parse_newsletter_content(archive)
        assert dict(item) == {
            **parse_newsletter_list(page)[requests.index(request)],
            "articles": parse_archive_articles(archive),
        }
    assert not spider.crawl_incomplete


def test_bad_date_marks_whole_dataset_incomplete(html_response):
    spider = NewsletterSpider()
    page = html_response(
        '<div id="acyarchivelisting"><table class="contentpane"><div class="archiveRow">'
        '<a>Title</a><span class="sentondate">bad date</span></div></table></div>',
        meta={"newsletter": {"name": "News"}},
    )
    assert list(spider.parse_newsletter_content(page)) == []
    assert spider.crawl_incomplete
