# NTHU-Data-Scraper

Public campus data from National Tsing Hua University, published as JSON at
**[data.nthusa.tw](https://data.nthusa.tw/)**.

Browse folders on the website or use the JSON URLs directly. The index supports
filename/path search and shows each file's update time and SHA-256 version.

## Datasets

| Data | JSON |
|---|---|
| Announcements | [announcements.json](https://data.nthusa.tw/announcements.json) |
| Bus schedules | [buses.json](https://data.nthusa.tw/buses.json) |
| Courses | [courses.json](https://data.nthusa.tw/courses.json) |
| Dining | [dining.json](https://data.nthusa.tw/dining.json) |
| Academic calendar | [calendars.json](https://data.nthusa.tw/calendars.json) |
| File inventory and versions | [file_details.json](https://data.nthusa.tw/file_details.json) |

The website also includes department directories, maps, newsletters, and library
data. Announcements, buses, courses, dining, libraries, and the academic calendar
are refreshed every two hours; other datasets retain their last published snapshot.

## Development

Requires Python 3.13 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run python -m scrapy crawl nthu_buses
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
```

Crawlers write to the Git-ignored `data/` directory. Use
`uv run ruff format .` to apply formatting. Tests run offline without Chromium.
For crawlers that use Playwright, install the browser with
`uv run playwright install chromium`.

### Available crawlers

Run a crawler with `uv run python -m scrapy crawl <name>`.

| Name | Data |
|---|---|
| `nthu_announcements_list` | Announcement sources |
| `nthu_announcements_item` | Announcement content |
| `nthu_buses` | Campus bus schedules |
| `nthu_courses` | Course information |
| `nthu_dining` | Dining information |
| `nthu_directory` | Department directory |
| `nthu_maps` | Campus maps |
| `nthu_newsletters` | Newsletters |
| `nthu_libraries` | Library RSS feeds and opening-hours calendars |
| `nthu_calendars` | University academic calendar |

Run `nthu_announcements_list` before `nthu_announcements_item` on a fresh
checkout, or populate `data/` from the published snapshot first.

### Website preview

With crawler output in `data/`:

```bash
uv run python generate_file_detail.py
uv run python generate_index.py
uv run python -m http.server 8000 --bind 127.0.0.1 --directory data
```

Open <http://127.0.0.1:8000>. The page is generated from `index_template.html`;
it needs no frontend build or external assets. Folders and file links work
without JavaScript; search and expand/collapse controls use JavaScript.

## Publishing

`main` holds source code and tests. The `data` branch holds the published
snapshot and is the GitHub Pages source.

GitHub Actions starts from the previous snapshot, runs the scheduled crawlers,
validates the data, and publishes changed files to `data`. It also runs on
pushes to `main` and manual dispatch.

### Data safety

Failed or empty refreshes retain previous data. Announcements, buses, maps,
and libraries preserve failed sources independently; directory, newsletter,
and course crawls require a complete valid result before replacing a dataset.
Announcements are removed only when removed from the source list.

JSON writes use atomic file replacement. Implementation, storage, or validation
errors block publication; a multi-file local crawl is not a single transaction.

`file_details.json` identifies exact file contents with SHA-256.
`last_commit` is a compatibility alias for `version` / `sha256`, not a Git commit.
See [workflow.md](workflow.md) for deployment and rollback details.

## License

[MIT](LICENSE)
