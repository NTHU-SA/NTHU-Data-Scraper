import pytest
from scrapy import Selector
from scrapy.http import HtmlResponse

from nthu_scraper.parsers import ParseError
from nthu_scraper.parsers.newsletters import (
    convert_chinese_month_to_english,
    newsletter_list_id,
    parse_archive_articles,
    parse_gallery_metadata,
    parse_metadata_table,
    parse_newsletter_date,
    parse_newsletter_list,
    parse_newsletter_sources,
    parse_popup_url,
)
from nthu_scraper.spiders import nthu_newsletters as newsletters
from nthu_scraper.spiders.nthu_newsletters import NewsletterPipeline, NewsletterSpider
from nthu_scraper.storage import read_json, write_json_atomic


def test_list_contract(fixture_text):
    page = Selector(text=fixture_text("newsletters", "list.html"))
    assert parse_newsletter_list(page) == [
        {
            "name": "清華電子報",
            "link": "https://newsletter.cc.nthu.edu.tw/archive/1",
            "details": {"發行單位": "計通中心", "週期": "每月"},
            "articles": [],
        },
        {
            "name": "校園快訊",
            "link": "https://newsletter.cc.nthu.edu.tw/archive/2",
            "details": {},
            "articles": [],
        },
    ]


def test_archive_contract(fixture_text):
    page = Selector(text=fixture_text("newsletters", "archive.html"))
    assert parse_archive_articles(page) == [
        {
            "title": "第一期",
            "link": "https://newsletter.cc.nthu.edu.tw/nthu-list/archive/1.html",
            "date": "2026-09-01",
        },
        {
            "title": "第二期",
            "link": "https://newsletter.cc.nthu.edu.tw/nthu-list/archive/2.html",
            "date": "2026-10-12",
        },
        {"title": "未標日期"},
    ]


@pytest.mark.parametrize(
    "month,english,number",
    [
        ("一月", "Jan", "01"),
        ("二月", "Feb", "02"),
        ("三月", "Mar", "03"),
        ("四月", "Apr", "04"),
        ("五月", "May", "05"),
        ("六月", "Jun", "06"),
        ("七月", "Jul", "07"),
        ("八月", "Aug", "08"),
        ("九月", "Sep", "09"),
        ("十月", "Oct", "10"),
        ("十一月", "Nov", "11"),
        ("十二月", "Dec", "12"),
    ],
)
def test_all_chinese_months(month, english, number):
    assert convert_chinese_month_to_english(f"01 {month} 2026") == f"01 {english} 2026"
    assert parse_newsletter_date(f" Sent on 01 {month} 2026 ") == f"2026-{number}-01"


@pytest.mark.parametrize(
    "date",
    [
        "",
        "unknown",
        "31 Feb 2026",
        "01 十三月 2026",
        "2026年02月29日",
        "2026年十三01日",
        "2026年13月01日",
        "2026年五32日",
    ],
)
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


def test_popup_url_handles_absolute_links_and_spaces():
    assert parse_popup_url("openpopup('https://example.test/issue one', 800)") == (
        "https://example.test/issue%20one"
    )
    with pytest.raises(ParseError, match="Invalid newsletter URL"):
        parse_popup_url("openpopup('javascript:alert(1)', 800)")


def test_newsletter_relative_links_use_response_base(html_response):
    page = html_response(
        '<div class="gallery"><li><h3><a href="issue one">News</a></h3></li></div>',
        url="https://newsletter.cc.nthu.edu.tw/archive/",
    )
    (request,) = NewsletterSpider().parse(page)
    assert request.url == "https://newsletter.cc.nthu.edu.tw/archive/issue%20one"
    assert request.meta["newsletter"]["link"] == request.url


def test_archive_href_uses_shared_normalization():
    page = Selector(
        text='<div id="acyarchivelisting"><table class="contentpane">'
        '<div class="archiveRow"><a href="issue one">News</a></div></table></div>'
    )
    assert parse_archive_articles(page, "https://example.test/archive/") == [
        {"title": "News", "link": "https://example.test/archive/issue%20one"}
    ]


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("29 Feb 2024", "2024-02-29"),
        ("Sent on 1 SEP 2026", "2026-09-01"),
        ("1   oct   2026", "2026-10-01"),
    ],
)
def test_english_dates(raw, expected):
    assert parse_newsletter_date(raw) == expected


