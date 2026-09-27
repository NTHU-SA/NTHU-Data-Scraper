import argparse
import html
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PurePosixPath
from string import Template
from urllib.parse import quote

REPOSITORY_URL = "https://github.com/NTHU-SA/NTHU-Data-Scraper"
TEMPLATE_PATH = Path(__file__).with_name("index_template.html")


def format_datetime(iso_string: str) -> str:
    if not iso_string or iso_string == "N/A":
        return "N/A"
    try:
        timestamp = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return str(iso_string)
    return timestamp.strftime("%Y-%m-%d %H:%M:%S %z")


@dataclass
class Folder:
    children: dict[str, "Folder"] = field(default_factory=dict)
    files: list[dict] = field(default_factory=list)

    @property
    def file_count(self) -> int:
        return len(self.files) + sum(
            child.file_count for child in self.children.values()
        )

    @property
    def folder_count(self) -> int:
        return len(self.children) + sum(
            child.folder_count for child in self.children.values()
        )


def render_folder(folder: Folder, path: PurePosixPath) -> str:
    rows = []
    for name, child in sorted(
        folder.children.items(), key=lambda entry: entry[0].casefold()
    ):
        child_path = path / name
        rows.append(
            '<details class="folder">'
            '<summary class="entry folder-entry">'
            '<span class="entry-name"><span class="chevron" aria-hidden="true">'
            '</span><svg class="icon folder-icon" aria-hidden="true">'
            '<use href="#folder-icon"/></svg>'
            f'<span class="name">{html.escape(name)}</span>'
            f'<span class="folder-count">{child.file_count} 個檔案</span></span>'
            "</summary>"
            f'<div class="folder-contents">{render_folder(child, child_path)}</div>'
            "</details>"
        )

    for file_info in sorted(
        folder.files, key=lambda entry: str(entry.get("name", "")).casefold()
    ):
        file_name = str(file_info.get("name", "N/A"))
        file_path = (path / file_name).as_posix()
        version = str(
            file_info.get("sha256")
            or file_info.get("version")
            or file_info.get("last_commit")
            or ""
        )
        timestamp = html.escape(format_datetime(file_info.get("last_updated", "N/A")))
        rows.append(
            f'<div class="entry file-entry" data-path="{html.escape(file_path, quote=True)}">'
            '<span class="entry-name"><svg class="icon file-icon" aria-hidden="true">'
            '<use href="#file-icon"/></svg>'
            f'<a class="name" href="{html.escape(quote(file_path, safe="/"), quote=True)}">'
            f"{html.escape(file_name)}</a></span>"
            f'<span class="timestamp">{timestamp}</span>'
            f'<code class="version" title="{html.escape(version, quote=True)}">'
            f"{html.escape(version[:12]) if version else 'N/A'}</code></div>"
        )
    return "\n".join(rows)


def generate_html_report(json_file_path: str, github_base_url: str, output_path: str):
    json_path = Path(json_file_path)
    output_path_obj = Path(output_path)

    if not json_path.is_file():
        raise FileNotFoundError(f"JSON file {json_file_path} does not exist.")

    with json_path.open(encoding="utf-8") as file:
        data = json.load(file)

    root = Folder()
    for directory, files in data.get("file_details", {}).items():
        folder = root
        if directory != "/":
            for part in PurePosixPath(directory).parts:
                folder = folder.children.setdefault(part, Folder())
        folder.files.extend(files)

    html_content = Template(TEMPLATE_PATH.read_text(encoding="utf-8")).substitute(
        last_updated=html.escape(format_datetime(data.get("last_updated", "N/A"))),
        repository_url=html.escape(github_base_url, quote=True),
        current_year=datetime.now().year,
        file_count=root.file_count,
        folder_count=root.folder_count,
        entries=render_folder(root, PurePosixPath()),
        empty_hidden="hidden" if root.file_count else "",
    )
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)
    output_path_obj.write_text(html_content, encoding="utf-8")
    print(f"{output_path} generated.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate a static index from file_details.json."
    )
    parser.parse_args()
    data_folder = (Path.cwd() / "data").resolve()
    generate_html_report(
        data_folder / "file_details.json",
        REPOSITORY_URL,
        data_folder / "index.html",
    )
