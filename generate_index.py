import argparse
import html
import json
import os
from datetime import datetime
from pathlib import Path


def format_datetime(iso_string: str) -> str:
    if not iso_string or iso_string == "N/A":
        return "N/A"
    try:
        timestamp = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return str(iso_string)
    return timestamp.strftime("%Y-%m-%d %H:%M:%S %z")


def generate_html_report(json_file_path: str, github_base_url: str, output_path: str):
    json_path = Path(json_file_path)
    output_path_obj = Path(output_path)

    if not json_path.is_file():
        raise FileNotFoundError(f"JSON file {json_file_path} does not exist.")

    with json_path.open(encoding="utf-8") as file:
        data = json.load(file)

    last_updated = html.escape(format_datetime(data.get("last_updated", "N/A")))
    file_details = data.get("file_details", {})
    current_year = datetime.now().year
    repository_url = html.escape(github_base_url, quote=True)

    html_content = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>檔案更新詳情</title>
    <style>
        body {{ font-family: "Helvetica Neue", Arial, sans-serif; margin: 10px; color: #333; line-height: 1.6; background-color: #f8f8f8; }}
        h1 {{ color: #a783b7; margin-bottom: 10px; font-size: 2.2em; }}
        h1 a {{ color: #a783b7; text-decoration: none; }}
        h2 {{ color: #007bff; border-bottom: 1px solid #ecf0f1; padding-bottom: 5px; margin-top: 15px; font-size: 1.6em; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 10px; box-shadow: 0 0 6px rgba(0,0,0,0.05); }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; font-size: 0.95em; white-space: nowrap; word-break: break-word; }}
        th {{ background-color: #f2f2f2; color: #777; }}
        tr:nth-child(even) {{ background-color: #f9f9f9; }}
        a {{ color: #007bff; text-decoration: none; font-weight: 500; }}
        a:hover {{ text-decoration: underline; }}
        .updated-time {{ font-size: 0.9em; color: #777; font-style: italic; }}
        .container {{ max-width: 960px; margin: 20px auto; padding: 25px; background-color: #fff; border-radius: 5px; }}
        .table-container {{ width: 100%; overflow-x: auto; }}
        .footer {{ margin-top: 20px; padding-top: 8px; border-top: 1px solid #eee; font-size: 0.8em; color: #888; text-align: center; }}
    </style>
</head>
<body>
    <div class="container">
        <h1><a href="{repository_url}">NTHU-DATA</a> 檔案更新詳情</h1>
        <p class="updated-time">最後更新時間: {last_updated}</p>
        <p>以下列出各資料檔案的最後更新時間與 SHA-256 內容版本。</p>
"""

    for directory, files in file_details.items():
        html_content += f"<h2>{html.escape(directory)}</h2>\n"
        html_content += (
            "<div class=\"table-container\"><table>"
            "<thead><tr><th>檔案名稱</th><th>最後更新時間</th>"
            "<th>SHA-256</th><th>開啟檔案</th></tr></thead><tbody>\n"
        )
        for file_info in files:
            file_name = str(file_info.get("name", "N/A"))
            file_last_updated = html.escape(
                format_datetime(file_info.get("last_updated", "N/A"))
            )
            version = str(
                file_info.get("sha256")
                or file_info.get("version")
                or file_info.get("last_commit")
                or ""
            )
            version_text = html.escape(version[:12]) if version else "N/A"
            version_title = html.escape(version, quote=True)
            file_path = (
                Path(file_name)
                if directory == "/"
                else Path(directory) / file_name
            ).as_posix()

            html_content += f"""<tr>
                <td>{html.escape(file_name)}</td>
                <td>{file_last_updated}</td>
                <td title="{version_title}">{version_text}</td>
                <td><a href="{html.escape(file_path, quote=True)}">開啟</a></td>
            </tr>
"""
        html_content += "</tbody></table></div>\n"

    html_content += f"""<div class="footer">
            <p>License: <a href="https://opensource.org/licenses/MIT">MIT License</a> |
            Copyright © {current_year} <a href="https://nthusa.tw/">清華大學學生會(NTHUSA) 資訊處</a>.</p>
            <p>此頁面由 Python 腳本自動生成，部署於 GitHub Pages。</p>
        </div>
    </div>
</body>
</html>
"""

    output_path_obj.parent.mkdir(parents=True, exist_ok=True)
    output_path_obj.write_text(html_content, encoding="utf-8")
    print(f"{output_path} generated.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate a static index from file_details.json."
    )
    parser.add_argument(
        "--github_base",
        default=os.getenv(
            "GITHUB_BASE", "https://github.com/NTHU-SA/NTHU-Data-Scraper"
        ),
    )
    args = parser.parse_args()
    data_folder = (Path.cwd() / "data").resolve()
    generate_html_report(
        data_folder / "file_details.json",
        args.github_base,
        data_folder / "index.html",
    )
