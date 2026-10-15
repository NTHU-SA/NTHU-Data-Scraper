import json
import subprocess
import sys
from pathlib import Path
from urllib.parse import urljoin

import pytest
from parsel import Selector

from generate_index import generate_html_report

SCRIPT = Path(__file__).parents[1] / "generate_index.py"


def test_cli_uses_fixed_workspace_data_paths(tmp_path):
    data_folder = tmp_path / "data"
    data_folder.mkdir()
    (data_folder / "file_details.json").write_text(
        json.dumps({"last_updated": "2026-09-27T20:00:00+08:00", "file_details": {}}),
        encoding="utf-8",
    )

    subprocess.run([sys.executable, str(SCRIPT)], cwd=tmp_path, check=True)

    assert (data_folder / "index.html").is_file()


def test_index_displays_content_version_and_file_history_link(tmp_path):
    metadata = tmp_path / "file_details.json"
    output = tmp_path / "index.html"
    version = "a" * 64
    metadata.write_text(
        json.dumps(
            {
                "last_updated": "2026-09-27T20:00:00+08:00",
                "file_details": {
                    "libraries": [
                        {
                            "name": "rss.json",
                            "last_updated": "2026-09-27T20:00:00+08:00",
                            "version": version,
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    generate_html_report(
        str(metadata), "https://github.com/NTHU-SA/NTHU-Data-Scraper", str(output)
    )
    html = output.read_text(encoding="utf-8")

    assert version[:12] in html
    assert f"/commit/{version}" not in html
    page = Selector(text=html)
    assert page.css("a.name::attr(href)").get() == "/libraries/rss.json"
    assert page.css("a.timestamp::attr(href)").get() == (
        "https://github.com/NTHU-SA/NTHU-Data-Scraper/commits/data/libraries/rss.json"
    )
    assert page.css("a.timestamp::text").get() == "2026-09-27 20:00:00 +0800"
    assert page.css(".column-head span::text").getall() == [
        "名稱",
        "最後更新時間",
        "版本",
    ]


def render_index(tmp_path, file_details):
    metadata = tmp_path / "file_details.json"
    output = tmp_path / "index.html"
    metadata.write_text(json.dumps({"file_details": file_details}), encoding="utf-8")
    generate_html_report(str(metadata), "https://github.com/example/repo", str(output))
    return Selector(text=output.read_text(encoding="utf-8"))


def test_index_builds_nested_folders_before_sorted_root_files(tmp_path):
    page = render_index(
        tmp_path,
        {
            "/": [{"name": "z.json"}, {"name": "a.json"}],
            "libraries/archive/2026": [{"name": "rss.json"}],
            "libraries": [{"name": "calendars.json"}],
            "buses": [{"name": "schedule.json"}],
        },
    )

    assert page.css("#entries > details > summary .name::text").getall() == [
        "buses",
        "libraries",
    ]
    assert page.css("#entries > .file-entry a::text").getall() == ["a.json", "z.json"]
    assert page.css("#entries > *")[0].root.tag == "details"
    assert page.css("details details details summary .name::text").getall() == ["2026"]
    assert page.css("details details details a::attr(href)").getall() == [
        "/libraries/archive/2026/rss.json"
    ]
    assert page.css("#result-count::text").get() == "4 個資料夾 · 5 個檔案"
    assert page.css("#entries > details > summary .folder-count::text").getall() == [
        "1 個檔案",
        "2 個檔案",
    ]
    assert not page.css("details[open]")
    assert page.css("#empty[hidden]")


def test_index_escapes_labels_attributes_and_url_segments(tmp_path):
    folder = 'folder<&"'
    name = '測試 #?&".json'
    page = render_index(
        tmp_path,
        {
            folder: [
                {
                    "name": name,
                    "last_updated": "<script>alert(1)</script>",
                    "version": '"><img src=x>',
                    "last_commit": '"><img src=y>',
                }
            ]
        },
    )

    assert page.css("summary .name::text").get() == folder
    assert page.css(".file-entry a.name::text").get() == name
    assert page.css(".file-entry::attr(data-path)").get() == f"{folder}/{name}"
    encoded_path = "folder%3C%26%22/%E6%B8%AC%E8%A9%A6%20%23%3F%26%22.json"
    assert page.css(".file-entry a.name::attr(href)").get() == f"/{encoded_path}"
    assert page.css("a.timestamp::attr(href)").get() == (
        f"https://github.com/example/repo/commits/data/{encoded_path}"
    )
    assert page.css(".timestamp::text").get() == "<script>alert(1)</script>"
    assert page.css(".version::attr(title)").get() == '"><img src=x>'
    assert not page.css(".entries script, .entries img")


def test_index_displays_version(tmp_path):
    version = "b" * 64
    page = render_index(tmp_path, {"/": [{"name": "data.json", "version": version}]})

    assert page.css(".version::text").get() == version[:12]
    assert page.css(".version::attr(title)").get() == version
    assert page.css(".timestamp::text").get() == "N/A"
    assert not page.css("a.timestamp")


@pytest.mark.parametrize(
    ("field", "value"),
    [("sha256", "c" * 64), ("last_commit", "a" * 40), ("last_commit", "b" * 64)],
)
def test_index_does_not_use_checksum_or_last_commit_as_version(tmp_path, field, value):
    page = render_index(tmp_path, {"/": [{"name": "data.json", field: value}]})

    assert page.css(".version::text").get() == "N/A"
    assert page.css(".version::attr(title)").get() == ""
    assert value not in page.get()


def test_index_uses_version_independently_of_checksum_and_last_commit(tmp_path):
    version = "d" * 64
    page = render_index(
        tmp_path,
        {
            "/": [
                {
                    "name": "data.json",
                    "version": version,
                    "sha256": "e" * 64,
                    "last_commit": "f" * 64,
                }
            ]
        },
    )

    assert page.css(".version::text").get() == version[:12]
    assert page.css(".version::attr(title)").get() == version


@pytest.mark.parametrize("page_path", ["/", "/courses/", "/courses/index.html"])
def test_file_links_resolve_from_site_root_at_any_page_path(tmp_path, page_path):
    page = render_index(
        tmp_path,
        {
            "/": [{"name": "buses.json"}],
            "courses/semesters": [{"name": "10810.json"}],
            "libraries/archive/2026": [{"name": "rss.json"}],
        },
    )
    base_url = f"https://data.nthusa.tw{page_path}"

    assert urljoin(base_url, "courses/semesters/10810.json") == (
        "https://data.nthusa.tw/courses/semesters/10810.json"
        if page_path == "/"
        else "https://data.nthusa.tw/courses/courses/semesters/10810.json"
    )
    for entry in page.css(".file-entry"):
        path = entry.attrib["data-path"]
        assert urljoin(base_url, entry.css("a.name::attr(href)").get()) == (
            f"https://data.nthusa.tw/{path}"
        )
    assert urljoin(base_url, page.css("h1 a::attr(href)").get()) == (
        "https://data.nthusa.tw/"
    )
    assert urljoin(base_url, page.css(".top-links a::attr(href)").get()) == (
        "https://data.nthusa.tw/file_details.json"
    )


def test_history_link_uses_repository_url_without_duplicate_separator(tmp_path):
    metadata = tmp_path / "file_details.json"
    output = tmp_path / "index.html"
    metadata.write_text(
        json.dumps(
            {
                "file_details": {
                    "/": [
                        {
                            "name": "data.json",
                            "last_updated": "2026-09-27T20:00:00+08:00",
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    generate_html_report(str(metadata), "https://github.com/example/repo/", str(output))
    page = Selector(text=output.read_text(encoding="utf-8"))

    assert page.css("a.timestamp::attr(href)").get() == (
        "https://github.com/example/repo/commits/data/data.json"
    )


def test_empty_index_shows_message_and_no_dead_script_controls(tmp_path):
    page = render_index(tmp_path, {})

    assert page.css("#empty:not([hidden])")
    assert page.css("#result-count::text").get() == "0 個資料夾 · 0 個檔案"
    assert page.css(".search[hidden], .actions[hidden]")
    assert page.css('a[href="/file_details.json"]')