def test_empty_structures(fixture_text):
    assert (
        parse_newsletter_list(Selector(text='<div class="gallery"><ul></ul></div>'))
        == []
    )
    assert parse_metadata_table(Selector(text="<table></table>")) == {}
    assert (
        parse_archive_articles(
            Selector(text=fixture_text("newsletters", "empty-archive.html"))
        )
        == []
    )


@pytest.mark.parametrize(
    "html",
    [
        "<html>Unavailable</html>",
        '<div class="gallery"><section>Redesigned</section></div>',
        '<div class="gallery"><li>No heading</li></div>',
        '<div class="gallery"><li><h3><a>No href</a></h3></li></div>',
        '<div class="gallery"><li><h3><a href="/archive"> </a></h3></li></div>',
        '<div class="gallery"><li><h3><a href="/archive">Name</a></h3><table><tr><td>Key</td></tr></table></li></div>',
    ],
)
def test_missing_or_broken_list(html):
    with pytest.raises(ParseError):
        parse_newsletter_list(Selector(text=html))


@pytest.mark.parametrize(
    "html",
    [
        "<html>Unavailable</html>",
        '<div id="acyarchivelisting"></div>',
        '<div id="acyarchivelisting"><table class="contentpane"></table></div>',
        '<div id="acyarchivelisting"><table class="contentpane"><tr><td></td></tr></table></div>',
        '<div id="acyarchivelisting"><div class="acypagination_counter">No results</div></div>',
        '<div id="acyarchivelisting"><table class="contentpane"><div class="acypagination_counter">Results 1 - 20</div></table></div>',
        '<div id="acyarchivelisting"><table class="contentpane"><div class="archiveRow">No title</div></table></div>',
        '<div id="acyarchivelisting"><table class="contentpane"><tr><td>Redesigned</td></tr></table></div>',
        '<div id="acyarchivelisting"><table class="contentpane"><div class="archiveRow"><a onclick="broken()">Title</a></div></table></div>',
        '<div id="acyarchivelisting"><table class="contentpane"><div class="archiveRow"><a>Title</a><span class="sentondate">bad date</span></div></table></div>',
    ],
)
def test_missing_or_broken_archive(html):
    with pytest.raises(ParseError):
        parse_archive_articles(Selector(text=html))


def test_empty_metadata_values_remain_optional():
    table = Selector(
        text="<table><tr><td>Empty</td><td></td></tr><tr><td></td><td>Value</td></tr></table>"
    )
    assert parse_metadata_table(table) == {}


def test_callbacks_without_network(fixture_text, html_response):
    spider = NewsletterSpider()
    page = html_response(fixture_text("newsletters", "list.html"))
    requests = list(spider.parse(page))
    assert len(requests) == 2
    assert list(spider.parse(page)) == []
    for request in requests:
        assert request.errback == spider.handle_request_error
        archive = html_response(
            fixture_text("newsletters", "archive.html"),
            url=request.url,
            meta=request.meta,
        )
        (item,) = spider.parse_newsletter_content(archive)
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


def test_processed_urls_and_completeness_are_instance_local(
    fixture_text, html_response
):
    page = html_response(fixture_text("newsletters", "list.html"))
    first = NewsletterSpider()
    first_urls = [request.url for request in first.parse(page)]
    first.mark_incomplete("First run failed")
    second = NewsletterSpider()
    assert second.processed_urls == set()
    assert not second.crawl_incomplete
    assert [request.url for request in second.parse(page)] == first_urls
    assert list(first.parse(page)) == []
    assert list(second.parse(page)) == []
    second.processed_urls.clear()
    assert first.processed_urls == set(first_urls)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Sent on 2026年10月02日", "2026-10-02"),
        ("2026年9月30日", "2026-09-30"),
        ("Sent on 2026年五29日", "2026-05-29"),
        ("2024年二月29日", "2024-02-29"),
        ("2026年十一01日", "2026-11-01"),
        ("2026年十二31日", "2026-12-31"),
    ],
)
def test_localized_dates(raw, expected):
    assert parse_newsletter_date(raw) == expected


