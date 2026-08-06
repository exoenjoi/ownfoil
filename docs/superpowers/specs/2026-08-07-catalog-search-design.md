# Catalog search ("Discover")

Search any Switch game by name from titledb — not only what the library already knows — and grab it
through the existing Prowlarr flow.

## Why

The downloader can only search for content the database already carries: a missing update, a missing
DLC, a base game whose title is already in `Titles`. There is no way to say "I want a game I do not
own at all". Everything needed is already present — titledb holds the whole catalog with names and
cover art, and the search/rank/grab chain works on plain dicts — so this is mostly plumbing plus a
page.

## Decisions taken

- **A dedicated `/discover` page**, not a mode inside the library. The library page already carries
  filters, three view modes, pagination and a tile-size control; mixing "what I own" with "what
  exists" would muddy the missing-content story the grouped view was built for.
- **Base games only.** A DLC without its base is useless, and once the base is owned the library's
  own 🔍 already covers its updates and DLCs.
- **Clicking a card opens the existing release modal.** No new auto-grab: the user sees the releases,
  including the ones the automatic job would refuse and why, and picks.
- **No index file.** Search scans the titledb already loaded in memory. See "Performance" below.

## Architecture

No database change, no Alembic revision, no new setting, no new Python module.

| Unit | Location | Responsibility |
|---|---|---|
| `search_base_games(query, limit)` | `app/titles.py` | scan `_titles_db`, keep base ids matching the query |
| `catalog_target(title_id)` | `app/downloader.py` | build a `target` dict for a game absent from the database |
| `GET /discover` | `app/app.py` | render the page, `@access_required('admin')` |
| `POST /api/catalog/search` | `app/app.py` | the name search |
| `app/templates/discover.html` | — | the results grid |
| `app/templates/release_modal.html` | — | the release modal, extracted so two pages can include it |

`titles.py` stays the only owner of `_titles_db`; nothing else reaches into it.

## Components

### `titles.search_base_games(query, limit=60)`

Returns a list of raw titledb records, or `None` when titledb is not loaded — the caller must be
able to tell "not available" from "no match", which is `[]`.

- Matching is case- and **accent-insensitive**: both the query and the candidate name are normalised
  with `unicodedata.normalize('NFKD')` and stripped of combining marks. Without this, `pokemon`
  finds nothing in a French library.
- Keeps records whose `id` ends in `000` (a base game). Records with a missing `id` or `name` are
  skipped rather than raising.
- Ordering: names *starting* with the query first, then the rest, each alphabetical. Searching
  `zelda` should not bury `The Legend of Zelda…` under `Hyrule Warriors…`.
- Returns at most `limit + 1` records. The route slices to `limit` and sets `truncated` when it
  received more than `limit` — returning exactly `limit` would leave "capped" and "exactly that
  many" indistinguishable.

### `downloader.catalog_target(title_id)`

```python
{'title_id': …, 'app_id': title_id, 'app_version': '0',
 'app_type': APP_TYPE_BASE, 'name': …, 'patch_level': 0}
```

For a base game the app id *is* the title id. Returns `None` when titledb has no name for the id.

`resolve_target()` gains a `catalog=False` argument. When true it returns `catalog_target(title_id)`
and never touches `Apps`. The flag is explicit so the library's existing 🔍 keeps its behaviour
exactly: without it, nothing changes on that path.

### `POST /api/catalog/search`

```
request   {"query": "zelda"}
success   {"success": true,  "errors": [], "results": [
             {"title_id", "name", "iconUrl", "bannerUrl", "owned"}], "truncated": false}
failure   {"success": false, "errors": [{"path": "catalog", "error": "…"}]}
```

Same envelope as the existing downloader endpoints. Ownership comes from one query —
`Apps.app_id IN (…) AND owned IS TRUE` — since a base game's app id equals its title id.

### Templates

`release_modal.html` is the current modal markup plus `openReleaseSearch`, `renderReleaseSearch`,
`grabRelease`, `escapeHtml` and `humanSize`, moved out of `index.html` unchanged and included by both
pages. This is the only existing, working code the feature disturbs — a move, not a rewrite.

`discover.html` reuses `.game-card`, `.card-img`, `.game-info`, `.game-title`, `.tags-container` and
`.game-tag` from the existing stylesheet. No new CSS. Search fires after 300 ms of quiet and at least
2 characters. An owned game shows an `Owned` badge and stays clickable — the user may want a
different release.

`nav.html` gains a Discover entry next to Downloads, behind the same admin condition.

## Data flow

```
type "zelda" ──300ms──> POST /api/catalog/search
                            │ @with_titledb
                            ├─ titles.search_base_games()
                            └─ Apps lookup for the owned flag
                        <── results
click a card ─────────> openReleaseSearch({title_id, catalog: true})
                        └─> /api/downloader/search → resolve_target(catalog=True)
                        └─> existing modal → existing grab → downloads.json
```

## Performance

The search scans the whole in-memory titledb, and `@with_titledb` loads it if it is not resident.
That cost is **already paid today**: `resolve_target` carries the same decorator, so every click on
the library's 🔍 already loads titledb — and that is fast enough in practice. Once loaded, matching a
few tens of thousands of names is milliseconds.

Marked with a `ponytail:` comment naming the ceiling and the exit: if the scan ever proves slow, a
slim `(id, name, iconUrl)` index built when titledb is downloaded replaces it behind the same
endpoint. Upstream 2.4.0 moves titledb into SQL (`titledb_store.py`, #318), which turns the scan into
a `LIKE` query and deletes the problem — another reason not to build the index now.

## Error handling

| Case | Behaviour |
|---|---|
| titledb not downloaded | `success: false`, same wording as the existing downloader endpoints |
| query under 2 characters | empty result, no scan |
| no match | empty state in the page |
| Prowlarr unconfigured | already surfaced by the modal |
| more than `limit` matches | results returned, `truncated: true`, page invites refining |

## Testing

No framework, no network, matching `app/test_*.py`.

- `app/test_titles.py` — `search_base_games` against a fake `_titles_db`: DLC and update ids are
  filtered out, accented and mixed-case names match, prefix matches sort first, the limit is
  respected, records missing `id` or `name` do not raise, and `None` comes back when titledb is
  unloaded.
- `app/test_downloader.py` — `catalog_target()` produces a valid target for a title absent from the
  database, and `None` when titledb has no name for it.

## Known limitation

`rank_releases()` is only tuned for updates: it rejects an update release carrying no version marker
because that is usually the base game. A base-game target passes through unranked by that rule, so
the ordering of results for a base game will be rough. Since no auto-grab is added, the consequence
is an imperfect sort, never a silent wrong download — the modal lists everything and the user picks.

## Out of scope

Pagination, region and category filters, "grab the latest update too", any new setting, and the
index file described under Performance.
