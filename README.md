# NTHU-Data-Scraper

NTHU-Data-Scraper collects public National Tsing Hua University campus data and
publishes it at <https://data.nthusa.tw/>.

## Repository architecture

- `main` contains crawler source, tests, publishing tools, workflows,
  development documentation, and a temporarily retained legacy `data/`
  snapshot. The workflow never commits generated updates back to `main`.
- `data` contains the canonical generated snapshot at the branch root. This is
  the future GitHub Pages source (`data` / root).
- `gh-pages` is the unchanged legacy Pages snapshot retained temporarily for
  rollback. Delete it only after the `data` deployment and scheduled publishing
  cycle have been verified in production.

  The retained `main/data/` tree is a migration fallback, not the canonical
  publishing source. Scheduled runs overwrite their local copy from the latest
  `data` branch before crawling and publish changes only to `data`.

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

The scheduled workflow hydrates `main/data/` from the previous `data` snapshot,
runs the current scheduled spider set, validates every JSON file, generates
publishing metadata and the index, then creates a normal commit on `data`.
Untouched legacy datasets remain in the hydrated snapshot.

`file_details.json` now versions each exact published file with SHA-256.
`last_commit` is retained for NTHU-Data-API compatibility, but it is a
deprecated alias for the content version:

```text
last_commit == version == sha256
```

See [workflow.md](workflow.md) for the lifecycle, cutover, and rollback steps.

## License

This project is licensed under the [MIT License](LICENSE).
