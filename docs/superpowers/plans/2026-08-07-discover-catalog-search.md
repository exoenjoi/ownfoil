# Discover Catalog Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user search any Switch base game by name from titledb and grab it through the existing Prowlarr flow, from a new `/discover` page.

**Architecture:** A name search over the titledb dict already held in memory by `titles.py`, a target builder that bypasses the `Apps` table, two routes, and a card grid reusing the library's stylesheet. The existing release modal moves into a shared partial so both pages can include it. No database change, no Alembic revision, no new setting, no new Python module.

**Tech Stack:** Python 3, Flask, SQLAlchemy, jQuery + Bootstrap 5 templates, `nsz` for titledb containers. Tests are plain asserts run by `python app/test_*.py` — no pytest, no framework, no network.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-07-catalog-search-design.md`. Read it before starting.
- Branch: `downloader`. This feature does not go on `master`.
- No Alembic migration. The fork deliberately has zero revisions — see `FORK.md`.
- Any new setting must be added to `DEFAULT_SETTINGS` in `constants.py` or it is silently deleted on the next load. This feature adds none.
- `titles.py` is the only module allowed to touch `_titles_db`.
- Tests follow the existing convention: module docstring naming the run command, `sys.path.insert` of the app dir, plain `assert`, and the `if __name__ == '__main__'` loop that prints `ok <name>`. Copy the shape from `app/test_organizer.py`.
- Run the whole suite before every commit: `python app/test_titles.py && python app/test_downloader.py && python app/test_organizer.py`. The interpreter with dependencies installed is `/Users/jalbert/claude-code/ownfoil/.venv/bin/python`.
- Commit messages: imperative subject, blank line, why-focused body, and the trailer `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `app/titles.py` | modify | add `_fold()` and `search_base_games()` next to `get_game_info()` |
| `app/test_titles.py` | modify | cover the name search |
| `app/downloader.py` | modify | add `catalog_target()` and `search_catalog()`, extend `resolve_target()` |
| `app/test_downloader.py` | modify | cover `catalog_target()` |
| `app/app.py` | modify | add `GET /discover` and `POST /api/catalog/search`, pass `catalog` through the existing search route |
| `app/templates/release_modal.html` | create | the release modal markup and its JS, moved out of `index.html` |
| `app/templates/index.html` | modify | drop the moved block, include the partial |
| `app/templates/discover.html` | create | the search box and the results grid |
| `app/templates/nav.html` | modify | add the Discover entry |

---

### Task 1: Name search over titledb

**Files:**
- Modify: `app/titles.py` (add `import unicodedata` to the imports at the top; add the two functions after `get_game_info`, which ends around line 320)
- Test: `app/test_titles.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `titles.search_base_games(query, limit=60) -> list[dict] | None`. Each dict is a raw titledb record carrying at least `id`, `name`, and usually `iconUrl` and `bannerUrl`. Returns `None` when titledb is not loaded, `[]` when nothing matches, and at most `limit + 1` records otherwise.

- [ ] **Step 1: Write the failing tests**

Append to `app/test_titles.py`, and add `import titles` to its imports (it currently imports only names from `titles`):

```python
FAKE_TITLES = {
    'k1': {'id': '01006000040C2000', 'name': "Yoshi's Crafted World", 'iconUrl': 'i1', 'bannerUrl': 'b1'},
    'k2': {'id': '0100000000010000', 'name': 'Super Mario Odyssey', 'iconUrl': 'i2', 'bannerUrl': 'b2'},
    'k3': {'id': '010003F003A34800', 'name': 'Pokemon Update', 'iconUrl': 'i3', 'bannerUrl': 'b3'},
    'k4': {'id': '01009BF0072D5001', 'name': 'Captain Toad DLC', 'iconUrl': 'i4', 'bannerUrl': 'b4'},
    'k5': {'id': '0100ABCDEF012000', 'name': 'Pokémon Écarlate', 'iconUrl': 'i5', 'bannerUrl': 'b5'},
    'k6': {'id': '0100111111112000', 'name': None, 'iconUrl': 'i6', 'bannerUrl': 'b6'},
    'k7': {'id': None, 'name': 'No id at all', 'iconUrl': 'i7', 'bannerUrl': 'b7'},
    'k8': {'id': '0100222222222000', 'name': 'A Game About Pokemon', 'iconUrl': 'i8', 'bannerUrl': 'b8'},
}


