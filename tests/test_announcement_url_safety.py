from html import escape

import pytest
import scrapy
from scrapy.http import HtmlResponse

from nthu_scraper.parsers.announcements import parse_articles
from nthu_scraper.spiders import nthu_announcements_item as announcements
from nthu_scraper.storage import read_json, write_json_atomic
from nthu_scraper.utils.url_utils import http_url_error

NVIDIA_URL = (
    "https://www.nvidia.com/gtc/?ncid=GTC-NV09OS1T]"
    "(https://www.nvidia.com/gtc/?ncid=GTC-NV09OS1T"
)
SOURCE_URL = "https://example.test/list"
SOURCE = {
    "title": "Notices",
    "link": SOURCE_URL,
    "language": "en",
    "department": "Department",
}
GOOD_ARTICLE = {
    "title": "Old good",
    "link": "https://example.test/old",
    "date": None,
    "extra": "preserved",
}
BAD_ARTICLE = {"title": "NVIDIA GTC", "link": NVIDIA_URL, "date": None}


def row(link, title="Article"):
    return (
        '<div class="row listBS"><div class="mtitle">'
        f'<a href="{escape(link, quote=True)}">{escape(title)}</a>'
        "</div></div>"
    )


def response(body):
    return HtmlResponse(
        SOURCE_URL,
        body=body.encode(),
        encoding="utf-8",
        request=scrapy.Request(SOURCE_URL, meta={**SOURCE, "source_link": SOURCE_URL}),
    )


@pytest.mark.parametrize(
    "url",
    [
        NVIDIA_URL,
        NVIDIA_URL + "\n\n",
        "https://example.test/a\nb",
        "https://example.test/a\tb",
        "https://example.test/a b",
        " https://example.test/a",
        "https://example.test/a ",
        "https://example.test/a\n",
        "https://[broken",
        "https://",
        "https://example.test:99999/a",
        "https://example.test:not-a-port/a",
        "https:relative",
        "javascript:alert(1)",
        "mailto:example@example.test",
        "ftp://example.test/a",
        "/relative",
        "",
        None,
        123,
        [],
    ],
)
def test_strict_http_url_rejects_invalid_values(url):
    assert http_url_error(url) is not None


@pytest.mark.parametrize(
    "href,expected",
    [
        ("/article?id=2&lang=en", "https://example.test/article?id=2&lang=en"),
        ("relative", "https://example.test/relative"),
        (" /article \n", "https://example.test/article"),
        ("//other.test/a", "https://other.test/a"),
        ("http://other.test/a", "http://other.test/a"),
        ("https://other.test/a?q=a%20b", "https://other.test/a?q=a%20b"),
        ("https://other.test/a(b)", "https://other.test/a(b)"),
        ("https://other.test/%5Bok%5D", "https://other.test/%5Bok%5D"),
        ("https://other.test/\u516c\u544a", "https://other.test/\u516c\u544a"),
        ("https://\u4f8b\u5b50.test/a", "https://\u4f8b\u5b50.test/a"),
        ("https://other.test:8443/a#b", "https://other.test:8443/a#b"),
    ],
)
def test_valid_article_urls_keep_their_representation(href, expected):
    page = response(f'<div id="pageptlist">{row(href)}</div>')
    result = parse_articles(page, page.url)
    assert result.rejected_count == 0
    assert result.articles == [{"title": "Article", "link": expected, "date": None}]
    assert http_url_error(expected) is None


@pytest.mark.parametrize(
    "href",
    [
        NVIDIA_URL,
        NVIDIA_URL + "\n\n",
        "/a\nb",
        "/a\tb",
        "https://[broken",
        "//[broken",
        "https://example.test:99999",
        "https:relative",
        "javascript:alert(1)",
        " ",
    ],
)
def test_parser_skips_only_invalid_urls_and_logs_context(href, caplog):
    page = response(
        '<div id="pageptlist">'
        + row("/first", "First")
        + row(href, "Broken")
        + row("/last", "Last")
        + "</div>"
    )
    result = parse_articles(page, page.url)
    assert [article["title"] for article in result.articles] == ["First", "Last"]
    assert result.rejected_count == 1
    assert len(caplog.records) == 1
    assert SOURCE_URL in caplog.text
    assert "Broken" in caplog.text
    assert repr(href) in caplog.text
    assert "article=1" in caplog.text


@pytest.fixture
def pipeline_setup(tmp_path, monkeypatch):
    aggregate = tmp_path / "announcements.json"
    folder = tmp_path / "announcements"
    monkeypatch.setattr(announcements, "ANNOUNCEMENTS_JSON_PATH", aggregate)
    monkeypatch.setattr(announcements, "ANNOUNCEMENTS_FOLDER", folder)
    monkeypatch.setattr(
        announcements.AnnouncementsItemSpider,
        "_load_announcement_list",
        lambda self: [SOURCE],
    )
    spider = announcements.AnnouncementsItemSpider()
    individual = folder / "Department" / "Notices_en.json"
    return spider, aggregate, individual