def test_big5_metadata_gallery_and_shared_management(fixture_text):
    text = fixture_text("newsletters", "metadata-gallery.html")
    page = HtmlResponse(
        url="https://newsletter.cc.nthu.edu.tw/search.html",
        body=(
            '<meta http-equiv="Content-Type" content="text/html; charset=big5">' + text
        ).encode("big5"),
    )
    metadata = parse_gallery_metadata(page, page.url)
    assert set(metadata) == {"112", "111", "114", "85"}
    assert metadata["112"] == {
        "管理者": "範例管理者",
        "管理單位": "英語教學精進中心",
        "電子信箱": "example@nthu.edu.tw",
        "聯絡電話": "35452",
    }
    assert metadata["111"] == metadata["114"] == metadata["112"]
    metadata["111"]["管理者"] = "Changed"
    assert metadata["112"]["管理者"] == "範例管理者"


def test_current_archives_keep_first_page_contract(fixture_text, html_response):
    page = html_response(
        fixture_text("newsletters", "redesigned-archive.html"),
        meta={"newsletter": {"name": "News"}},
    )
    spider = NewsletterSpider()
    (item,) = spider.parse_newsletter_content(page)
    assert item["articles"] == [
        {
            "title": "2026 新生十月秋聚",
            "link": "https://newsletter.cc.nthu.edu.tw/index.php/home-zh-tw/list/listid-35/mailid-5875-2026?tmpl=component&tmpl=component",
            "date": "2026-10-02",
        },
        {
            "title": "五月電子報",
            "link": "https://newsletter.cc.nthu.edu.tw/index.php/home-zh-tw/list/listid-35/mailid-5600?tmpl=component",
            "date": "2026-05-29",
        },
    ]
    assert not spider.crawl_incomplete


def test_redesigned_crawl_publishes_fresh_metadata_and_explicit_empty(
    fixture_text, html_response, tmp_path, monkeypatch
):
    path = tmp_path / "newsletters.json"
    write_json_atomic([{"name": "old", "details": {"管理者": "Stale"}}], path)
    monkeypatch.setattr(newsletters, "NEWSLETTERS_JSON_PATH", path)
    spider = NewsletterSpider()
    pipeline = NewsletterPipeline()
    pipeline.open_spider(spider)
    wrapper = html_response(
        fixture_text("newsletters", "wrapper.html"), url=spider.start_urls[0]
    )
    (gallery_request,) = spider.parse(wrapper)
    assert gallery_request.url == "https://newsletter.cc.nthu.edu.tw/search.html"
    assert gallery_request.errback == spider.handle_request_error
    gallery = html_response(
        fixture_text("newsletters", "metadata-gallery.html"),
        url=gallery_request.url,
        meta=gallery_request.meta,
    )
    (list_request,) = gallery_request.callback(gallery)
    assert (
        list_request.url
        == "https://newsletter.cc.nthu.edu.tw/index.php/home-zh-tw/list/lists/listing"
    )
    assert list_request.errback == spider.handle_request_error
    listing = html_response(
        fixture_text("newsletters", "redesigned-list.html"),
        url=list_request.url,
        meta=list_request.meta,
    )
    archive_requests = list(list_request.callback(listing))
    assert len(archive_requests) == 4
    assert [newsletter_list_id(r.url) for r in archive_requests] == [
        "112",
        "111",
        "114",
        "180",
    ]
    for request in archive_requests:
        assert request.errback == spider.handle_request_error
        fixture = (
            "empty-archive.html"
            if newsletter_list_id(request.url) == "180"
            else "redesigned-archive.html"
        )
        archive = html_response(
            fixture_text("newsletters", fixture), url=request.url, meta=request.meta
        )
        (item,) = request.callback(archive)
        pipeline.process_item(item, spider)
    pipeline.close_spider(spider)
    data = read_json(path)
    assert len(data) == 4
    empty = next(item for item in data if newsletter_list_id(item["link"]) == "180")
    assert empty == {
        "name": "大學部115級",
        "link": "https://newsletter.cc.nthu.edu.tw/index.php/home-zh-tw/list/listid-180-da-xue-bu115ji",
        "details": {},
        "articles": [],
    }
    assert all(
        item["details"]["管理者"] == "範例管理者" for item in data if item is not empty
    )
    assert not spider.crawl_incomplete


