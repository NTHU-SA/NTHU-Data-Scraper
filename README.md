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
| Courses | [courses/latest.json](https://data.nthusa.tw/courses/latest.json) |
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

### Course sources and processing tool

Latest courses are available only at
[`courses/latest.json`](https://data.nthusa.tw/courses/latest.json).
`courses/semesters/<semester>.json` uses the same standard schema for each
semester. The former root `courses.json` is removed after a successful refresh;
it is not a compatibility alias. This is a breaking schema change: public
course files contain standard fields only, not the official JSON or a mixture
of raw and structured fields.

```text
uv run python -m scrapy crawl nthu_courses
```

The spider downloads **only the latest official JSON**. It does not visit the
source inventory or download historical attachments. Both scheduled and manual
workflow runs use this same operation; the old spider `backfill` and `rebuild`
modes and workflow `course_mode` input are removed.

Processing has three distinct storage layers:

| Layer | Location | Contents |
|---|---|---|
| Official originals | `courses/raw/<source-id>.json` or `.xlsx` | Original bytes, including JSON encoding and complete workbooks with auxiliary sheets; the current response is always `courses/raw/latest.json` |
| First-stage JSON | `courses/raw/converted/<source-id>.json` | Versioned UTF-8 records with original field names and values, row/sheet origins, supplemental-field origins, and the original SHA-256 |
| Public courses | `courses/latest.json`, `courses/semesters/<semester>.json` | Standard course fields only; latest contains only the current feed's courses |

First-stage conversion extracts the configured main course sheets and joins
the configured teacher supplement without applying public field names or
display-text cleanup. Other workbook sheets remain in the original Excel.
Normalization consumes these first-stage records; they are reusable inputs,
not just debug exports.

Download historical files manually from the
[official download page](https://curricul.site.nthu.edu.tw/p/404-1208-111356.php?Lang=zh-tw),
then import them with the offline tool:

```text
uv run python -m nthu_scraper.course_tool import --source 108-110 --input history.xlsx --data-folder data
uv run python -m nthu_scraper.course_tool import --source 10820 --input history.json --data-folder data
uv run python -m nthu_scraper.course_tool rebuild --data-folder data
```

Supported source IDs are `latest`, `10820`, `10910-11110`, `11120-11220`,
`108-110`, `111-113`, and `11410`; the last three require Excel. Sheet layouts
are explicitly configured, not inferred from arbitrary workbooks. `--data-folder`
defaults to `DATA_FOLDER` or `data`. Import archives the supplied file, creates
its first-stage JSON, and republishes using the other available local sources.
Rebuild makes no network requests and does not require every historical source.
Importing only history does not fabricate a latest feed; import `latest` or run
the spider to create `courses/latest.json`.

The reusable functions live in `nthu_scraper.course_data`: `convert_source`
extracts first-stage records, `merge_converted_sources` merges validated
first-stage documents, `normalize_course` builds the public schema, and
`publish_sources` coordinates archive validation and publication. The CLI and
spider use this same implementation.

Latest data is automatically split by semester even when no historical official
file exists. On a semester rollover the outgoing feed is preserved byte-for-byte
as `courses/raw/latest-<semester>.json`, with its own converted JSON. For feeds
covering multiple semesters, only semesters absent from the incoming feed are
replayed from this archive. Existing current-semester courses come from the new
feed, not an earlier latest archive.

Historical Excel has priority over historical JSON, which fills missing fields
or courses; the current latest feed has highest priority. **Finalized
add/drop-source replacement of an entire semester is not implemented here.**
An attachment's label alone does not declare a semester final. Only configured
main sheets create courses; the 11410 bilingual teacher supplement joins by ID.
Conflicting duplicates and unsupported source layouts fail explicitly.

`courses/sources.json` declares `path_base: "courses"`; original and converted
archive paths are relative to that directory. It records checksums, selected
sheets, actual semester coverage, gaps, merge conflicts, and verified repairs.
It does not add retrieval timestamps on each run. Row/field provenance stays in
first-stage records and internal merge diagnostics, not public course objects.
Existing raw archives without a first-stage file are converted automatically.
Missing tracked files, checksum mismatches, malformed intermediate documents,
and unsupported versions block publication; restore matching archived files
before retrying. A manually supplied source can replace its damaged original
historical archive through `import`.

Published-only legacy semesters are preserved byte-for-byte in
`courses/raw/retained-<semester>.json`. An explicit legacy adapter emits the
standard public schema while preserving existing structured values; it does not
mix legacy objects into public course lists. These backups are identified
separately as `retained_published_snapshots`, not recovered official sources.
`normalized_records`, `retained_records`, and `published_records` distinguish
their counts. An official source covering the same semester supersedes the
published-only snapshot, but its raw backup remains archived. Invalid or
unexpectedly changed retained data blocks publication.

### Standard course fields

| Fields | Meaning |
|---|---|
| `id`, `chinese_title`, `english_title` | Course identity and display titles; `id` retains its source spelling |
| `semester_code`, `department_code`, `course_number` | Useful string components of the course ID |
| `department_name`, `college_name`, `course_level_code`, `course_level`, `remote_teaching` | Available source metadata; missing historical metadata is not guessed |
| `note`, `limit_note`, `object`, `ge_type`, `ge_category`, `no_extra_selection` | Notes, enrollment restrictions/targets, general education information, and extra-selection restrictions |
| `meetings` | Ordered `{classroom, time, time_codes}` objects preserving all room/time pairs |
| `lecturers` | Paired `{name_zh, name_en}` objects when reliable; otherwise `{label}` entries, including units and “指導教授” |
| `expertises`, `programs`, `curriculum_requirements` | Specialty objects, program-name strings, and `{target, requirement}` objects |
| `credits`, `capacity`, `capacity_unlimited`, `enrolled_count`, `reserved_for_freshmen` | Typed numeric values and explicit unlimited status; fractional credits are supported |
| `enrollment_after_selection`, `enrollment_after_withdrawal` | Different official enrollment checkpoints; neither substitutes for `enrolled_count` |
| `is_cancelled`, `language_code` | Official cancellation state and `zh`/`en`, or `null` when unknown |
| `prerequisite_text` | HTML/entity-cleaned text, not an executable eligibility rule |
| `parsing_issues` | Explicit diagnostics for values that cannot be reliably interpreted |

Removed public duplicates include `credit`, `size_limit`, `student_count`,
`freshman_reservation`, `lecturer`, `lecturer_names_zh`, `lecturer_names_en`,
top-level `classroom`, `time`, `class_room_and_time`, `expertise`, `program`,
`required_optional_note`, `prerequisite`, `suspend`, `language`, and
`source_semester`. Source semester disagreements still produce diagnostics.
Per-course `sources` and `field_sources` are also removed.

Empty lists remain `[]`; useful unknown typed values remain `null`. Blank
capacity means unlimited, not unknown; zero remains zero. Time codes remain
official period codes, not guessed clock times. Teacher supplements that cannot
be paired do not create guessed bilingual names: original names remain in raw
and the public object reports the ambiguity.

Unexpected values are archived, logged, and reported in `parsing_issues`.
Unparseable collections, missing sheets, unrecoverable identities, and download
failures block replacement. All candidate inputs and target JSON files are
validated and serialized before writes; writes are individually atomic, not a
multi-file transaction. Identical inputs preserve file bytes and modification
times. The known historical quoted-row conversion defect is repaired only when
the intact Excel record verifies recovery, with a warning and manifest entry.

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
