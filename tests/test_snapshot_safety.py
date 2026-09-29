import asyncio
import json
from dataclasses import asdict
from types import SimpleNamespace

import pytest
import scrapy
from scrapy import signals
from scrapy.crawler import Crawler
from scrapy.http import HtmlResponse, TextResponse
from twisted.python.failure import Failure

from nthu_scraper.commands.crawl import Command
from nthu_scraper.spiders import (
    nthu_announcements_item as announcements,
)
from nthu_scraper.spiders import (
    nthu_buses as buses,
)
from nthu_scraper.spiders import (
    nthu_courses as courses,
)
from nthu_scraper.spiders import (
    nthu_dining as dining,
)
from nthu_scraper.spiders import (
    nthu_directory as directory,
)
from nthu_scraper.spiders import (
    nthu_maps as maps,
)
from nthu_scraper.spiders import (
    nthu_newsletters as newsletters,
)
from nthu_scraper.storage import read_json, write_json_atomic
from nthu_scraper.utils import constants
from nthu_scraper.utils.crawl_safety import log_source_failure


@pytest.mark.parametrize(
    "name,relative_path",
    [
        ("DIRECTORY_JSON_PATH", "directory.json"),
        ("ANNOUNCEMENTS_FOLDER", "announcements"),
        ("ANNOUNCEMENTS_LIST_PATH", "announcements_list.json"),
        ("ANNOUNCEMENTS_JSON_PATH", "announcements.json"),
        ("BUSES_JSON_PATH", "buses.json"),
        ("BUSES_FOLDER", "buses"),
        ("COURSES_FOLDER", "courses"),
        ("COURSES_JSON_PATH", "courses.json"),
        ("DINING_JSON_PATH", "dining.json"),
        ("MAPS_FOLDER", "maps"),
        ("MAPS_JSON_PATH", "maps.json"),
        ("NEWSLETTERS_JSON_PATH", "newsletters.json"),
        ("LIBRARIES_FOLDER", "libraries"),
        ("LIBRARIES_RSS_JSON_PATH", "libraries/rss.json"),
        ("LIBRARIES_CALENDARS_JSON_PATH", "libraries/calendars.json"),
    ],
)
def test_dataset_paths_remain_unchanged(name, relative_path):
    assert getattr(constants, name) == constants.DATA_FOLDER / relative_path


def announcement(link, title="old"):
    return {
        "link": link,
        "title": title,
        "department": "department",
        "language": "en",
        "articles": [
            {
                "title": title,
                "link": (
                    link if link.startswith("https://") else f"https://{link}.test"
                )
                + "/article",
                "date": "2026-09-27",
            }
        ],
    }


@pytest.mark.parametrize("successful", [[], ["a"], ["a", "b"]])
def test_announcements_merge_authoritative_sources(
    tmp_path, monkeypatch, caplog, successful
):
    path = tmp_path / "announcements.json"
    folder = tmp_path / "announcements"
    monkeypatch.setattr(announcements, "ANNOUNCEMENTS_JSON_PATH", path)
    monkeypatch.setattr(announcements, "ANNOUNCEMENTS_FOLDER", folder)
    expected = [announcement(key, key) for key in ("b", "a", "new-without-baseline")]
    old = [announcement(key, key) for key in ("removed", "b", "a")]
    write_json_atomic(old, path)
    spider = scrapy.Spider("test")
    spider.announcement_list = expected
    pipeline = announcements.AnnouncementItemPipeline()
    pipeline.open_spider(spider)
    for key in reversed(successful):
        pipeline.process_item(
            announcements.AnnouncementItem(announcement(key, "new-" + key)), spider
        )
    pipeline.close_spider(spider)
    assert read_json(path) == [
        announcement(key, "new-" + key if key in successful else key)
        for key in ("a", "b")
    ]
    assert "No known-good announcement source: new-without-baseline" in caplog.text


def test_empty_announcement_keeps_individual_and_aggregate(tmp_path, monkeypatch):
    path = tmp_path / "announcements.json"
    folder = tmp_path / "announcements"
    monkeypatch.setattr(announcements, "ANNOUNCEMENTS_JSON_PATH", path)
    monkeypatch.setattr(announcements, "ANNOUNCEMENTS_FOLDER", folder)
    old = announcement("a")
    individual = folder / "department" / "old_en.json"
    write_json_atomic(old, individual)
    write_json_atomic([old], path)
    original = individual.read_bytes()
    spider = scrapy.Spider("test")
    spider.announcement_list = [old]
    pipeline = announcements.AnnouncementItemPipeline()
    pipeline.open_spider(spider)
    pipeline.process_item(
        announcements.AnnouncementItem({**old, "articles": []}), spider
    )
    pipeline.close_spider(spider)
    assert read_json(path) == [old]
    assert individual.read_bytes() == original


