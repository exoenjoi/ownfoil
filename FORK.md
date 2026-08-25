# Fork log

What this fork changes, and *why* it was done that way. The reasoning is the part that is
expensive to rediscover — the code itself is in the diff.

Fork of [a1ex4/ownfoil](https://github.com/a1ex4/ownfoil), forked at `7ca28d5` (upstream's last
commit at the time, 2026-03-25). Synced with upstream **2.4.0** on 2026-08-25 — read the sync note
under Operations before fetching, upstream rewrote its history and `7ca28d5` no longer exists there.

## The setup this fork is built for

Games arrive by torrent and must keep seeding, so **the files can never be renamed or moved**.
Upstream's organizer does exactly that. Everything below follows from that constraint.

```
/games/torrents    ← qBittorrent downloads here, seeds forever, untouched
/games/organized   ← hardlink tree with clean names, this is "the library"
```
Both must be inside a **single** mount: hardlinks cannot cross filesystems (`EXDEV`).

---

## On `master`: hardlink organizer

`Settings > Library > Organizer > Destination folder`. Empty = upstream behaviour (rename in
place). Set = hardlink mode.

**Key decision: the destination folder is not an Ownfoil library.** It is never scanned nor
watched. If it were, the scan would pick every link up as a new file and each game would appear
twice in the shop and be identified (decrypted) twice. The DB keeps pointing at the source file;
only the *published name* (`Files.filename`) becomes the link's name, which is what the shop
exposes and what Tinfoil parses. Downloads serve the same inode either way.

Consequences, all deliberate:
- `Remove empty folders` is skipped in this mode — it would prune the torrent directories.
- `Delete older updates` only removes the link, never the source file.
- **Stale links are not cleaned up.** Changing a template or deleting a source leaves the old link
  behind. Chosen explicitly over an automatic sweep of the destination folder. Marked with a
  `ponytail:` comment on `link_organized_file()` in `library.py`.
- Fixed a pre-existing bug on the way: Sphaira served files from `Files.folder`, which becomes
  library-relative once a file is organized. It now serves from `Files.filepath`.

## Also on `master`: merged NSPs were only half identified

An upstream bug, found from a library reporting `Base missing` on a game whose base was sitting
right there inside the NSP. `get_cnmts()` walked every NCA of an **Xci** but called
`Nsp.cnmt()` for an **Nsp** — and that helper returns the *first* `.cnmt.nca` and stops
(`nsz/Fs/Nsp.py:220`). A merged base+update NSP therefore registered one content only: the base
stayed `owned=False`, `nb_content` stayed 1, so `multicontent` stayed false and the organizer named
the file with the `update` template. That name was the trap: the base and update templates used to be
identical, so the file read as a base game and only one hex digit of the app id (`…2000` vs `…2800`)
said otherwise. Same bug hit an `Incl.All.Dlcs` NSP: base owned, every DLC not.

Fixed by walking the whole container, mirroring the Xci branch — in `containers/cnmt.py` since the
2.4.0 sync, where upstream still has the original bug. Covered by `app/test_titles.py`.

**The `update` template now carries `[UPD]`**, so an update is never mistaken for a base game again.
The marker is safe for the no-keys fallback — neither `\[([0-9A-Fa-f]{16})\]` nor `\[v(\d+)\]` can
match it — and a test pins that against the real default. Two consequences: existing installs keep
the template already written in their `settings.yaml` and must change it by hand, and changing it at
all makes the organizer re-place every update file, which in hardlink mode leaves the old links
behind (see the stale-links note above).

**Re-identification is not automatic.** `get_files_to_identify()` only returns rows with
`identified=False`, so files identified before the fix keep their half-truth. Remove and re-add the
library path in the settings to force a full pass — `delete_files_by_library()` drops database rows
only, it never touches the filesystem.

## Also on `master`: manual downloader

Built on the `downloader` branch, merged into `master` on 2026-08-25 once every part of it had
been exercised against real trackers.