def with_fake_titledb(fake):
    """Swap the module-level titledb, returning a restore callable."""
    previous = titles._titles_db
    titles._titles_db = fake

    def restore():
        titles._titles_db = previous
    return restore


def search(query, limit=60):
    restore = with_fake_titledb(FAKE_TITLES)
    try:
        return titles.search_base_games(query, limit)
    finally:
        restore()


def test_only_base_games_are_returned():
    # Update ids end in 800 and DLC ids in something else; neither is grabbable on its own.
    names = [r['name'] for r in search('o')]
    assert 'Pokemon Update' not in names
    assert 'Captain Toad DLC' not in names


def test_the_match_ignores_case_and_accents():
    # Without folding, a French library is unsearchable from an ASCII keyboard.
    assert [r['id'] for r in search('ecarlate')] == ['0100ABCDEF012000']
    assert [r['id'] for r in search('POKÉMON É')] == ['0100ABCDEF012000']


def test_prefix_matches_come_first():
    names = [r['name'] for r in search('pokemon')]
    assert names == ['Pokémon Écarlate', 'A Game About Pokemon']


def test_the_limit_leaves_room_to_detect_truncation():
    # limit + 1 records come back so the caller can tell "capped" from "exactly that many".
    assert len(search('pokemon', limit=1)) == 2


def test_records_missing_a_name_or_an_id_are_skipped():
    assert search('no id at all') == []
    assert all(r['name'] for r in search('o'))


def test_a_blank_query_matches_nothing():
    assert search('   ') == []


def test_an_unloaded_titledb_returns_none():
    restore = with_fake_titledb(None)
    try:
        assert titles.search_base_games('zelda') is None
    finally:
        restore()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `/Users/jalbert/claude-code/ownfoil/.venv/bin/python app/test_titles.py`
Expected: FAIL with `AttributeError: module 'titles' has no attribute 'search_base_games'`.

- [ ] **Step 3: Write the implementation**

Add `import unicodedata` alongside the other stdlib imports at the top of `app/titles.py`, then add after `get_game_info`:

```python
def _fold(text):
    """Lowercase and strip accents, so 'pokemon' matches 'Pokémon'."""
    decomposed = unicodedata.normalize('NFKD', text or '')
    return ''.join(c for c in decomposed if not unicodedata.combining(c)).lower()


def search_base_games(query, limit=60):
    """Base games from titledb whose name contains the query.

    Returns None when titledb is not loaded, so the caller can tell that apart from
    an empty result. Returns up to limit + 1 records for the same reason: exactly
    limit would be indistinguishable from a capped list. Names starting with the
    query come first — searching 'zelda' should not bury the Zelda games.
    """
    global _titles_db
    if _titles_db is None:
        logger.error("titles_db is not loaded. Call load_titledb first.")
        return None

    needle = _fold(query).strip()
    if not needle:
        return []

    matches = []
    for record in _titles_db.values():
        app_id, name = record.get('id'), record.get('name')
        # An update id ends in 800 and a DLC id in something else; only a base game
        # can be grabbed on its own.
        if not app_id or not name or not app_id.endswith('000'):
            continue
        folded = _fold(name)
        if needle in folded:
            matches.append((not folded.startswith(needle), folded, record))

    matches.sort(key=lambda match: match[:2])
    return [match[2] for match in matches[:limit + 1]]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `/Users/jalbert/claude-code/ownfoil/.venv/bin/python app/test_titles.py`
Expected: PASS — every line prefixed `ok `, including the four pre-existing CNMT tests.

- [ ] **Step 5: Commit**

```bash
git add app/titles.py app/test_titles.py
git commit -m "Search titledb base games by name

Accent- and case-insensitive, prefix matches first, and one record past the
limit so a capped result is distinguishable from an exact one.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: A target for a game absent from the library

**Files:**
- Modify: `app/downloader.py` (extend the `constants` import on line 12; add `catalog_target` next to `_game_name` around line 138; extend `resolve_target` at line 190; add `search_catalog` after `resolve_target`)
- Test: `app/test_downloader.py`

**Interfaces:**
- Consumes: `titles.search_base_games(query, limit)` from Task 1.
- Produces:
  - `downloader.catalog_target(title_id) -> dict | None` — the same shape `_target()` produces: keys `title_id`, `app_id`, `app_version`, `app_type`, `name`, `patch_level`.
  - `downloader.resolve_target(app_id=None, app_version=None, title_id=None, catalog=False)` — unchanged behaviour unless `catalog=True`.
  - `downloader.search_catalog(query, limit=60) -> dict | None` — `{'results': [...], 'truncated': bool}` where each result is `{'title_id', 'name', 'iconUrl', 'bannerUrl', 'owned'}`. `None` when titledb is unloaded.

