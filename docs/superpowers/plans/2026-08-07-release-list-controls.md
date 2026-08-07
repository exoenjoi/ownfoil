# Release List Controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Drop dead torrents from the release modal, let the user sort it by clicking a column, and show each release's date.

**Architecture:** One guard server-side in `rank_releases()`, where both the automatic job and the modal route through. Everything else is client-side in the shared release modal partial: a date column reading a field that already reaches the browser, and an in-place sort of the results array.

**Tech Stack:** Python 3, Flask, jQuery + Bootstrap 5 templates. Tests are plain asserts run by `python app/test_downloader.py` — no pytest, no framework, no network.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-07-release-list-controls-design.md`. Read it before starting.
- Branch: `downloader`.
- The zero-seeder drop is **unconditional** — it must not depend on the `min_seeders` filter.
- The sort must mutate `releaseSearchResults` **in place**. `grabRelease(index, button)` looks a release up by its index in that array; sorting a copy makes the Grab button download the wrong release.
- The default order stays the ranking score. Sorting is opt-in.
- Run the whole suite before every commit: `/Users/jalbert/claude-code/ownfoil/.venv/bin/python app/test_titles.py && … app/test_downloader.py && … app/test_organizer.py`.
- Commit messages: imperative subject, blank line, why-focused body, and the trailer `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `app/downloader.py` | modify | skip zero-seeder releases in `rank_releases()`, log how many |
| `app/test_downloader.py` | modify | cover the drop, including when `min_seeders` is 0 |
| `app/templates/release_modal.html` | modify | date column, sortable headers, in-place sort, honest empty message |

---

### Task 1: Drop dead torrents server-side

**Files:**
- Modify: `app/downloader.py` — inside `rank_releases()` (starts line 38), in the `for release in releases:` loop after `seeders` is read (line 63)
- Test: `app/test_downloader.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `rank_releases(releases, target, filters)` keeps its signature and return shape — a list of annotated release dicts — but never returns one whose `seeders` is 0.

- [ ] **Step 1: Write the failing tests**

Append to `app/test_downloader.py`, before the `if __name__ == '__main__':` block:

The file already has a `release(title, seeders=50, size=1024 ** 3, guid=None)` factory (line 30) and a
`FILTERS` dict with `min_seeders: 3` (line 16). Use them:

```python
def dead_and_alive():
    """One unusable release, one merely below the seeder threshold."""
    return [
        release('Mario Kart 8 Deluxe [v196608].nsp', seeders=0, guid='dead'),
        release('Mario Kart 8 Deluxe [v196608].nsp', seeders=1, guid='thin'),
    ]


def test_a_dead_torrent_is_dropped_not_greyed():
    # 0 seeders is not an override opportunity, it is undownloadable.
    ranked = rank_releases(dead_and_alive(), UPDATE_TARGET, FILTERS)
    assert [r['guid'] for r in ranked] == ['thin']


def test_a_release_below_the_threshold_is_kept_and_greyed():
    # 1 seeder with a minimum of 3 is a rejection the user may still want to override.
    ranked = rank_releases(dead_and_alive(), UPDATE_TARGET, FILTERS)
    assert ranked[0]['rejected'] and 'seeder' in ranked[0]['rejected']


def test_a_dead_torrent_is_dropped_even_with_no_minimum():
    # min_seeders=0 makes nothing "rejected" for seeders, but dead is still dead.
    ranked = rank_releases(dead_and_alive(), UPDATE_TARGET, dict(FILTERS, min_seeders=0))
    assert [r['guid'] for r in ranked] == ['thin']
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `/Users/jalbert/claude-code/ownfoil/.venv/bin/python app/test_downloader.py`
Expected: FAIL on `test_a_dead_torrent_is_dropped_not_greyed` — the dead release is still in the list.

- [ ] **Step 3: Write the implementation**

In `app/downloader.py`, inside `rank_releases`, replace the start of the loop body:

```python
    ranked = []
    for release in releases:
        release = dict(release)
        title = release.get('title') or ''
        title_norm = _norm(title)
        seeders = int(release.get('seeders') or 0)
```

with:

```python
    ranked = []
    dead = 0
    for release in releases:
        release = dict(release)
        title = release.get('title') or ''
        title_norm = _norm(title)
        seeders = int(release.get('seeders') or 0)

        # A release nobody seeds cannot be downloaded at all, so it is not an override
        # the user might want — it is noise. Dropped whatever min_seeders is set to.
        if seeders == 0:
            dead += 1
            continue
```

Then find the `return` at the end of `rank_releases` and add the log immediately before it:

```python
    if dead:
        logger.info(f'[downloader] Ignored {dead} release(s) with no seeder.')
```

- [ ] **Step 4: Run the whole suite to verify it passes**

Run:
```bash
/Users/jalbert/claude-code/ownfoil/.venv/bin/python app/test_downloader.py
/Users/jalbert/claude-code/ownfoil/.venv/bin/python app/test_titles.py
/Users/jalbert/claude-code/ownfoil/.venv/bin/python app/test_organizer.py
```
Expected: every line prefixed `ok `. The pre-existing downloader tests must still pass — if one now fails because its fixture had `seeders=0`, that fixture was relying on the old behaviour: give it a non-zero value rather than weakening the guard.

- [ ] **Step 5: Commit**

```bash
git add app/downloader.py app/test_downloader.py
git commit -m "Drop releases nobody seeds

A rejected release is an override the user may want; a release with zero
seeders is undownloadable, so listing it is noise. Dropped in rank_releases
so the automatic job and the modal both stop seeing them.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: Date column and sortable headers

**Files:**
- Modify: `app/templates/release_modal.html` — `renderReleaseSearch()` at line 45, and the state block at the top (line 4)

**Interfaces:**
- Consumes: `rank_releases` output from Task 1; each release dict carries `publish_date` already, produced by `prowlarr._release()` (`app/prowlarr.py:59`).
- Produces: `sortReleases(key)` as a global function, called from the `onClick` of each sortable header.

- [ ] **Step 1: Add the sort state**

At the top of the `<script>` in `app/templates/release_modal.html`, next to `let releaseSearchResults = [];`, add:

```javascript
    // Default order is the ranking score: sorting is something the user asks for.
    let releaseSort = {key: null, dir: 1};
```

And in `openReleaseSearch`, next to the existing `releaseSearchResults = [];` reset, add:

```javascript
        releaseSort = {key: null, dir: 1};
```

- [ ] **Step 2: Add the sort function**

Add after `renderReleaseSearch()`:

```javascript
    const SORT_KEYS = {
        title: r => (r.title || '').toLowerCase(),
        size: r => r.size || 0,
        seeders: r => r.seeders || 0,
        publish_date: r => r.publish_date || '',
    };

    function sortReleases(key) {
        releaseSort = {key: key, dir: releaseSort.key === key ? -releaseSort.dir : 1};
        const pick = SORT_KEYS[key];
        // Sorted in place: grabRelease() finds its release by index in this very array,
        // so a sorted copy would make the Grab button download the wrong one.
        releaseSearchResults.sort((a, b) => {
            const x = pick(a), y = pick(b);
            return x < y ? -releaseSort.dir : x > y ? releaseSort.dir : 0;
        });
        renderReleaseSearch();
    }
```

- [ ] **Step 3: Render the date column and the clickable headers**

In `renderReleaseSearch`, replace the row template (lines 53-64) so it gains a date cell after the S/L cell:

```javascript
        const rows = releaseSearchResults.map((release, index) => {
            const rejected = release.rejected;
            return `<tr class="${rejected ? 'opacity-50' : ''}">
                <td class="small">${escapeHtml(release.title)}
                    ${rejected ? `<div class="text-warning">${escapeHtml(rejected)}</div>` : ''}</td>
                <td class="small text-nowrap">${escapeHtml(release.indexer)}</td>
                <td class="small text-nowrap">${humanSize(release.size)}</td>
                <td class="small text-nowrap">${release.seeders} / ${release.leechers}</td>
                <td class="small text-nowrap">${escapeHtml((release.publish_date || '').slice(0, 10))}</td>
                <td class="text-end"><button class="btn btn-sm ${rejected ? 'btn-outline-secondary' : 'btn-primary'}"
                    onClick="grabRelease(${index}, this)">Grab</button></td>
            </tr>`;
        });
