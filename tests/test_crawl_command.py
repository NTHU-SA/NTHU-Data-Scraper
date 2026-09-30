import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

import pytest

from nthu_scraper.spiders.nthu_libraries import RSS_TYPES, parse_rss
from nthu_scraper.storage import read_json, write_json_atomic
from nthu_scraper.utils.url_utils import http_url_error

ROOT = Path(__file__).resolve().parents[1]


def run_spider(tmp_path, name, *args):
    environment = {
        **os.environ,
        "DATA_FOLDER": str(tmp_path),
        "PYTHONPATH": os.pathsep.join([str(ROOT / "tests" / "fixtures"), str(ROOT)]),
    }
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "scrapy",
            "crawl",
            name,
            "-s",
            "SPIDER_MODULES=safety_spiders",
            "-s",
            "TELNETCONSOLE_ENABLED=False",
            "-s",
            "LOG_LEVEL=WARNING",
            *args,
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        encoding="utf-8",
        errors="replace",
    )


@pytest.mark.parametrize(
    "scenario",
    [
        "callback",
        "item",
        "open",
        "close",
        "start",
        "write",
        "hook",
        "import",
        "request",
    ],
)
def test_real_scrapy_implementation_failures_exit_nonzero(tmp_path, scenario):
    path = tmp_path / "preserved.json"
    write_json_atomic({"known-good": True}, path)
    original = path.read_bytes()
    result = run_spider(tmp_path, "offline_failure", "-a", f"scenario={scenario}")
    assert result.returncode != 0, result.stdout + result.stderr
    assert path.read_bytes() == original


def test_real_scrapy_success_exits_zero(tmp_path):
    result = run_spider(tmp_path, "offline_failure")
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    "spider_name,filename,expected_name",
    [
        ("offline_directory", "directory.json", "Test department"),
        ("offline_newsletters", "newsletters.json", "Test newsletter"),
        ("offline_dining", "dining.json", "\u6c34\u6728\u9910\u5ef3"),
    ],
)
def test_source_pipeline_hooks_through_scrapy(
    tmp_path, spider_name, filename, expected_name
):
    result = run_spider(tmp_path, spider_name)
    assert result.returncode == 0, result.stdout + result.stderr
    data = read_json(tmp_path / filename)
    assert data[0]["name"] == expected_name
    if spider_name == "offline_newsletters":
        assert len(data[0]["articles"]) == 3
    elif spider_name == "offline_directory":
        assert data[0]["details"]["contact"] == {"phone": "03-0000000", "fax": "N/A"}
    else:
        assert len(data) == 2


def test_announcement_list_pipeline_and_https_middleware_through_scrapy(tmp_path):
    result = run_spider(tmp_path, "offline_announcement_list")
    assert result.returncode == 0, result.stdout + result.stderr
    data = read_json(tmp_path / "announcements_list.json")
    item = next(item for item in data if item["department"] == "Test department")
    assert item == {
        "title": "\u6821\u5712\u516c\u544a",
        "link": "https://example.test/list",
        "department": "Test department",
        "language": "en",
    }


def test_real_item_error_signal_preserves_whole_dataset(tmp_path):
    path = tmp_path / "directory.json"
    write_json_atomic([{"name": "old"}], path)
    before = path.read_bytes()
    result = run_spider(tmp_path, "offline_directory_failure")
    assert result.returncode != 0, result.stdout + result.stderr
    assert "offline injected item failure" in result.stderr
    assert "Error caught on signal handler" not in result.stderr
    assert path.read_bytes() == before


def test_campus_calendar_pipeline_through_scrapy(tmp_path):
    library_path = tmp_path / "libraries" / "calendars.json"
    write_json_atomic([{"id": "main", "events": ["old"]}], library_path)
    before = library_path.read_bytes()
    result = run_spider(tmp_path, "offline_calendars")
    assert result.returncode == 0, result.stdout + result.stderr
    (calendar,) = read_json(tmp_path / "calendars.json")
    assert calendar["id"] == "academic"
    assert calendar["events"][0]["title"] == "Semester begins"
    assert library_path.read_bytes() == before


def test_library_hooks_and_partial_upstream_failures_through_scrapy(tmp_path):
    rss_path = tmp_path / "libraries" / "rss.json"
    calendars_path = tmp_path / "libraries" / "calendars.json"
    old_articles = parse_rss(
        "<rss><channel><item><title>Old</title></item></channel></rss>"
    )
    write_json_atomic(
        {key: old_articles for key in ("news", "exhibit", "branches")}, rss_path
    )
    old_main = {"id": "main", "events": ["old"]}
    write_json_atomic([old_main, {"id": "hss", "events": ["old"]}], calendars_path)

    result = run_spider(tmp_path, "offline_libraries")

    assert result.returncode == 0, result.stdout + result.stderr
    rss = read_json(rss_path)
    assert rss["news"][0]["title"] == "New"
    assert rss["exhibit"] == old_articles
    assert rss["branches"] == old_articles
    calendars = read_json(calendars_path)
    assert calendars[0] == old_main
    assert calendars[1]["id"] == "hss"
    assert calendars[1]["events"][0]["title"] == "New"


def test_library_url_repairs_and_nullable_images_through_scrapy(tmp_path):
    result = run_spider(tmp_path, "offline_library_urls")
    assert result.returncode == 0, result.stdout + result.stderr
    rss = read_json(tmp_path / "libraries" / "rss.json")
    assert list(rss) == RSS_TYPES
    for articles in rss.values():
        assert len(articles) == 6
        assert articles[0]["link"].startswith(
            "https://www.proquest.com/centralpremium/index, "
            "https://ebookcentral.proquest.com/"
        )
        assert articles[3]["image"]["url"].endswith("CNKI%20Trial.jpg")
        assert articles[4]["image"]["url"].endswith("Wiley%20UBCM.jpg")
        assert articles[5]["title"] == "Broken image"
        assert articles[5]["image"] is None
        for article in articles:
            if article["image"]:
                assert http_url_error(article["image"]["url"]) is None
    assert "using null" in result.stderr