- [ ] **Step 1: Write the failing tests**

Append to `app/test_downloader.py`, and add `import downloader` to its imports:

```python
def with_fake_game_info(name):
    """Swap the titledb lookup downloader uses, returning a restore callable."""
    previous = downloader.titles_lib.get_game_info
    downloader.titles_lib.get_game_info = lambda title_id: {'name': name} if name else None

    def restore():
        downloader.titles_lib.get_game_info = previous
    return restore


def test_catalog_target_describes_a_base_game():
    # A game absent from the library has no Apps row, so the target is built from
    # titledb alone. For a base game the app id is the title id.
    restore = with_fake_game_info("Yoshi's Crafted World")
    try:
        target = downloader.catalog_target('01006000040C2000')
    finally:
        restore()
    assert target == {
        'title_id': '01006000040C2000',
        'app_id': '01006000040C2000',
        'app_version': '0',
        'app_type': 'BASE',
        'name': "Yoshi's Crafted World",
        'patch_level': 0,
    }


def test_catalog_target_without_a_known_name_is_none():
    restore = with_fake_game_info(None)
    try:
        assert downloader.catalog_target('01006000040C2000') is None
    finally:
        restore()
```

Note: `APP_TYPE_BASE` is `'BASE'` (`constants.py:106`), so the literal in the assertion is correct.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `/Users/jalbert/claude-code/ownfoil/.venv/bin/python app/test_downloader.py`
Expected: FAIL with `AttributeError: module 'downloader' has no attribute 'catalog_target'`.

- [ ] **Step 3: Write the implementation**

Change the constants import on line 12 of `app/downloader.py`:

```python
from constants import APP_TYPE_BASE, APP_TYPE_DLC, APP_TYPE_UPD
```

Add after `_game_name`:

```python
def catalog_target(title_id):
    """Target for a base game that is not in the library at all.

    No Apps row exists for it, so everything comes from titledb. A base game's app
    id is its title id.
    """
    name = _game_name(title_id)
    if not name:
        return None
    return {
        'title_id': title_id,
        'app_id': title_id,
        'app_version': '0',
        'app_type': APP_TYPE_BASE,
        'name': name,
        'patch_level': 0,
    }
```

Change the `resolve_target` signature and add the branch as its first statement:

```python
def resolve_target(app_id=None, app_version=None, title_id=None, catalog=False):
    """Target of a manual search from the UI.

    Accepts an exact app, an app id whose latest missing version is picked, or a title id
    whose latest missing update is picked. Resolving here rather than in the browser keeps
    the app id arithmetic (base id -> update id) in one place.

    catalog=True means the title comes from the Discover page and has no Apps row: the
    flag is explicit so the library's own search keeps its behaviour untouched.
    """
    if catalog:
        return catalog_target(title_id) if title_id else None
    if app_id and app_version:
```

Leave the rest of the function as is. Add after it:

```python
@with_titledb
def search_catalog(query, limit=60):
    """Base games matching the query, flagged with whether the library owns them."""
    records = titles_lib.search_base_games(query, limit)
    if records is None:
        return None

    truncated = len(records) > limit
    records = records[:limit]
    title_ids = [record['id'] for record in records]
    owned = set()
    if title_ids:
        owned = {app.app_id for app in Apps.query.filter(
            Apps.app_id.in_(title_ids), Apps.owned.is_(True)).all()}

    return {
        'results': [{
            'title_id': record['id'],
            'name': record['name'],
            'iconUrl': record.get('iconUrl'),
            'bannerUrl': record.get('bannerUrl'),
            'owned': record['id'] in owned,
        } for record in records],
        'truncated': truncated,
    }
```

`search_catalog` must be defined after `with_titledb` (line 141) for the decorator to resolve.

- [ ] **Step 4: Run the whole suite to verify it passes**

Run: `/Users/jalbert/claude-code/ownfoil/.venv/bin/python app/test_downloader.py && /Users/jalbert/claude-code/ownfoil/.venv/bin/python app/test_titles.py`
Expected: PASS for both, including the ten pre-existing downloader tests.