@pytest.mark.parametrize("stage", ["wrapper", "gallery", "listing", "archive"])
def test_redesigned_structure_failures_retain_baseline(
    stage, html_response, tmp_path, monkeypatch
):
    path = tmp_path / "newsletters.json"
    write_json_atomic([{"name": "old"}], path)
    original = path.read_bytes()
    monkeypatch.setattr(newsletters, "NEWSLETTERS_JSON_PATH", path)
    spider = NewsletterSpider()
    pipeline = NewsletterPipeline()
    pipeline.open_spider(spider)
    pipeline.process_item({"name": "valid sibling", "articles": []}, spider)
    html = {
        "wrapper": '<div class="com-wrapper"><iframe id="blockrandom" src="/search.html"></iframe></div>',
        "gallery": '<div class="gallery"></div>',
        "listing": '<div id="acylistslisting"><div class="acymailing_list"><div class="list_name">Broken</div></div></div>',
        "archive": '<div id="acyarchivelisting"><table class="contentpane"></table></div>',
    }[stage]
    page = html_response(
        html,
        meta={
            "newsletter": {"name": "News"},
            "listing_url": "https://newsletter.cc.nthu.edu.tw/list",
        },
    )
    callback = (
        spider.parse_gallery
        if stage == "gallery"
        else spider.parse_newsletter_content
        if stage == "archive"
        else spider.parse
    )
    assert list(callback(page)) == []
    pipeline.close_spider(spider)
    assert spider.crawl_incomplete
    assert path.read_bytes() == original


@pytest.mark.parametrize(
    "target", ["https://example.test/search.html", "javascript:alert(1)"]
)
def test_wrapper_rejects_invalid_sources(target):
    page = Selector(
        text=f'<div class="com-wrapper"><iframe id="blockrandom" src="{target}"></iframe></div>'
        '<a href="/index.php/home-zh-tw/list/lists/listing">Lists</a>'
    )
    with pytest.raises(ParseError):
        parse_newsletter_sources(page, "https://newsletter.cc.nthu.edu.tw/")


def test_start_uses_strict_wrapper_callback():
    spider = NewsletterSpider()
    with pytest.raises(StopIteration) as yielded:
        spider.start().__anext__().send(None)
    request = yielded.value.value
    assert request.url == spider.start_urls[0]
    assert request.callback == spider.parse_wrapper
    assert request.errback == spider.handle_request_error


def test_redirect_to_wrong_known_structure_is_incomplete(fixture_text, html_response):
    spider = NewsletterSpider()
    gallery = html_response(fixture_text("newsletters", "metadata-gallery.html"))
    assert list(spider.parse_wrapper(gallery)) == []
    assert spider.crawl_incomplete
    spider = NewsletterSpider()
    assert list(spider.parse_listing(gallery)) == []
    assert spider.crawl_incomplete


def test_conflicting_gallery_metadata_is_rejected():
    page = Selector(
        text='<div class="gallery"><li><h3><a href="/listid-1">One</a></h3>'
        "<table><tr><td>Manager</td><td>First</td></tr></table></li>"
        '<li><h3><a href="/listid-1-other">Other</a></h3>'
        "<table><tr><td>Manager</td><td>Second</td></tr></table></li></div>"
    )
    with pytest.raises(ParseError, match="Conflicting newsletter metadata"):
        parse_gallery_metadata(page, "https://newsletter.cc.nthu.edu.tw/")


@pytest.mark.parametrize(
    "html",
    [
        '<div id="acylistslisting"></div>',
        '<div id="acylistslisting"><div class="acymailing_list"><div class="list_name">'
        '<a href="https://example.test/listid-1">Wrong host</a></div></div></div>',
        '<div id="acylistslisting"><div class="acymailing_list"><div class="list_name">'
        '<a href="/listid-1">One</a><a href="/listid-2">Two</a></div></div></div>',
    ],
)
def test_invalid_official_lists_are_rejected(html):
    with pytest.raises(ParseError):
        parse_newsletter_list(Selector(text=html))