@pytest.mark.parametrize("refresh_legacy", [False, True])
def test_legacy_redirected_announcement_is_migrated(
    tmp_path, monkeypatch, refresh_legacy
):
    path = tmp_path / "announcements.json"
    folder = tmp_path / "announcements"
    monkeypatch.setattr(announcements, "ANNOUNCEMENTS_JSON_PATH", path)
    monkeypatch.setattr(announcements, "ANNOUNCEMENTS_FOLDER", folder)
    legacy = announcement("https://example.test/redirected", "notice")
    canonical = {**legacy, "link": "https://example.test/original"}
    other = announcement("https://other.test", "other")
    write_json_atomic([legacy, other], path)
    individual = folder / "department" / "notice_en.json"
    write_json_atomic(legacy, individual)
    before = individual.read_bytes()
    spider = scrapy.Spider("test")
    spider.announcement_list = [canonical, other]
    refreshed = {
        **canonical,
        "articles": [{"title": "fresh", "link": "https://example.test/fresh"}],
    }
    pipeline = announcements.AnnouncementItemPipeline()
    pipeline.open_spider(spider)
    pipeline.process_item(announcements.AnnouncementItem(other), spider)
    if refresh_legacy:
        pipeline.process_item(announcements.AnnouncementItem(refreshed), spider)
    pipeline.close_spider(spider)
    expected = [refreshed if refresh_legacy else canonical, other]
    assert read_json(path) == expected
    if not refresh_legacy:
        assert individual.read_bytes() == before
    pipeline = announcements.AnnouncementItemPipeline()
    pipeline.open_spider(spider)
    pipeline.close_spider(spider)
    assert read_json(path) == expected


@pytest.mark.parametrize("duplicate", ["expected", "legacy"])
def test_ambiguous_legacy_source_fails_without_overwriting(
    tmp_path, monkeypatch, duplicate
):
    path = tmp_path / "announcements.json"
    monkeypatch.setattr(announcements, "ANNOUNCEMENTS_JSON_PATH", path)
    old = [announcement("https://example.test/redirected")]
    expected = [announcement("https://example.test/original")]
    target = old if duplicate == "legacy" else expected
    target.append(announcement("https://example.test/another"))
    write_json_atomic(old, path)
    before = path.read_bytes()
    spider = scrapy.Spider("test")
    spider.announcement_list = expected
    pipeline = announcements.AnnouncementItemPipeline()
    with pytest.raises(ValueError, match="Ambiguous legacy"):
        pipeline.open_spider(spider)
    assert path.read_bytes() == before


def test_canonical_link_takes_precedence_over_legacy_metadata(tmp_path, monkeypatch):
    path = tmp_path / "announcements.json"
    monkeypatch.setattr(announcements, "ANNOUNCEMENTS_JSON_PATH", path)
    monkeypatch.setattr(announcements, "ANNOUNCEMENTS_FOLDER", tmp_path / "individual")
    canonical = announcement("https://example.test/original")
    write_json_atomic([canonical, announcement("https://example.test/removed")], path)
    spider = scrapy.Spider("test")
    spider.announcement_list = [canonical]
    pipeline = announcements.AnnouncementItemPipeline()
    pipeline.open_spider(spider)
    pipeline.close_spider(spider)
    assert read_json(path) == [canonical]


def test_announcement_redirect_keeps_authoritative_identity(tmp_path, monkeypatch):
    source = announcement("https://example.test/original")
    path = tmp_path / "announcements_list.json"
    write_json_atomic([source], path)
    monkeypatch.setattr(announcements, "ANNOUNCEMENTS_LIST_PATH", path)
    spider = announcements.AnnouncementsItemSpider()

    async def requests():
        return [request async for request in spider.start()]

    request = asyncio.run(requests())[0]
    response = HtmlResponse(
        "https://example.test/redirected",
        request=request,
        body=b'<div id="pageptlist"><div class="row listBS"><div class="mtitle">'
        b'<a href="/article">Article</a></div></div></div>',
        encoding="utf-8",
    )
    assert list(spider.parse(response))[0]["link"] == source["link"]