- [ ] **Step 5: Commit**

```bash
git add app/downloader.py app/test_downloader.py
git commit -m "Build a search target for a game absent from the library

The Discover page finds titles with no Apps row, so the target comes from
titledb alone. The catalog flag is explicit so the library's own search path
is unchanged.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: The routes

**Files:**
- Modify: `app/app.py` (add the page route next to `downloads_page` at line 276; add the API route next to the downloader endpoints around line 487; change the `resolve_target` call on line 493)

**Interfaces:**
- Consumes: `downloader.search_catalog(query, limit)` and `downloader.resolve_target(..., catalog=)` from Task 2.
- Produces: `GET /discover` rendering `discover.html`, and `POST /api/catalog/search` with the envelope described below. No later task depends on Python names from this one.

- [ ] **Step 1: Add the page route**

After `downloads_page` in `app/app.py`:

```python
@app.route('/discover')
@access_required('admin')
def discover_page():
    return render_template('discover.html', title='Discover',
                           admin_account_created=admin_account_created())
```

- [ ] **Step 2: Add the search endpoint**

After `search_downloader_api` in `app/app.py`:

```python
CATALOG_SEARCH_LIMIT = 60

@app.post('/api/catalog/search')
@access_required('admin')
def search_catalog_api():
    query = ((request.json or {}).get('query') or '').strip()
    # Two characters is the floor: one letter matches most of the catalog and the
    # scan is wasted work.
    if len(query) < 2:
        return jsonify({'success': True, 'errors': [], 'results': [], 'truncated': False})
    try:
        found = downloader_lib.search_catalog(query, CATALOG_SEARCH_LIMIT)
    except FileNotFoundError:
        found = None
    if found is None:
        return jsonify({'success': False, 'errors': [
            {'path': 'catalog', 'error': 'TitleDB is not available yet, scan the library first.'}]})
    return jsonify({'success': True, 'errors': [], **found})
```

- [ ] **Step 3: Pass the catalog flag through the existing search route**

On line 493 of `app/app.py`, change:

```python
        target = downloader_lib.resolve_target(data.get('app_id'), data.get('app_version'),
                                               data.get('title_id'))
```

to:

```python
        target = downloader_lib.resolve_target(data.get('app_id'), data.get('app_version'),
                                               data.get('title_id'),
                                               catalog=bool(data.get('catalog')))
```

- [ ] **Step 4: Verify the module still imports**

Run: `cd app && /Users/jalbert/claude-code/ownfoil/.venv/bin/python -c "import ast, sys; ast.parse(open('app.py').read()); print('app.py parses')"`
Expected: `app.py parses`. The app cannot be started here — titledb fails to download in this sandbox — so a parse check plus the template check in Task 5 is the available verification.

- [ ] **Step 5: Commit**

```bash
git add app/app.py
git commit -m "Serve the Discover page and its catalog search

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: Extract the release modal into a shared partial

This task changes no behaviour. It only moves code so Task 5 can reuse it. Verify by loading the library page and confirming the 🔍 badge still opens the modal and grabs.

**Files:**
- Create: `app/templates/release_modal.html`
- Modify: `app/templates/index.html`

**Interfaces:**
- Consumes: nothing.
- Produces: a template partial defining the global JS functions `openReleaseSearch(payload)`, `renderReleaseSearch()`, `grabRelease(index, button)`, `escapeHtml(text)`, `humanSize(bytes)`, plus the `#releaseSearchModal` markup. Task 5 calls `openReleaseSearch`.

- [ ] **Step 1: Create the partial**

Create `app/templates/release_modal.html` containing, in this order:

1. A `<script>` tag holding, moved **verbatim** from `app/templates/index.html`: the `releaseSearchTarget` and `releaseSearchResults` declarations, and the functions `escapeHtml`, `humanSize`, `openReleaseSearch`, `renderReleaseSearch` and `grabRelease`.
2. The `<div class="modal fade" id="releaseSearchModal" …>` block, moved verbatim (currently lines 913-927 of `index.html`).

Do **not** move `missingContentSearchButton` — it takes a library `group` object and belongs to the library page.

Prepend this comment inside the `<script>`:

```html
<!-- Shared by the library and Discover: both open the same release list. -->
```

- [ ] **Step 2: Remove the moved block from index.html and include the partial**

Delete from `index.html` the declarations and five functions listed above, and the `#releaseSearchModal` div. Keep `missingContentSearchButton` and the `// ---------------------------------------------------------- downloader` comment above it.

