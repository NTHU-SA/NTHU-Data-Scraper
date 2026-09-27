import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

import pytest

from nthu_scraper.storage import read_json, write_json_atomic

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


def test_library_hooks_and_partial_upstream_failures_through_scrapy(tmp_path):
    rss_path = tmp_path / "libraries" / "rss.json"
    calendars_path = tmp_path / "libraries" / "calendars.json"
    write_json_atomic(
        {"news": ["old"], "exhibit": ["old"], "branches": ["old"]}, rss_path
    )
    old_main = {"id": "main", "events": ["old"]}
    write_json_atomic([old_main, {"id": "hss", "events": ["old"]}], calendars_path)

    result = run_spider(tmp_path, "offline_libraries")

    assert result.returncode == 0, result.stdout + result.stderr
    rss = read_json(rss_path)
    assert rss["news"][0]["title"] == "New"
    assert rss["exhibit"] == ["old"]
    assert rss["branches"] == ["old"]
    calendars = read_json(calendars_path)
    assert calendars[0] == old_main
    assert calendars[1]["id"] == "hss"
    assert calendars[1]["events"][0]["title"] == "New"


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
    previous = [{**source, "articles": ["old"]} for source in sources]
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