@pytest.mark.parametrize("broken", [False, True])
def test_announcement_table_header_and_partial_parse(tmp_path, monkeypatch, broken):
    path = tmp_path / "announcements_list.json"
    write_json_atomic([], path)
    monkeypatch.setattr(announcements, "ANNOUNCEMENTS_LIST_PATH", path)
    spider = announcements.AnnouncementsItemSpider()
    html = (
        '<table id="pageptlist"><tr><th>Title</th></tr>'
        '<tr><td class="mtitle"><a href="/article">Article</a></td></tr>'
        + ('<tr><td class="mtitle">Broken article</td></tr>' if broken else "")
        + "</table>"
    )
    response = HtmlResponse(
        "https://example.test", body=html.encode(), encoding="utf-8"
    )
    result = spider._extract_articles(response)
    if broken:
        assert result is None
    else:
        assert len(result.articles) == 1


@pytest.mark.parametrize(
    "module,pipeline_type,item_type,aggregate_name,folder_name",
    [
        (buses, buses.BusPipeline, buses.BusInfo, "BUSES_JSON_PATH", "BUSES_FOLDER"),
        (maps, maps.MapPipeline, maps.MapItem, "MAPS_JSON_PATH", "MAPS_FOLDER"),
    ],
)
def test_components_keep_missing_and_empty_values(
    tmp_path, monkeypatch, module, pipeline_type, item_type, aggregate_name, folder_name
):
    path = tmp_path / "aggregate.json"
    monkeypatch.setattr(module, aggregate_name, path)
    monkeypatch.setattr(module, folder_name, tmp_path / "individual")
    previous = {"MainEN": {"old": 1}, "MainZH": {"old": 2}, "NandaEN": {"old": 3}}
    write_json_atomic(previous, path)
    spider = scrapy.Spider("test")
    pipeline = pipeline_type()
    pipeline.open_spider(spider)
    for key, data in [("MainZH", {}), ("MainEN", {"new": 1})]:
        item = (
            item_type(item_name=key, route_type="main", data=data)
            if module is buses
            else item_type(map_type=key, data=data)
        )
        pipeline.process_item(item, spider)
    pipeline.close_spider(spider)
    result = read_json(path)
    assert result == {**previous, "MainEN": {"new": 1}}
    if module is maps:
        assert list(result) == sorted(result)


def test_partial_bus_parse_does_not_publish_truncated_component():
    spider = buses.BusesSpider()
    assert (
        spider._parse_schedule_variable(
            "schedule", 'const schedule = [{"time":"08:00"}, {"description":"broken"}];'
        )
        is None
    )


VALID_COURSES = [
    {"\u79d1\u865f": "11510CS101", "\u4e2d\u6587\u8ab2\u540d": "Course A"},
    {"\u79d1\u865f": "11520CS102", "\u4e2d\u6587\u8ab2\u540d": "Course B"},
]


def course_response(data):
    return TextResponse(
        "https://example.test/courses",
        body=json.dumps(data).encode("utf-8"),
        encoding="utf-8",
        request=scrapy.Request(
            "https://example.test/courses", meta={"data_type": "latest"}
        ),
    )


@pytest.fixture
def course_paths(tmp_path, monkeypatch):
    folder = tmp_path / "courses"
    root = tmp_path / "courses.json"
    monkeypatch.setattr(courses, "COURSES_FOLDER", folder)
    monkeypatch.setattr(courses, "COURSES_JSON_PATH", root)
    paths = [root, folder / "latest.json", folder / "semesters" / "11510.json"]
    for path in paths:
        write_json_atomic(["known-good"], path)
    return paths, folder


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"error": "unavailable"},
        [],
        "invalid",
        [None],
        [{}],
        {"\u5de5\u4f5c\u88681": {}},
        VALID_COURSES + [{}],
        [
            {
                "\u79d1\u865f": "../xxCS101",
                "\u4e2d\u6587\u8ab2\u540d": "invalid semester",
            }
        ],
    ],
)
def test_invalid_courses_preserve_all_previous_files(course_paths, data):
    paths, folder = course_paths
    before = {path: path.read_bytes() for path in paths}
    spider = courses.CoursesSpider()
    response = course_response(data)
    with pytest.raises(ValueError):
        spider.parse(response)
    assert {path: path.read_bytes() for path in paths} == before
    assert len(list(folder.rglob("*.json"))) == 2