@pytest.mark.parametrize("baseline", ["none", "mixed", "invalid", "valid"])
@pytest.mark.parametrize(
    "refresh", ["failed", "empty", "broken", "all-invalid", "mixed", "valid"]
)
def test_fresh_and_retained_outputs_are_sanitized(pipeline_setup, baseline, refresh):
    spider, aggregate, individual = pipeline_setup
    previous_articles = {
        "none": [],
        "mixed": [GOOD_ARTICLE, BAD_ARTICLE],
        "invalid": [BAD_ARTICLE],
        "valid": [GOOD_ARTICLE],
    }[baseline]
    original = None
    if baseline != "none":
        previous = {**SOURCE, "articles": previous_articles}
        write_json_atomic([previous], aggregate)
        write_json_atomic(previous, individual)
        original = individual.read_bytes()
    pipeline = announcements.AnnouncementItemPipeline()
    pipeline.open_spider(spider)
    html = {
        "empty": '<div id="pageptlist"></div>',
        "broken": "<html>Unavailable</html>",
        "all-invalid": f'<div id="pageptlist">{row(NVIDIA_URL)}</div>',
        "mixed": (f'<div id="pageptlist">{row("/fresh")}{row(NVIDIA_URL)}</div>'),
        "valid": f'<div id="pageptlist">{row("/fresh")}</div>',
    }
    if refresh != "failed":
        for item in spider.parse(response(html[refresh])):
            pipeline.process_item(item, spider)
    pipeline.close_spider(spider)

    fallback = refresh in {"failed", "empty", "broken"}
    if fallback and baseline == "none":
        assert read_json(aggregate) == []
        assert not individual.exists()
        return
    if fallback:
        expected_articles = [a for a in previous_articles if a != BAD_ARTICLE]
    elif refresh == "all-invalid":
        expected_articles = []
    else:
        expected_articles = [
            {"title": "Article", "link": "https://example.test/fresh", "date": None}
        ]
    expected = {**SOURCE, "articles": expected_articles}
    assert read_json(aggregate) == [expected]
    assert read_json(individual) == expected
    if fallback and baseline == "valid":
        assert individual.read_bytes() == original
    assert "_all_articles_invalid" not in read_json(individual)

    # Repeated fallback must not resurrect articles or rewrite healthy files.
    before = individual.read_bytes()
    pipeline = announcements.AnnouncementItemPipeline()
    pipeline.open_spider(spider)
    pipeline.close_spider(spider)
    assert read_json(aggregate) == [expected]
    assert individual.read_bytes() == before


@pytest.mark.parametrize("all_invalid", [False, True])
def test_pipeline_validates_items_before_writing(pipeline_setup, all_invalid, caplog):
    spider, aggregate, individual = pipeline_setup
    pipeline = announcements.AnnouncementItemPipeline()
    pipeline.open_spider(spider)
    articles = [BAD_ARTICLE] if all_invalid else [GOOD_ARTICLE, BAD_ARTICLE]
    item = announcements.AnnouncementItem({**SOURCE, "articles": articles})
    pipeline.process_item(item, spider)
    pipeline.close_spider(spider)
    expected = {**SOURCE, "articles": [] if all_invalid else [GOOD_ARTICLE]}
    assert read_json(aggregate) == [expected]
    assert read_json(individual) == expected
    warnings = [
        record
        for record in caplog.records
        if "Skipping invalid announcement URL" in record.message
    ]
    assert len(warnings) == 1
    assert NVIDIA_URL in caplog.text
    assert "NVIDIA GTC" in caplog.text


def test_legacy_fallback_is_sanitized_after_matching(pipeline_setup):
    spider, aggregate, individual = pipeline_setup
    old = {
        **SOURCE,
        "link": "https://example.test/redirected",
        "articles": [GOOD_ARTICLE, BAD_ARTICLE],
        "extra": "preserved",
    }
    write_json_atomic([old], aggregate)
    write_json_atomic(old, individual)
    pipeline = announcements.AnnouncementItemPipeline()
    pipeline.open_spider(spider)
    pipeline.close_spider(spider)
    expected = {**old, "link": SOURCE_URL, "articles": [GOOD_ARTICLE]}
    assert read_json(aggregate) == [expected]
    assert read_json(individual) == expected


@pytest.mark.parametrize("whitespace", [" ", "\n", "\t"])
@pytest.mark.parametrize("position", ["prefix", "suffix"])
@pytest.mark.parametrize("retained", [False, True])
def test_pipeline_rejects_whitespace_in_published_urls(
    pipeline_setup, whitespace, position, retained, caplog
):
    spider, aggregate, individual = pipeline_setup
    url = "https://example.test/article"
    link = whitespace + url if position == "prefix" else url + whitespace
    source = {
        **SOURCE,
        "articles": [GOOD_ARTICLE, {"title": "Whitespace", "link": link}],
    }
    if retained:
        write_json_atomic([source], aggregate)
        write_json_atomic(source, individual)
    pipeline = announcements.AnnouncementItemPipeline()
    pipeline.open_spider(spider)
    if not retained:
        pipeline.process_item(announcements.AnnouncementItem(source), spider)
    pipeline.close_spider(spider)

    expected = {**SOURCE, "articles": [GOOD_ARTICLE]}
    assert read_json(aggregate) == [expected]
    assert read_json(individual) == expected
    assert repr(link) in caplog.text
    assert "url_syntax_violation" in caplog.text
