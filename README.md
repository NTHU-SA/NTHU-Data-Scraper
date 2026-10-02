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
List titles come from the module containing the announcement list, falling back
to a standalone section heading or the document title rather than search or
article headings. Successful content refreshes use the page's current title,
but scheduled crawls intentionally leave `announcements_list.json` unchanged.
Run the source crawler manually to update existing source titles. Custom source
titles remain explicitly configured. Announcement titles and dates normalize
control characters (including `\u000b`) and repeated Unicode whitespace to
single spaces, without changing URLs.

`nthu_newsletters` starts at the official
[metadata gallery wrapper](https://newsletter.cc.nthu.edu.tw/index.php/home-zh-tw/lis),
follows its embedded Big5 gallery and current AcyMailing list, and joins freshly
scraped management details by list ID. The AcyMailing list determines membership,
names, and archive URLs; lists absent from the metadata gallery have empty
`details`. External or retired gallery links do not add extra lists.
Each archive contributes only its default, recent-first page (not its full
paginated history), preserving the existing `name`, `link`, `details`, and
`articles` JSON shape. Explicit “No results” archives remain as empty lists.
Missing structures, malformed entries/dates, or failed requests retain the
previous whole newsletter snapshot. This crawler is manual, not scheduled.

### URL handling

Use `normalize_http_url` from `nthu_scraper.utils.url_utils` for HTTP(S) URL
fields. It resolves relative links against an explicit base, supplies HTTPS for
protocol-relative links, trims surrounding whitespace, and encodes spaces in
paths, queries, and fragments without double-encoding existing escapes.
Pydantic's strict `HttpUrl` validation then produces a canonical URL, including
encoded Unicode paths and internationalized hostnames. HTTP remains HTTP unless
the caller explicitly requires HTTPS.

Unrecoverable hosts, ports, schemes, embedded controls, and malformed URLs raise
`InvalidHttpUrl`; they are not guessed into valid links. Optional URL fields use
`normalize_optional_http_url`, which logs the value and context before returning
`null`. Announcements, directory links/websites, newsletters, dining images,
bus image links, maps/course requests, and calendar URLs use these shared rules.

Library RSS article `link` is an exception: it is nullable **text**, matching
[NTHU-SA/NTHU-Data-API#276](https://github.com/NTHU-SA/NTHU-Data-API/pull/276).
Single links, relative links, and comma-separated URL lists retain their original
text; missing or blank links become `null`. RSS image URLs are normalized before
publication. An unrecoverable image URL makes `image` null without removing the
article; an invalid image hyperlink makes only `image.link` null.

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
Announcement sources are removed only when removed from the source list.
Individual announcement article URLs are first normalized; unrecoverable URLs
are skipped with a warning, without discarding valid siblings. The same handling
applies to retained previous articles, and affected individual files and the
aggregate are saved consistently. If every article is rejected, the source
remains with an empty `articles` list; this is distinct from an empty or failed refresh.
URL checks validate syntax, not live HTTP availability.

Library RSS normalization retains every article and unknown fields in JSON
snapshots. Fresh and retained feeds use the same output shape and image
normalization, including when all RSS requests fail. RSS titles must contain a
non-whitespace character in both fresh and retained feeds. Structural feed
errors retain the previous source; corrupt baselines block the crawl instead of
silently replacing data. Library and academic calendars reject reversed or
mixed date/datetime event boundaries before publication, retaining the previous
source on invalid upstream data.

JSON writes use atomic file replacement. Implementation, storage, or validation
errors block publication; a multi-file local crawl is not a single transaction.

`file_details.json` identifies exact file contents with SHA-256.
`last_commit` is a compatibility alias for `version` / `sha256`, not a Git commit.
See [workflow.md](workflow.md) for deployment and rollback details.

## License

[MIT](LICENSE)
