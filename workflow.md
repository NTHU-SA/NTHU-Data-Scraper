# Data publishing workflow

## Branch responsibilities

| Branch | Responsibility |
|---|---|
| `main` | Source, tests, tools, and documentation only; generated `data/` output is ignored and removed from history |
| `data` | Canonical generated dataset and static Pages files at branch root |
| `gh-pages` | Temporary, unchanged rollback branch pending production verification |

The `data` branch inherits the historical `main` ancestry. Its current tree is
data-only, while old source and generated-data commits remain reachable in
history.

`main` history has been rewritten to remove `data/` and commits that only
updated that directory. Source changes are retained with new commit IDs.
The `data`, `gh-pages`, and `archive/*` branches are unchanged by this cleanup
and still retain their historical commits; this is not a repository-wide
purge of generated data.

Each workflow run creates an ignored local `data/` directory from the latest
`data` branch before crawling, and only the `data` branch receives
generated-data commits.

Existing clones must refresh `origin/main` and base new work on the rewritten
history. Do not merge the old `main` history back into the cleaned branch;
reapply any unpublished source changes onto the new history instead.

## Scheduled lifecycle

```mermaid
flowchart TD
  snapshot[data branch snapshot] --> hydrate[Hydrate ignored local data directory]
  hydrate --> crawl[Run scheduled spiders from main]
  crawl --> validate[Validate all JSON and critical datasets]
  validate --> metadata[Generate file_details.json]
  metadata --> index[Generate index.html and .nojekyll]
  index --> commit[Commit changed snapshot to data]
```

The workflow runs on pushes to `main`, every two hours, and manual dispatch.
Its concurrency group permits only one publisher at a time and does not cancel
an in-progress publication. It has only `contents: write` permission.

Hydration excludes `.git`, `.nojekyll`, `CNAME`, `file_details.json`, and
`index.html`. Existing datasets are copied before crawling, so a spider that
does not run—or a library source that fails—does not erase its previous
published output. A preserved `CNAME` is restored during publication if one is
ever added to the `data` branch.

The regular spider set remains:

- `nthu_announcements_item`
- `nthu_buses`
- `nthu_courses`
- `nthu_dining`
- `nthu_libraries` (failure-isolated because upstream sites may reject hosted
  runner IPs)

Directory, maps, newsletters, announcement-list, and other legacy datasets are
preserved by hydration; Phase 1 does not expand the crawler schedule.

## Validation and metadata

`validate_data.py` rejects missing critical root datasets, empty JSON files,
and malformed JSON before publication. It validates generated
`file_details.json` in the final pass but does not count publishing metadata as
crawler data.

`generate_file_detail.py` hashes the exact bytes of each published data asset.
Unchanged hashes preserve their previous `last_updated`; changed and new files
receive an offset-aware Asia/Taipei timestamp. The top-level timestamp is the
newest meaningful file timestamp and therefore remains stable when no dataset
changes.

Publishing controls (`file_details.json`, `index.html`, `.nojekyll`, and
`CNAME`) are excluded from the inventory. For backward compatibility:

```text
last_commit == version == sha256
```

NTHU-Data-API treats `last_commit` as an opaque cache identity. It is no longer
necessarily a Git commit SHA. The generated index displays a SHA-256 prefix and
does not create Git commit links from content hashes.

## Dependency management

`pyproject.toml` and `uv.lock` are the only dependency sources.

```bash
uv sync
uv run pytest -q
uv run python -m scrapy crawl nthu_buses
```

CI uses Python 3.13, `astral-sh/setup-uv`, and frozen lockfile installs.

## Manual GitHub Pages cutover

Do not delete `gh-pages` during cutover.

1. Confirm `data` contains the complete root-level snapshot and at least one
   publication commit.
2. Open **Settings → Pages**.
3. Choose **Deploy from a branch**.
4. Select branch **data** and folder **/ (root)**.
5. Wait for deployment and verify <https://data.nthusa.tw/>.
6. Verify `/buses.json`, `/courses.json`, `/announcements.json`, and
   `/file_details.json`.
7. Verify NTHU-Data-API cache refresh behavior.
8. Wait for at least one scheduled crawl and confirm another normal commit can
   be pushed to `data`.
9. Only then consider deleting `gh-pages` in a separate operation.

If repository rules later protect `data`, GitHub Actions must be permitted to
push without weakening unrelated protections.

## Rollback

If production verification fails, set the Pages source back to
`gh-pages` / root. The legacy branch and archived pre-split history remain
unchanged, so a Pages rollback requires no history rewrite or force push.
Do not restore old ancestry to the cleaned `main` branch.
