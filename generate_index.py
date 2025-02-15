import argparse
import json
import os
from datetime import datetime
from pathlib import Path


def format_datetime(iso_string: str) -> str:
    """將 ISO 格式的時間字串轉換為 YYYY-MM-DD 時區格式。"""
    if not iso_string or iso_string == "N/A":
        return "N/A"
    try:
        dt = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
    except Exception:
        return iso_string
    return dt.strftime("%Y-%m-%d %H:%M:%S %Z")


def generate_html_report(json_file_path: str, github_base_url: str, output_path: str):
    """
    根據 JSON 檔案生成 HTML 報告。

    Args:
        json_file_path: file_detail.json 檔案的路徑。
        github_base_url: GitHub 倉庫的 base URL。
        output_path: 生成的 HTML 檔案儲存路徑。
    """
    json_path = Path(json_file_path)
    output_path_obj = Path(output_path)

    if not json_path.is_file():
        raise FileNotFoundError(f"JSON 檔案 {json_file_path} 不存在。")

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    last_updated = format_datetime(data.get("last_updated", "N/A"))
    file_details = data.get("file_details", {})
    current_year = datetime.now().year

    html_content = f"""
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>檔案更新詳情</title>
    <style>
        body {{ font-family: 'Helvetica Neue', Arial, sans-serif; margin: 10px; color: #333; line-height: 1.6; background-color: #f8f8f8; }}
        h1 {{ color: #a783b7; font-weight: bold; margin-bottom: 10px; font-size: 2.2em; }}
        h1 a {{ color: #a783b7; font-weight: bold; ; text-decoration: none; }}
        h2 {{ color: #007bff; border-bottom: 1px solid #ecf0f1; padding-bottom: 5px; margin-top: 15px; font-size: 1.6em; }}
        p {{ color: #555; margin-bottom: 8px; font-size: 1em; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 10px; box-shadow: 0 0 6px rgba(0,0,0,0.05); }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; font-size: 0.95em; white-space: nowrap; word-break: break-word;}}
        th {{ background-color: #f2f2f2; color: #777; font-weight: bold; }}
        tr:nth-child(even) {{ background-color: #f9f9f9; }}
        a {{ color: #007bff; text-decoration: none; font-weight: 500; }}
        a:hover {{ text-decoration: underline; }}
        .updated-time {{ font-size: 0.9em; color: #777; margin-bottom: 8px; font-style: italic; }}
        .container {{ max-width: 960px; margin: 20px auto; padding: 25px; background-color: #fff; border-radius: 5px; }}
        .github-link {{ margin-top: 15px; font-size: 0.9em; text-align: center; }}
        .github-link a {{ color: #27ae60; }}
        .commit-link {{ cursor: pointer; }}
        .open-file-link {{ cursor: pointer; }}
        .license-copyright {{ margin-top: 20px; padding-top: 8px; border-top: 1px solid #eee; font-size: 0.8em; color: #888; text-align: center; }}
        .license-copyright a {{ color: #888; }}
        /* 新增 table-container 對小螢幕添加水平滾動 */
        .table-container {{ width: 100%; overflow-x: auto; }}
    </style>
</head>
<body>
    <div class="container">
        <h1><u><a href="{github_base_url}">NTHU-DATA</a></u> 檔案更新詳情</h1>
        <p class="updated-time">最後更新時間: {last_updated}</p>
        <p>以下列出各目錄下的檔案及其最後更新時間與 Commit 連結 (Commit Hash)。</p>
    """

    for directory, files in file_details.items():
        html_content += f"<h2>{directory}</h2>\n"
        html_content += "<div class='table-container'>\n"
        html_content += "<table>\n"
        html_content += "<thead><tr><th>檔案名稱</th><th>最後更新時間</th><th>Commit</th><th>開啟檔案</th></tr></thead>\n"
        html_content += "<tbody>\n"
        for file_info in files:
            file_name = file_info.get("name", "N/A")
            file_last_updated = format_datetime(file_info.get("last_updated", "N/A"))
            last_commit = file_info.get("last_commit", "")
            commit_link = (
                f"{github_base_url}/commit/{last_commit}"
                if last_commit and github_base_url
                else "#"
            )
            commit_display_text = last_commit[:7] if last_commit else "N/A"
            commit_link_html = (
                f'<a href="{commit_link}" target="_blank" class="commit-link">{commit_display_text}</a>'
                if last_commit and github_base_url
                else "N/A"
            )
            if directory == "/":
                file_path = file_name
            else:
                file_path = Path(directory) / file_name

            open_file_button = f'<a href="{file_path}" class="open-file-link">開啟</a>'

            html_content += f"""
            <tr>
                <td>{file_name}</td>
                <td>{file_last_updated}</td>
                <td>{commit_link_html}</td>
                <td>{open_file_button}</td>
            </tr>
            """
        html_content += "</tbody>\n</table>\n"
        html_content += "</div>\n"

    html_content += f"""
        <div class="license-copyright">
            <p>
                License: <a href="https://opensource.org/licenses/MIT" target="_blank">MIT License</a> |
                Copyright © {current_year} <a href="https://nthusa.tw/" target="_blank">清華大學學生會(NTHUSA) 資訊處</a>. All rights reserved.
            </p>
        </div>
        <div class="github-link">
            <p>此頁面由 Python 腳本自動生成，部署於 <a href="https://pages.github.com/" target="_blank">GitHub Pages</a>。</p>
        </div>
    </div>
</body>
</html>
    """

    output_path_obj.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path_obj, "w", encoding="utf-8") as html_file:
        html_file.write(html_content)

    print(f"{output_path} 檔案已生成。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="從 file_detail.json 檔案生成檔案更新詳情 HTML 報告。"
    )
    parser.add_argument(
        "--json_path",
        type=str,
        default="file_detail.json",
        help="file_detail.json 檔案路徑 (預設為 file_detail.json)",
    )
    parser.add_argument(
        "--github_base",
        type=str,
        default=os.getenv(
            "GITHUB_BASE", "https://github.com/NTHU-SA/NTHU-Data-Scraper"
        ),
        help="GitHub 倉庫的 base URL (預設為 GITHUB_BASE 環境變數或 https://github.com/NTHU-SA/NTHU-Data-Scraper)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="index.html",
        help="輸出 HTML 檔案路徑 (預設為 index.html)",
    )
    args = parser.parse_args()
    generate_html_report(args.json_path, args.github_base, args.output)