Searches **Prowlarr** for the content missing from the library and hands the release *you pick* to
Prowlarr's own download client. Inspired by
[Athos97/ownfoil](https://github.com/Athos97/ownfoil) (Jackett + qBittorrent, ~1300 lines),
rewritten in ~700 for three reasons:

1. **Prowlarr grabs by itself.** `POST /api/v1/search` with `{guid, indexerId}` and it hands the
   release to *its own* download client. All the code that talks to qBittorrent to add a torrent
   disappears. qBittorrent is only read here, only to show progress, and is optional.
2. **Missing content is already in the database.** `add_missing_apps_to_db()` materializes every
   update and DLC known to titledb as an `Apps` row with `owned=False`. No need to recompute it.
3. **Searching by app id barely works.** A title id almost never appears in a release name. Search
   by game name, and use the id/version for *scoring* instead.

Decisions:
- **Nothing is ever grabbed without a click.** There was a scheduled job that grabbed the latest
  missing update of every owned game, capped by `max_per_run`; it worked, and it was removed on
  2026-08-25 because the user does not want the fork to download on its own. Deleted with it: the
  `download_interval` scheduler entry, the `max_per_run` filter, the `Run now` button, the
  `/api/downloader/run` route, and the `enabled` flag — which by then gated the job and nothing
  else, the manual search never having been conditioned on it. `git log` has it if it is ever
  wanted back.
- **The 🔍 badge is per title group, not per app.** Since `master` groups the library by title, the
  badge searches the base game's missing update, or the base game itself if it is missing. Missing
  DLCs are only counted by the DLC badge — no per-DLC search from a grouped card.
- **Seeders are a tiebreaker, never a score term.** A popular release of the wrong version is still
  the wrong version. A caught regression, see `test_exact_version_beats_patch_level`.
- **An update release with no version marker in its name is refused** — it is usually the base game.
  The manual search modal still lists refused releases with the reason, so a human can override.
- **History lives in `config/downloads.json`**, not in a table. See the Alembic note below.
- `completed` means the library identified the file, not that the torrent finished.
- **Discover searches titledb, not the library.** A dedicated page finds any base game by name and
  hands it to the same release modal, so a game you own nothing of is reachable. It used to scan a
  titledb loaded whole into memory; since 2.4.0 titledb *is* SQLite, so `search_base_games()` (now in
  `downloader.py`) selects six columns per base game and matches in Python. **Not a `LIKE`**, which
  was the guess written here before: SQL cannot fold accents or anchor at word starts without a UDF,
  and folding defeats the index anyway. GraphQL's own `search` argument has the same limit — it is
  `LIKE %q%`, so `zelda breath of the wild` finds nothing through it. The `@with_titledb` decorator
  is gone with the load it guarded.
- **`resolve_target(catalog=True)` skips the `Apps` table entirely.** The flag is explicit rather
  than inferred from a missing row, so the library's own 🔍 keeps its exact behaviour: without it
  nothing on that path changes.
- **`rank_releases()` is only tuned for updates** — it rejects an update release with no version
  marker because that is usually the base game. A base-game target passes unranked by that rule, so
  its ordering is rough, and a patch-only release (`…_Update_v1.9.0_NSW-…`, ~1 GB) can sit near the
  top of a base-game search. Tolerable because every grab is a human choice: the modal lists each
  release with its rejection reason and the size, and the user picks.
- The release modal lives in `templates/release_modal.html`, included by both the library and
  Discover. `missingContentSearchButton()` stayed in `index.html`, and since 2.4.0 it takes one of
  upstream's card models rather than a fork-built group — see the 2.4.0 section.
- **A Discover card carries `title id · release date · publisher`**, one line, id first so the
  ellipsis eats the publisher rather than the id. Two titledb entries can share a name (the game
  and its KIOSK demo), and the id is what tells them apart before opening the release list. The
  fields come off the record the catalog scan already walked, so the search costs nothing more.
- **Discover's grid is pinned to 300px tiles** (`#catalogGrid` in `style.css`). It is the only grid
  with no size slider, and a 220px tile leaves a 221x124 card whose overlay covers 109px of it — the
  metadata line overflowed and the cover art was gone. It used to match the library slider's second
  notch exactly; 2.4.0 rebuilt the library grid on Bootstrap columns instead of the `--tile` variable,
  so the two are no longer the same mechanism and no longer line up. Discover is self-contained and
  still renders correctly — `.library-grid` and `--tile` in `style.css` are now fork-only.
- **A release with 0 seeder is dropped in `rank_releases()`, whatever `min_seeders` says.** It is not
  an override the user might want, it is undownloadable. Releases merely *below* `min_seeders` stay,
  greyed out with the reason — that distinction is the point.
- **A missing file extension only sinks a release that cannot prove it is a Switch dump.** An app id,
  a title id or the `NSW` scene tag is proof enough — `…[01007EF00011E000][v1048576] 1G+1U+2D` and
  `…_v1.9.0_NSW-SUXXORS` are real releases that used to be refused for "no Switch file extension".
  A soundtrack, a PDF or a WiiU `.wua` carries none of the three and is still refused. An unknown
  format scores 0 on the extension preference, so a named `.nsp` still outranks it.
- **`\b` is the wrong boundary for release names** — `_` is a word character, so `\bv196608\b` never
  matches `…_v196608_NSW-…`, and `\bxci\b` never matches `SuperXCi`. `TOKEN_START` / `TOKEN_END` in
  `downloader.py` say what is meant instead: a token edge is anything that is not a letter or digit.
- **The catalog search matches the whole query, or every typed word at the start of a word.** Plain
  substring alone means `zelda breath of the wild` finds nothing, because titledb calls it
  `The Legend of Zelda: Breath of the Wild`. Word starts only, or a stray letter matches half the
  catalog.
- **The modal's column sort mutates `releaseSearchResults` in place.** `grabRelease(index)` looks its
  release up by index in that array, so sorting a copy would grab the wrong release. Verified in a
  browser (stubbed ajax, clicked a row after sorting, compared the grabbed title to the row's).

---

## Things learned about this codebase

Worth re-reading before touching anything here.

- **No Alembic migrations in this fork, on purpose.** Any revision we add chains from upstream's
  latest — and so will upstream's next one, which gives two Alembic *heads* and a hand-written merge
  revision at every sync. Both features avoided this: the hardlink mode by reusing `Files.filename`,
  the downloader by using a JSON file. The 2.4.0 sync proved the bet: upstream added nine revisions
  in one linear chain and there was nothing to arbitrate.
- **A new setting must be added to `DEFAULT_SETTINGS`** in `constants.py`, or `remove_obsolete_keys()`
  silently deletes it from `settings.yaml` on the next load.
- **The settings JS sends whole sub-dicts** and the server does `.update()`, so a key missing from
  the JS payload is wiped on every save.
- **titledb is a SQLite database** (`config/titles.db`), built from the downloaded JSON by
  `titledb/store.py` and queried per title id. `get_game_info()` is a cheap indexed lookup, safe on a
  request path — the reason the shop could not compute organized names on the fly is gone.
  `titles.py` keeps `get_game_info` and friends as thin re-exports of `titledb.store`.
- **Upstream has a real test suite**: `python -m pytest tests` — 1390 tests, no network, ~90s. It
  covers the shop clients against replayed traffic, the organizer paths, the task queue and the
  GraphQL schema. Run it before and after touching anything: it is a far better check than the
  fork's three scripts, which only cover what upstream has no test for.

---

## Upstream 2.4.0: what it actually cost

Merged 2026-08-25. The 2026-08-06 survey of this release, made while it was still on `develop`, was
right about nearly everything; what follows keeps only what is still worth knowing, and is explicit
about the two things the survey got wrong.

**The survey was wrong about `index.html`.** It said `develop` did not touch it, so the UI would
merge clean. 2.4.0 rewrote it: the library is now GraphQL-driven and paginated, and `library.json`
is gone. That was the largest single re-port of the merge — and it *deleted* fork code rather than
moving it. `apps(groupByAppId: true)` groups by title server side, sorted and filtered, so the
fork's browser-side `groupTitles()` went with the cache file it was built on. Upstream's
`cardModel()` already carries `ownership.haveBase` and `upToDate`, which is everything the 🔍 badge
needs, so `missingContentSearchButton()` is now a dozen lines reading that model.

**The survey was wrong about a `LIKE`** — see the Discover note above.

**It was right about the organizer.** `process_library_organization()` is gone; organizing is
`organize_file()` in `library.py`, driven per file by the task queue in `tasks.py`. The hardlink
branch was re-ported, not merged: git had no conflict to offer, the function it patched simply no
longer existed.

- `organized_relpath()` factors out the template computation so `unlink_organized_file()` can reuse
  it. It takes the root it is relative to, because the Windows path-length budget is measured from
  the organizer destination in hardlink mode, not from the library.
- **`Files.organized` means "has been placed", not "has been moved".** That was the open question
  the survey left. In hardlink mode it is set once the link exists; it is what stops
  `_needs_organize()` running the organizer again on every pass. `reset_files_organized()` re-links
  everything, which is the intended way to re-place after a template change.
- `library_maintenance` no longer prunes empty folders in hardlink mode, and
  `remove_outdated_update_files()` unlinks instead of deleting the source.

**It was right about Alembic.** The no-migration bet paid exactly as predicted: upstream's nine new
revisions form one linear chain under `78c33e9bffce`, we added none, so there was no second head and
nothing to merge. Keep it that way.

**Compression stays off, forever.** It rewrites files in place and the pipeline chains
organize → compress. Our files must keep seeding — see the constraint at the top of this file. It is
off by default upstream too, so the real risk is enabling it out of curiosity later, having
forgotten why not. **Verification, on the other hand, is on**: it only reads and hashes, which is
safe for seeding files, and it sorts the library into `valid` / `repack` / `modified` / `corrupt`.

**What the merge deleted from the fork**, all of it obsolete rather than dropped:

- `load_titledb()` / `unload_titledb()` / the `with_titledb` decorator and the defensive
  `try/finally` around their leaking counter — titledb is a database now.
- `groupTitles()` and the whole client-side grouping.
- `place_file()`, replaced by `link_organized_file()`.

**What moved, to stop being conflict surface.** Upstream removed `safe_write_json()` from `utils.py`
along with `library.json`, and `is_app_owned()` was ours in `db.py`. Both now live in the fork's own
files (`downloads_store.py`, `downloader.py`), where the next sync cannot collide with them. Same
reasoning for anything else small and fork-only: keep it out of files upstream owns.

**Things that changed under us, worth knowing:**

- `get_cnmts()` moved to `containers/cnmt.py` and now **raises** instead of returning `[]`. Upstream
  did *not* fix the merged-NSP bug, so our walk of the whole container was re-applied there.
- Upstream fixed Sphaira twice, both for other causes. Our `folder` → `filepath` fix is still needed
  and still distinct: upstream still serves from `Files.folder`.
- `scheduler.scan_interval` was renamed `titledb_update_interval`.
- Titledb now comes from a GitHub release asset (`TITLEDB_RELEASE_URL`), which is what the fork
  already wanted — our `TITLEDB_ARTEFACTS_URL` override is gone and that divergence with it.
- The Flask development server is finally gone: Gunicorn plus a worker pool, started by `app/run.py`.
- Downloads moved to `/admin/downloads`, in upstream's new admin sidebar next to Tasks and Stats.
  Discover stayed a top-level page.

## Operations

- Image: `ghcr.io/exoenjoi/ownfoil:latest`, public, amd64 + arm64. Rebuilt by GitHub Actions on
  every push to `master` (`.github/workflows/docker.yml`, uses the built-in token, no secret).
- **`docker compose up -d` alone does not fetch a new `latest`** — it reuses the locally cached one,
  which is how a merged feature can appear missing on the instance. Always `docker compose pull &&
  docker compose up -d`. To check what the registry holds:
  `gh api /user/packages/container/ownfoil/versions --jq '.[] | select(.metadata.container.tags[]? == "latest") | .name'`
  against `docker image inspect ghcr.io/exoenjoi/ownfoil:latest --format '{{index .RepoDigests 0}}'`.
- **A branch has no `latest`.** The workflow only auto-builds `master`, so a testable image of a
  branch comes from pushing a tag: `git tag -a 2.4.0-<branch>.N -m '…' && git push origin
  2.4.0-<branch>.N` builds `ghcr.io/exoenjoi/ownfoil:2.4.0-<branch>.N` (the workflow's tag filter
  is `*.*.*`). Bump N, never move an existing tag — a running instance pins one. `2.4.0-downloader.1`
  through `.7` were the downloader's.
- Dropped two upstream-only workflows: the stale-issue bot, and the titledb build — the app pulls
  titledb from upstream's release asset (`TITLEDB_RELEASE_URL` in `constants.py`, upstream's own
  default since 2.4.0).
- **Sync with upstream: `git fetch upstream && git merge upstream/master`.** This works normally
  again. Watch `upstream/develop` for what is coming, but merge only `master`: upstream develops on
  `develop` and only advances `master` at a release, so `master` looks frozen for months and then
  moves by a whole release at once. The quiet is an illusion, not a dead project.
- **Upstream rewrote its entire history before 2.4.0** (`git fetch` logged a `forced-update`, and
  the root commit changed). For that one merge `git merge-base` returned nothing and git refused to
  merge unrelated histories. The fork point still existed on both sides under different hashes —
  identical tree objects proved it, our `7ca28d5` == upstream `3a1c2df` — so the merge was made
  possible by a temporary graft:

  ```sh
  git replace 7ca28d5 3a1c2df    # only needed for the 2.4.0 merge
  git merge upstream/master
  git replace -d 7ca28d5
  ```

  **This is history, not a procedure.** The 2.4.0 merge commit records `upstream/master` as a real
  parent, so there is a common ancestor again and no graft is needed any more. If upstream ever
  force-pushes another rewrite, the recipe is: find the commit on each side with the same tree
  (`git rev-parse <c>^{tree}`), graft, merge, drop the graft.
- Tests. Upstream's suite first — `python -m pytest tests`, 1390 tests, ~90s, no network. Then the
  fork's three, which cover only what upstream does not: `python app/test_organizer.py`,
  `python app/test_titles.py`, `python app/test_downloader.py`.
- Running it locally: `cd app && python run.py` (Gunicorn + workers, port 8465). `OWNFOIL_CONFIG_DIR`
  redirects the config away from the real one; the titledb download lands in `app/data/` regardless,
  which is 168 MB and gitignored.