After the closing `</script>` and before `{% endblock %}`, add:

```html
{% include 'release_modal.html' %}
```

- [ ] **Step 3: Verify nothing was lost**

Run:

```bash
grep -c "function openReleaseSearch\|function renderReleaseSearch\|function grabRelease\|function escapeHtml\|function humanSize" app/templates/release_modal.html
grep -c "releaseSearchModal" app/templates/release_modal.html
grep -c "openReleaseSearch\|renderReleaseSearch\|grabRelease\|escapeHtml\|humanSize\|releaseSearchModal" app/templates/index.html
grep -c "missingContentSearchButton" app/templates/index.html
```

Expected: `5`, then `2` or more, then `1` (only the `openReleaseSearch` call inside `missingContentSearchButton`), then `2`.

- [ ] **Step 4: Verify both templates still parse**

Run:

```bash
/Users/jalbert/claude-code/ownfoil/.venv/bin/python -c "
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('app/templates'))
for t in ('index.html', 'release_modal.html'):
    env.parse(open('app/templates/' + t).read())
print('templates parse')
"
```

Expected: `templates parse`.

- [ ] **Step 5: Commit**

```bash
git add app/templates/index.html app/templates/release_modal.html
git commit -m "Extract the release modal so two pages can include it

Pure move, no behaviour change: Discover needs the same modal the library
already opens.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: The Discover page

**Files:**
- Create: `app/templates/discover.html`
- Modify: `app/templates/nav.html`

**Interfaces:**
- Consumes: `POST /api/catalog/search` from Task 3, and `openReleaseSearch({title_id, catalog: true})` from Task 4.
- Produces: the user-facing page. Nothing depends on it.

- [ ] **Step 1: Create the page**

Create `app/templates/discover.html`:

```html
{% extends "base.html" %}

{% block content %}
{% include 'nav.html' %}
<div class="container-fluid mt-3">

    <div class="row justify-content-center">
        <div class="col-12 col-lg-8">
            <input type="search" id="catalogQuery" class="form-control form-control-lg"
                   placeholder="Search any Switch game by name..." autofocus>
            <div id="catalogStatus" class="text-body-secondary small mt-2"></div>
        </div>
    </div>

    <!-- .library-grid is the library's own layout class: auto-fill columns sized by
         --tile, which falls back to 220px without the library's size slider. -->
    <div id="catalogGrid" class="library-grid mt-3"></div>
</div>

<script>
    // The catalog is titledb, not the library: a result is a game that exists, owned or not.
    let catalogTimer = null;

    $('#catalogQuery').on('input', function () {
        const query = $(this).val();
        clearTimeout(catalogTimer);
        // Debounced: the server scans the whole titledb, one scan per keystroke is one too many.
        catalogTimer = setTimeout(() => searchCatalog(query), 300);
    });

    function searchCatalog(query) {
        if (query.trim().length < 2) {
            $('#catalogGrid').empty();
            $('#catalogStatus').text('');
            return;
        }
        $('#catalogStatus').text('Searching...');
        $.ajax({
            url: '/api/catalog/search', type: 'POST', contentType: 'application/json',
            data: JSON.stringify({query: query}),
            success: function (result) {
                if (!result['success']) {
                    const error = (result['errors'] || [{}])[0]['error'] || 'Search failed.';
                    $('#catalogGrid').empty();
                    $('#catalogStatus').html(`<span class="text-warning">${escapeHtml(error)}</span>`);
                    return;
                }
                renderCatalog(result['results'] || [], result['truncated']);
            },
            error: function () {
                $('#catalogGrid').empty();
                $('#catalogStatus').html('<span class="text-danger">Search request failed.</span>');
            }
        });
    }

    function renderCatalog(results, truncated) {
        const grid = $('#catalogGrid').empty();
        if (!results.length) {
            $('#catalogStatus').text('No game found.');
            return;
        }
        $('#catalogStatus').text(truncated
            ? `Showing the first ${results.length} matches, refine your search.`
            : `${results.length} ${results.length === 1 ? 'result' : 'results'}`);

        results.forEach(function (game) {
            const card = $('<div class="card text-bg-dark game-card"></div>').css('cursor', 'pointer');
            card.append($('<img class="card-img" alt="">').attr('src', game.bannerUrl || game.iconUrl || ''));

            const overlay = $('<div class="card-img-overlay game-info"></div>');
            overlay.append($('<h5 class="card-title game-title"></h5>').text(game.name));

            const tags = $('<div class="tags-container"></div>');
            tags.append($('<span class="badge rounded-pill game-tag"></span>')
                .addClass(game.owned ? 'text-bg-success' : 'text-bg-secondary')
                .text(game.owned ? 'Owned' : 'Search'));
            overlay.append(tags);

            card.append(overlay);
            // Owned games stay clickable: the user may want a different release.
            card.on('click', () => openReleaseSearch({title_id: game.title_id, catalog: true}));
            grid.append(card);
        });
    }
