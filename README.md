# NTHU-Data-Scraper

NTHU-Data-Scraper collects public National Tsing Hua University campus data and
publishes it at <https://data.nthusa.tw/>.

## Repository architecture

- `main` contains only crawler source, tests, publishing tools, workflows,
  and development documentation. Generated `data/` snapshots have been removed
  from its history, and local `data/` output is ignored by Git. The workflow
  never commits generated updates back to `main`.
- `data` contains the canonical generated snapshot at the branch root. This is
  the active GitHub Pages source (`data` / root).

These are the only remote branches. Legacy `gh-pages`, archive, and migration
branches have been removed after retaining the migration source changes in
`main`.

Scheduled runs create their local `data/` directory from the latest `data`
branch before crawling and publish changes only to `data`.

Public paths remain unchanged, including:

- <https://data.nthusa.tw/buses.json>
- <https://data.nthusa.tw/courses.json>
- <https://data.nthusa.tw/announcements.json>
- <https://data.nthusa.tw/file_details.json>

## Development

Python 3.13 and [uv](https://docs.astral.sh/uv/) are required.

```bash
uv sync
uv run pytest -q
uv run python -m scrapy crawl nthu_buses
uv run python -m scrapy crawl nthu_courses
```

For announcements, hydrate `data/` from the published snapshot before running
the item spider, or run the list spider first:

```bash
uv run python -m scrapy crawl nthu_announcements_list
uv run python -m scrapy crawl nthu_announcements_item
```

For a Playwright-based spider, install its browser only when needed:

```bash
uv run playwright install chromium
```

## Available spiders

- `nthu_announcements_list`: maintains the announcement source list
- `nthu_announcements_item`: refreshes announcement content from that list
- `nthu_buses`: scrapes campus bus schedules
- `nthu_courses`: fetches course information
- `nthu_dining`: retrieves dining data
- `nthu_directory`: downloads the department directory
- `nthu_maps`: gets campus map data
- `nthu_newsletters`: collects newsletters
- `nthu_libraries`: collects library RSS feeds and opening-hours calendars

## Publishing

The scheduled workflow hydrates an ignored local `data/` directory from the previous `data` snapshot,
validates that baseline, runs the current scheduled spider set, validates every JSON file, generates
publishing metadata and the index, then creates a normal commit on `data`.
Untouched legacy datasets remain in the hydrated snapshot.

### Data safety

The candidate snapshot is the previous known-good snapshot plus successfully
refreshed sources. Announcements merge by authoritative source link, buses by
component key, maps by map type, and libraries by RSS/calendar source. Failed
or empty refreshes retain existing non-empty data. Announcements leave the
aggregate only when removed from `announcements_list.json`; failed refreshes
do not delete their individual files.
Legacy post-redirect announcement URLs are matched to authoritative links
using unique department/title/language metadata. Ambiguous matches fail
instead of dropping or guessing the known-good source.

Directory and newsletter crawls retain their whole previous dataset on known
request/parser failures, malformed entries in a partial listing, or an empty
result. Courses validate the complete
collection and prepare semester records before writing any output. Dining
continues to leave its previous file untouched when parsing yields no data.

`nthu_scraper.storage` provides `read_json`, `read_json_optional`, and
`write_json_atomic`. Only a missing optional file returns a default; malformed
JSON and I/O errors raise. Writes serialize into a same-directory temporary
file, flush and fsync it, then replace the destination. Failed writes preserve
the destination, clean up temporary files, and raise. Dataset-specific
indentation and key ordering are retained.

The project's `scrapy crawl` command returns a failure exit status for
implementation errors, including errors Scrapy would otherwise only log.
Expected upstream failures are handled inside the crawlers. There is no
workflow-level exception for libraries: implementation or storage failures
block publication.

Atomicity is per file, not a transaction across the local snapshot. An error
can leave earlier successful writes in local `data/`, but CI will not publish
that candidate. These checks detect known failures and invalid/empty results;
they cannot prove that a non-empty, structurally plausible upstream response
is complete. Offline regression tests cover the stated fallback behavior.

Snapshot commits use `data(<changed-datasets>): update published snapshot`.
Sorted scopes come from actual staged dataset changes, and the commit body lists
the exact changed paths with generated publishing files in a separate section.
No snapshot commit is created when nothing changed.

`file_details.json` now versions each exact published file with SHA-256.
`last_commit` is retained for NTHU-Data-API compatibility, but it is a
deprecated alias for the content version:

```text
last_commit == version == sha256
```

See [workflow.md](workflow.md) for the lifecycle, deployment, and rollback steps.

## License

This project is licensed under the [MIT License](LICENSE).