```

And replace the `<thead>` line (line 69) with:

```javascript
                <thead><tr>
                    ${sortableHeader('Release', 'title')}
                    <th>Indexer</th>
                    ${sortableHeader('Size', 'size')}
                    ${sortableHeader('S/L', 'seeders')}
                    ${sortableHeader('Date', 'publish_date')}
                    <th></th>
                </tr></thead>
```

Add this helper next to `sortReleases`:

```javascript
    function sortableHeader(label, key) {
        const caret = releaseSort.key === key ? (releaseSort.dir > 0 ? ' ▲' : ' ▼') : '';
        return `<th role="button" style="cursor: pointer" onClick="sortReleases('${key}')">${label}${caret}</th>`;
    }
```

- [ ] **Step 4: Make the empty message honest**

Line 50 currently reads `'<div class="alert alert-warning">Prowlarr returned no result for this search.</div>'`. With dead torrents dropped server-side that sentence can be false, so replace the text with:

```javascript
                '<div class="alert alert-warning">No usable release found.</div>');
```

- [ ] **Step 5: Verify the templates parse and the suite is green**

Run:
```bash
/Users/jalbert/claude-code/ownfoil/.venv/bin/python -c "
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('app/templates'))
for t in ('index.html', 'discover.html', 'release_modal.html'):
    env.parse(open('app/templates/' + t).read())
print('templates parse')
"
/Users/jalbert/claude-code/ownfoil/.venv/bin/python app/test_downloader.py
```
Expected: `templates parse`, then every test line prefixed `ok `.

- [ ] **Step 6: Commit**

```bash
git add app/templates/release_modal.html
git commit -m "Sort the release list and show each release's date

publish_date already reached the browser unused. The sort mutates the results
array in place because grabRelease() finds its release by index in it.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: Verify the modal in a browser

The sorting is JavaScript and this project has no JS test framework, so it gets the same treatment the Discover page got: a standalone page built from the real template, then DOM assertions.

**Files:**
- Create: a build script in the session scratchpad directory (not in the repo)

- [ ] **Step 1: Build a standalone preview**

Write a script in the scratchpad that reads `app/templates/release_modal.html`, wraps it in a minimal HTML document with jQuery and Bootstrap from their CDNs, defines `releaseSearchTarget` and `releaseSearchResults` with six fake releases of varying `size`, `seeders`, `publish_date` and `title`, calls `renderReleaseSearch()`, and shows the modal. Serve it with `python -m http.server`; Playwright refuses `file:` URLs.

Give at least one fake release a `rejected` reason so the greyed-out styling is exercised, and one an empty `publish_date` so the date cell's fallback is exercised.

- [ ] **Step 2: Assert the sort works**

With Playwright, evaluate on the page:

- clicking the `Size` header orders the rendered rows by ascending size;
- clicking it again reverses them, and the caret flips;
- clicking `Date` orders by date;
- **after sorting, the `onClick="grabRelease(N, this)"` index on each row still points at the release whose title is rendered in that row.** This is the regression the whole task exists to catch: stub `grabRelease` to record the index it receives, click the Grab button of a known row, and assert `releaseSearchResults[recordedIndex].title` equals the title shown in that row.

- [ ] **Step 3: Take a screenshot and look at it**

Screenshot the modal and read the image. The DOM assertions cannot see a column overflowing the dialog or a caret rendering as a broken glyph.

- [ ] **Step 4: Record the outcome**

If anything failed, fix it and re-run Steps 2-3 before continuing. Report to the user what the assertions covered and attach what the screenshot showed.

---

## Manual verification

For the user, on their instance, after the image is rebuilt:

1. A search no longer lists releases with `0 / 0` in the S/L column.
2. Clicking `Size`, `S/L` or `Date` reorders the list; clicking again reverses it.
3. The date column shows something like `2019-04-23`.
4. **The key regression check:** sort by any column, then grab a release — the download that appears on the Downloads page must be the one whose row you clicked.