</script>

{% include 'release_modal.html' %}
{% endblock %}
```

- [ ] **Step 2: Add the nav entry**

In `app/templates/nav.html`, inside the `{% if current_user.is_admin or admin_account_created == false %}` block, immediately after the Downloads `<li>`:

```html
                <li class="nav-item">
                    <a class="nav-link{% if title == 'Discover' %} active" aria-current="page"{% else %}"{% endif %}" href="/discover">Discover</a>
                </li>
```

- [ ] **Step 3: Verify the templates parse**

Run:

```bash
/Users/jalbert/claude-code/ownfoil/.venv/bin/python -c "
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('app/templates'))
for t in ('index.html', 'discover.html', 'release_modal.html', 'nav.html'):
    env.parse(open('app/templates/' + t).read())
print('templates parse')
"
/Users/jalbert/claude-code/ownfoil/.venv/bin/python app/test_titles.py
/Users/jalbert/claude-code/ownfoil/.venv/bin/python app/test_downloader.py
/Users/jalbert/claude-code/ownfoil/.venv/bin/python app/test_organizer.py
```

Expected: `templates parse`, then every test line prefixed `ok `.

- [ ] **Step 4: Commit**

```bash
git add app/templates/discover.html app/templates/nav.html
git commit -m "Add the Discover page

A card grid over titledb reusing the library's .library-grid and card styles,
so no CSS is added. Clicking a game opens the same release modal the library
uses.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: Record the feature

**Files:**
- Modify: `FORK.md`

- [ ] **Step 1: Document it**

In `FORK.md`, under the `## On the `downloader` branch (not merged): auto-downloader` section, add to the Decisions list:

```markdown
- **Discover searches titledb, not the library.** A dedicated page finds any base game by name and
  hands it to the same release modal. It scans the titledb already resident in memory rather than
  building an index: `resolve_target` is decorated `@with_titledb`, so every manual search already
  pays that load. Marked with a `ponytail:` comment naming the exit — upstream 2.4.0 moves titledb
  into SQL, which turns the scan into a `LIKE` and deletes the question.
- **`rank_releases()` is only tuned for updates**, so the ordering of base-game releases is rough.
  Tolerable because Discover never auto-grabs: the modal lists everything with reasons and the user
  picks.
```

- [ ] **Step 2: Add the ponytail comment**

In `app/titles.py`, immediately above `def search_base_games`, add:

```python
# ponytail: linear scan of the whole titledb per search. The load it needs is already
# paid by every manual downloader search, so this costs nothing extra today. If it ever
# drags, build a slim (id, name, iconUrl) index when titledb is downloaded — or wait for
# upstream 2.4.0, which puts titledb in SQL and makes this a LIKE query.
```

- [ ] **Step 3: Run the full suite and commit**

```bash
/Users/jalbert/claude-code/ownfoil/.venv/bin/python app/test_titles.py
/Users/jalbert/claude-code/ownfoil/.venv/bin/python app/test_downloader.py
/Users/jalbert/claude-code/ownfoil/.venv/bin/python app/test_organizer.py
git add FORK.md app/titles.py
git commit -m "Record the Discover design decisions and its known ceiling

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Manual verification

The app cannot run in this sandbox — titledb fails to download over SSL, and `/` returns 500 without
it. These checks belong to the user, on their instance, after the image is rebuilt:

1. Discover appears in the nav for an admin, and not for a shop-only user.
2. Typing `pokemon` (no accent) finds `Pokémon` titles — this is the accent-folding check.
3. A game already in the library shows the `Owned` badge.
4. Clicking a card opens the release modal and lists Prowlarr releases.
5. Grabbing from Discover adds a line to the Downloads page.
6. **Regression:** the library's own 🔍 badge still opens the modal and still searches for the
   missing update, not the base game.