def test_malformed_library_baseline_fails_real_crawl(tmp_path):
    path = tmp_path / "libraries" / "rss.json"
    path.parent.mkdir()
    path.write_bytes(b"{invalid")
    result = run_spider(tmp_path, "offline_libraries")
    assert result.returncode != 0, result.stdout + result.stderr
    assert path.read_bytes() == b"{invalid"


def test_library_implementation_failure_exits_nonzero(tmp_path):
    result = run_spider(tmp_path, "offline_broken_library")
    assert result.returncode != 0, result.stdout + result.stderr
    assert "offline injected library regression" in result.stderr


def test_invalid_courses_exit_nonzero_and_preserve_files(tmp_path):
    paths = [tmp_path / "courses.json", tmp_path / "courses" / "latest.json"]
    for path in paths:
        write_json_atomic(["old"], path)
    before = [path.read_bytes() for path in paths]
    result = run_spider(tmp_path, "offline_courses")
    assert result.returncode != 0, result.stdout + result.stderr
    assert [path.read_bytes() for path in paths] == before


def test_announcements_request_failure_keeps_source_and_individual_file(tmp_path):
    good_link = "data:text/html," + quote(
        '<div id="pageptlist"><div class="row listBS"><div class="mtitle">'
        '<a href="https://example.test/article">New article</a></div></div></div>'
    )
    sources = [
        {"link": good_link, "title": "good", "department": "dept", "language": "en"},
        {
            "link": "data:text/plain,failed",
            "title": "failed",
            "department": "dept",
            "language": "en",
        },
    ]
    previous = [
        {
            **source,
            "articles": [{"title": "Old", "link": "https://example.test/old"}],
        }
        for source in sources
    ]
    write_json_atomic(sources, tmp_path / "announcements_list.json")
    path = tmp_path / "announcements.json"
    write_json_atomic(previous, path)
    individual = tmp_path / "announcements" / "dept" / "failed_en.json"
    write_json_atomic(previous[1], individual)
    before = individual.read_bytes()

    result = run_spider(tmp_path, "offline_announcements")

    assert result.returncode == 0, result.stdout + result.stderr
    actual = {source["link"]: source for source in read_json(path)}
    assert actual[good_link]["articles"][0]["title"] == "New article"
    assert actual[sources[1]["link"]] == previous[1]
    assert individual.read_bytes() == before


@pytest.mark.parametrize("all_invalid", [False, True])
def test_invalid_announcement_urls_do_not_fail_real_crawl(tmp_path, all_invalid):
    bad_url = "https://example.test/bad](https://example.test/bad"
    good_row = (
        '<div class="row listBS"><div class="mtitle">'
        '<a href="https://example.test/fresh">Fresh</a></div></div>'
    )
    link = "data:text/html," + quote(
        '<div id="pageptlist">'
        + ("" if all_invalid else good_row)
        + '<div class="row listBS"><div class="mtitle">'
        + f'<a href="{bad_url}">Invalid</a></div></div></div>'
    )
    sources = [
        {"link": link, "title": "fresh", "department": "dept", "language": "en"},
        {
            "link": "data:text/plain,failed",
            "title": "fallback",
            "department": "dept",
            "language": "en",
        },
    ]
    previous = [
        {**source, "articles": [{"title": "Invalid", "link": bad_url}]}
        for source in sources
    ]
    write_json_atomic(sources, tmp_path / "announcements_list.json")
    write_json_atomic(previous, tmp_path / "announcements.json")
    for source in previous:
        write_json_atomic(
            source, tmp_path / "announcements" / "dept" / f"{source['title']}_en.json"
        )

    result = run_spider(tmp_path, "offline_announcements")

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stderr.count("Skipping invalid announcement URL") == 2
    actual = {
        source["title"]: source for source in read_json(tmp_path / "announcements.json")
    }
    assert actual["fallback"] == {**sources[1], "articles": []}
    assert actual["fresh"] == {
        **sources[0],
        "articles": []
        if all_invalid
        else [{"title": "Fresh", "link": "https://example.test/fresh", "date": None}],
    }
    for title, source in actual.items():
        assert (
            read_json(tmp_path / "announcements" / "dept" / f"{title}_en.json")
            == source
        )


@pytest.mark.parametrize(
    "spider_name,filename,previous,expected",
    [
        (
            "offline_buses",
            "buses.json",
            {
                "towardTSMCBuildingInfo": {"route": "old"},
                "towardNandaInfo": {"route": "old"},
            },
            {
                "towardTSMCBuildingInfo": {"route": "new"},
                "towardNandaInfo": {"route": "old"},
            },
        ),
        (
            "offline_maps",
            "maps.json",
            {"MainZH": {"old": {}}, "MainEN": {"old": {}}},
            {
                "MainZH": {"New": {"latitude": "1", "longitude": "2"}},
                "MainEN": {"old": {}},
            },
        ),
    ],
)
def test_component_request_failure_is_safe_through_scrapy(
    tmp_path, spider_name, filename, previous, expected
):
    path = tmp_path / filename
    write_json_atomic(previous, path)
    result = run_spider(tmp_path, spider_name)
    assert result.returncode == 0, result.stdout + result.stderr
    assert read_json(path) == expected, result.stdout + result.stderr
