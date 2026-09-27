import json
import subprocess
import sys
from pathlib import Path

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
