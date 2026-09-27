import argparse
import json

import pytest

from generate_index import generate_html_report, workspace_path


def test_cli_paths_must_remain_in_workspace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert workspace_path("data/index.html").is_relative_to(tmp_path)
    with pytest.raises(argparse.ArgumentTypeError, match="must remain within"):
        workspace_path("../index.html")


def test_index_displays_content_version_without_commit_link(tmp_path):
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
                            "last_commit": version,
                            "version": version,
                            "sha256": version,
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
    assert 'href="libraries/rss.json"' in html