@pytest.mark.parametrize("wrapped", [False, True])
def test_valid_courses_preserve_structure_and_indentation(course_paths, wrapped):
    paths, folder = course_paths
    payload = {"\u5de5\u4f5c\u88681": VALID_COURSES} if wrapped else VALID_COURSES
    courses.CoursesSpider().parse(course_response(payload))
    assert read_json(paths[0]) == VALID_COURSES
    assert read_json(paths[1]) == VALID_COURSES
    assert paths[0].read_text(encoding="utf-8") == json.dumps(
        VALID_COURSES, ensure_ascii=False, indent=4
    )
    assert paths[1].read_text(encoding="utf-8") == json.dumps(
        VALID_COURSES, ensure_ascii=False, indent=2
    )
    for course, semester in zip(VALID_COURSES, ("11510", "11520"), strict=True):
        assert read_json(folder / "semesters" / f"{semester}.json") == [
            asdict(courses.CoursesData.from_dict(course))
        ]


@pytest.mark.parametrize(
    "module,spider_type,pipeline_type,path_name",
    [
        (
            directory,
            directory.DirectorySpider,
            directory.DirectoryPipeline,
            "DIRECTORY_JSON_PATH",
        ),
        (
            newsletters,
            newsletters.NewsletterSpider,
            newsletters.NewsletterPipeline,
            "NEWSLETTERS_JSON_PATH",
        ),
    ],
)
@pytest.mark.parametrize(
    "failure_kind", ["request", "parse", "empty", "implementation", "none"]
)
def test_whole_dataset_retained_unless_complete(
    tmp_path, monkeypatch, module, spider_type, pipeline_type, path_name, failure_kind
):
    path = tmp_path / "aggregate.json"
    write_json_atomic([{"name": "old"}], path)
    original = path.read_bytes()
    monkeypatch.setattr(module, path_name, path)
    spider = spider_type()
    pipeline = pipeline_type()
    pipeline.open_spider(spider)
    if failure_kind != "empty":
        pipeline.process_item({"name": "new", "index": "1"}, spider)
    request = scrapy.Request(
        "https://example.test/child",
        meta={"dept_name": "name", "newsletter": {"name": "name"}},
    )
    if failure_kind == "request":
        failure = Failure(OSError("upstream unavailable"))
        failure.request = request
        spider.handle_request_error(failure)
    elif failure_kind == "implementation":
        spider.handle_spider_error(Failure(RuntimeError("regression")))
    elif failure_kind == "parse":
        response = HtmlResponse(
            request.url, request=request, body=b"<html>broken</html>"
        )
        callback = (
            spider.parse_dept_page
            if module is directory
            else spider.parse_newsletter_content
        )
        assert list(callback(response)) == []
    pipeline.close_spider(spider)
    if failure_kind == "none":
        assert read_json(path) == [{"name": "new", "index": "1"}]
    else:
        assert path.read_bytes() == original


@pytest.mark.parametrize(
    "spider_type,html",
    [
        (directory.DirectorySpider, '<li><a href="dept.php?dd=1">Dept</a></li>'),
        (
            newsletters.NewsletterSpider,
            '<div class="gallery"><li><h3><a href="https://example.test/news">News</a></h3></li></div>',
        ),
    ],
)
def test_whole_dataset_requests_have_errbacks(spider_type, html):
    spider = spider_type()

    async def requests():
        return [request async for request in spider.start()]

    assert all(
        request.errback == spider.handle_request_error
        for request in asyncio.run(requests())
    )
    response = HtmlResponse(
        "https://example.test", body=html.encode(), encoding="utf-8"
    )
    children = list(spider.parse(response))
    assert children
    assert all(request.errback == spider.handle_request_error for request in children)


@pytest.mark.parametrize(
    "module,spider_type,pipeline_type,path_name,valid,invalid",
    [
        (
            directory,
            directory.DirectorySpider,
            directory.DirectoryPipeline,
            "DIRECTORY_JSON_PATH",
            '<li><a href="dept.php?dd=1">Good</a></li>',
            invalid,
        )
        for invalid in (
            "<li>Missing link</li>",
            "<li><a>Missing href</a></li>",
            '<li><a href="dept.php?dd=2"></a></li>',
            '<li><a href="dept.php?dd=2"> </a></li>',
        )
    ]
    + [
        (
            newsletters,
            newsletters.NewsletterSpider,
            newsletters.NewsletterPipeline,
            "NEWSLETTERS_JSON_PATH",
            '<li><h3><a href="https://example.test/good">Good</a></h3></li>',
            invalid,
        )
        for invalid in (
            "<li>Missing heading</li>",
            "<li><h3>No link</h3></li>",
            "<li><h3><a>No href</a></h3></li>",
            '<li><h3><a href="https://example.test/empty"></a></h3></li>',
            '<li><h3><a href="https://example.test/empty"> </a></h3></li>',
        )
    ],
)
def test_mixed_root_listing_keeps_previous_dataset(
    tmp_path, monkeypatch, module, spider_type, pipeline_type, path_name, valid, invalid
):
    path = tmp_path / "aggregate.json"
    write_json_atomic([{"name": "old"}], path)
    before = path.read_bytes()
    monkeypatch.setattr(module, path_name, path)
    spider = spider_type()
    pipeline = pipeline_type()
    pipeline.open_spider(spider)
    html = f'<div class="gallery"><ul>{valid}{invalid}</ul></div>'
    response = HtmlResponse(
        "https://example.test", body=html.encode(), encoding="utf-8"
    )
    requests = list(spider.parse(response))
    assert len(requests) == 1
    pipeline.process_item({"name": "good", "index": "1"}, spider)
    pipeline.close_spider(spider)
    assert path.read_bytes() == before


