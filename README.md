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

### Course sources and structured fields

`nthu_courses` preserves the official latest JSON as `courses.json` and
`courses/latest.json`. Semester files in `courses/semesters/` retain the legacy
English keys and add structured fields. They are **not** the same schema as the
raw latest files.

```bash
uv run python -m scrapy crawl nthu_courses
uv run python -m scrapy crawl nthu_courses -a mode=backfill
uv run python -m scrapy crawl nthu_courses -a mode=rebuild
```

The default downloads only the latest JSON, then rebuilds with any locally
archived historical sources. `backfill` checks the
[official download page](https://curricul.site.nthu.edu.tw/p/404-1208-111356.php?Lang=zh-tw)
and fetches all configured historical JSON and Excel attachments. `rebuild`
requires all archived sources and makes no network requests. GitHub Actions
manual dispatch supports these modes through `course_mode`; scheduled runs
remain `latest`.
Missing or checksum-mismatched previously archived files block a refresh;
use `backfill` to restore them rather than silently dropping historical sources.
When the latest feed moves to a new semester, its outgoing response is
preserved byte-for-byte as `courses/raw/latest-<semester>.json`. If a response
spans semesters, only those no longer covered by the incoming latest feed are
replayed from that archive; current-semester courses always come from the new
feed. These archives have their own source IDs, checksums, row provenance, and
semester coverage in `sources.json`, and are included in future refreshes and
offline rebuilds. Previously published semesters without an official raw
source are preserved byte-for-byte in `courses/raw/retained-<semester>.json`
and restored to `courses/semesters/` on offline rebuilds. They are labeled
separately as `retained_published_snapshots` with checksums, coverage, and
record counts, not represented as recovered official sources. `normalized_records`
counts only source-normalized rows; `retained_records` and `published_records`
account for the preserved snapshot rows. Malformed or changed retained snapshots
block publication rather than being silently deleted or overwritten.
If an official source later covers a retained semester, its normalized data
replaces the published semester while the original snapshot stays archived,
marked `superseded` and excluded from `retained_records`.

Original response bytes are saved under `courses/raw/`, including complete
workbooks and auxiliary sheets. `courses/sources.json` declares
`path_base: "courses"`: resolve each archive `path` relative to this directory
under the published snapshot root. It records URLs, SHA-256,
selected course sheets, source counts, actual semester coverage, regular-semester
gaps, merge conflicts, and verified source repairs. No new retrieval timestamp
is generated on each run. Identical inputs leave output files unchanged.
Current attachments cover 10810–11410 and the current latest semester; the
page's “114下 Excel” link now describes converting the latest JSON, not a
separate 11420 archive. Missing terms are reported, never synthesized.

Historical Excel is authoritative; JSON only fills missing fields or courses.
Blank capacity means unlimited, not missing; zero remains zero. Different
enrollment snapshots are kept separate. Only configured main course sheets
create courses. The 11410 bilingual teacher supplement joins existing courses
by ID; its other auxiliary sheets remain available in the original workbook.
An attachment or schema change requires an explicit adapter update, not guessing
which new sheets to import. Conflicting duplicates fail the crawl.

| Added field | Meaning |
|---|---|
| `semester_code`, `department_code`, `course_number` | String components of the original course ID; `id` retains its source spelling |
| `department_name`, `college_name`, `course_level_code`, `course_level`, `source_semester`, `remote_teaching` | Available source metadata; historical unit names are not guessed for newer terms |
| `meetings` | Ordered `{classroom, time, time_codes}` objects, preserving room/time pairing |
| `lecturers` | Bilingual `{name_zh, name_en}` objects when the source supplies pairings; otherwise `{label}` entries, including units and “指導教授” |
| `lecturer_names_zh`, `lecturer_names_en` | Available original teacher-supplement name lists, even when individual pairings cannot be established |
| `expertises`, `programs`, `curriculum_requirements` | Specialty objects, program-name strings, and `{target, requirement}` objects |
| `credits`, `capacity`, `capacity_unlimited`, `enrolled_count`, `reserved_for_freshmen` | Typed numbers and explicit unlimited status; fractional credits are supported |
| `enrollment_after_selection`, `enrollment_after_withdrawal` | Counts at different official enrollment checkpoints; neither substitutes for `enrolled_count` |
| `is_cancelled`, `language_code` | Official cancellation marker and `zh`/`en` language mapping, or `null` when unknown |
| `prerequisite_text` | HTML/entity-cleaned display text, not an executable eligibility rule |
| `sources`, `field_sources` | Source IDs and 1-based JSON record or Excel row/sheet locations, including per-field provenance |
| `parsing_issues` | Explicit issues for source values that cannot be reliably interpreted |

Multiple meetings now retain **all** room/time pairs: legacy `classroom` and
`time` use corresponding newline-separated entries for the official combined
format, instead of truncating at the second tab. Historical separate fields
retain their source text; paired comma-separated rooms/times are also parsed
into `meetings`. Time codes remain official period codes, not guessed clock
times. Empty lists are `[]`; unknown typed values are `null`, not zero.

Raw source fields are retained in the downloadable originals even if not
modeled as an added field. Missing fields and documented empty values are
distinct. Unexpected source values retain their legacy text, log a warning,
and appear in `parsing_issues` rather than becoming plausible defaults.
Unparseable collections, missing source sheets, unrecoverable identities, and
download failures block replacement. All inputs and target JSON files are
validated before writes; individual writes are atomic, not a multi-file
transaction. The known quoted multiline row split in one historical converted
JSON is accepted only when its intact Excel course is verified, with a repair
entry and warning; otherwise it fails.

### Announcement sources

List titles come from the module containing the announcement list, falling back
to a standalone section heading, the current-page breadcrumb in the RPage path
module, or the document title rather than search or article headings. This avoids
including the website name when a list's module heading is hidden or absent.
`announcements_list.json` is the only source of list names for the content crawler:
content refreshes preserve its titles exactly, without extracting page headings or
overriding custom source names. Scheduled crawls leave this source list unchanged.
Failed, malformed, or empty refreshes retain known-good articles while applying
the configured source metadata to aggregate and individual files. Source titles
must be nonempty strings without NUL characters.
Run `nthu_announcements_list` manually to update existing source titles, including
removing website suffixes through the breadcrumb fallback. Custom source titles
remain explicitly configured by the source crawler. Parsed announcement titles
and dates normalize control characters (including `\u000b`) and repeated Unicode whitespace to
single spaces, without changing URLs.
After a successful title refresh, superseded individual files are removed only
when they belong to the same source; filename collisions block overwrites.
Legacy URL recovery first matches the full source metadata, then permits an
unambiguous department/language/hostname match when refreshed titles differ. Ambiguous
matches block the crawl rather than discarding known-good articles.

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

Library RSS article `link` is a nullable, validated HTTP(S) URL. Comma-separated
URL lists contribute only their first URL, including lists following a query
string; commas within a single URL are preserved. Slash-only relative entries
in a list require whitespace after the comma. Relative links resolve against
the library website. Missing, blank, or unrecoverable links become `null`; invalid
values are logged without dropping the article or falling back to a later URL.
RSS image URLs are also normalized before publication. An unrecoverable image
URL makes `image` null without removing the article; an invalid image hyperlink
makes only `image.link` null.

RSS titles, categories, dates, authors, and image titles are single-line text:
controls, newlines, tabs, and repeated Unicode whitespace collapse to one space.
Descriptions preserve line breaks, including `<br>` variants, but collapse
consecutive newlines and whitespace-only lines to one newline. Each line is
trimmed and its horizontal whitespace normalized. Blank optional text becomes
`null`; descriptions remain strings, including empty strings. Identifiers and
unknown metadata are preserved.

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
normalization and text cleanup, including when all RSS requests fail.
RSS titles must contain a non-whitespace character in both fresh and retained
feeds. Structural feed
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
