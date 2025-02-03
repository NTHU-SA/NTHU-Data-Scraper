import os

docs_path = "docs"
output_file = "index.html"


def generate_file_list_html(base_path):
    html = "<html><head><meta charset='UTF-8'><title>檔案列表</title></head><body>\n"
    html += "<h1>檔案列表</h1>\n<ul>\n"
    for root, dirs, files in os.walk(base_path):
        # 將路徑轉為相對路徑
        rel_root = os.path.relpath(root, base_path)
        # 如果不是根目錄，顯示資料夾名稱
        if rel_root != ".":
            html += f"<li><strong>{rel_root}</strong><ul>\n"
        for file in files:
            file_path = os.path.join(root, file)
            # 轉換為相對於 docs 目錄的連結
            rel_file = os.path.relpath(file_path, base_path)
            html += f'<li><a href="{base_path}/{rel_file}">{file}</a></li>\n'
        if rel_root != ".":
            html += "</ul></li>\n"
    html += "</ul>\n</body></html>"
    return html


if __name__ == "__main__":
    html_content = generate_file_list_html(docs_path)
    with open(docs_path + "/" + output_file, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"{output_file} 已生成！")