def test_mixed_child_department_listing_keeps_previous_dataset(tmp_path, monkeypatch):
    path = tmp_path / "directory.json"
    write_json_atomic([{"name": "old"}], path)
    before = path.read_bytes()
    monkeypatch.setattr(directory, "DIRECTORY_JSON_PATH", path)
    spider = directory.DirectorySpider()
    pipeline = directory.DirectoryPipeline()
    pipeline.open_spider(spider)
    response = HtmlResponse(
        "https://example.test/dept?dd=1",
        request=scrapy.Request(
            "https://example.test/dept?dd=1", meta={"dept_name": "Dept"}
        ),
        body=b'<div class="story_left"><a href="dept.php?dd=2">Good</a><a>Broken</a></div>',
        encoding="utf-8",
    )
    outputs = list(spider.parse_dept_page(response))
    assert any(isinstance(output, scrapy.Request) for output in outputs)
    for output in outputs:
        if isinstance(output, directory.DepartmentItem):
            pipeline.process_item(output, spider)
    pipeline.close_spider(spider)
    assert path.read_bytes() == before


@pytest.mark.parametrize("signal", [signals.spider_error, signals.item_error])
def test_scrapy_error_signals_accept_failure_only_receivers(signal):
    crawler = Crawler(directory.DirectorySpider)
    spider = directory.DirectorySpider.from_crawler(crawler)
    command = Command()
    command._errors = SimpleNamespace(failed=False)
    crawler.signals.connect(command._implementation_error, signal=signal)
    failure = Failure(RuntimeError("injected signal failure"))
    payload = {"failure": failure, "response": None, "spider": spider}
    if signal == signals.item_error:
        payload["item"] = {"name": "failed"}
    results = crawler.signals.send_catch_log(signal=signal, **payload)
    assert len(results) == 2
    assert all(not isinstance(result, Failure) for _, result in results)
    assert command._errors.failed
    assert spider.crawl_incomplete


def test_dining_failed_parse_keeps_existing_file(tmp_path, monkeypatch):
    path = tmp_path / "dining.json"
    monkeypatch.setattr(dining, "DINING_JSON_PATH", path)
    write_json_atomic([{"old": True}], path)
    original = path.read_bytes()
    spider = dining.DiningSpider()
    pipeline = dining.DiningPipeline()
    pipeline.open_spider(spider)
    response = HtmlResponse("https://example.test", body=b"<html>unavailable</html>")
    for item in spider.parse(response):
        pipeline.process_item(item, spider)
    assert path.read_bytes() == original


def test_newsletter_partial_article_parse_keeps_whole_dataset(tmp_path, monkeypatch):
    path = tmp_path / "newsletters.json"
    write_json_atomic([{"name": "old"}], path)
    before = path.read_bytes()
    monkeypatch.setattr(newsletters, "NEWSLETTERS_JSON_PATH", path)
    spider = newsletters.NewsletterSpider()
    pipeline = newsletters.NewsletterPipeline()
    pipeline.open_spider(spider)
    response = HtmlResponse(
        "https://example.test",
        request=scrapy.Request(
            "https://example.test", meta={"newsletter": {"name": "new"}}
        ),
        body=b'<div id="acyarchivelisting"><table class="contentpane">'
        b'<div class="archiveRow"><a>Good article</a></div>'
        b'<div class="archiveRow">Broken article</div></table></div>',
        encoding="utf-8",
    )
    for item in spider.parse_newsletter_content(response):
        pipeline.process_item(item, spider)
    pipeline.close_spider(spider)
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "handler",
    [
        log_source_failure,
        directory.DirectorySpider().handle_request_error,
        newsletters.NewsletterSpider().handle_request_error,
    ],
)
def test_unexpected_request_errors_are_not_swallowed(handler):
    failure = Failure(AttributeError("downloader implementation regression"))
    with pytest.raises(AttributeError):
        handler(failure)
