# Fork log

What this fork changes, and *why* it was done that way. The reasoning is the part that is
expensive to rediscover — the code itself is in the diff.

Fork of [a1ex4/ownfoil](https://github.com/a1ex4/ownfoil), forked at `7ca28d5` (upstream's last
commit at the time, 2026-03-25).

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
  `ponytail:` comment in `process_library_organization()`.
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

Fixed by walking the whole container, mirroring the Xci branch. Covered by `app/test_titles.py`.

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

## On the `downloader` branch (not merged): auto-downloader

Grabs the updates missing from the library through **Prowlarr**. Inspired by
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
- **Auto grabs updates only**, latest missing one per game, and only for games whose base game is
  owned. Capped by `max_per_run` — on a large library the first run would otherwise queue hundreds
  of torrents. Anything else is grabbed by hand from the 🔍 badge in the library.
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
  hands it to the same release modal, so a game you own nothing of is reachable. It scans the
  titledb already resident in memory rather than building an index: `resolve_target` is decorated
  `@with_titledb`, so every manual search already pays that load and the scan costs nothing extra.
  Marked with a `ponytail:` comment naming the exit — upstream 2.4.0 moves titledb into SQL, which
  turns the scan into a `LIKE` and deletes the question.
- **`resolve_target(catalog=True)` skips the `Apps` table entirely.** The flag is explicit rather
  than inferred from a missing row, so the library's own 🔍 keeps its exact behaviour: without it
  nothing on that path changes.
- **`rank_releases()` is only tuned for updates** — it rejects an update release with no version
  marker because that is usually the base game. A base-game target passes unranked by that rule, so
  Discover's ordering is rough. Tolerable because Discover never auto-grabs: the modal lists every
  release with its rejection reason and the user picks.
- The release modal lives in `templates/release_modal.html`, included by both the library and
  Discover. `missingContentSearchButton()` stayed in `index.html` — it takes a library group object.
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

- **No Alembic migrations in this fork, on purpose.** Upstream's chain has a single revision
  (`78c33e9bffce`). Any revision we add chains from it — and so will upstream's next one, which
  gives two Alembic *heads* and a hand-written merge revision at every sync. Both features avoided
  this: the hardlink mode by reusing `Files.filename`, the downloader by using a JSON file.
- **A new setting must be added to `DEFAULT_SETTINGS`** in `constants.py`, or `remove_obsolete_keys()`
  silently deletes it from `settings.yaml` on the next load.
- **The settings JS sends whole sub-dicts** and the server does `.update()`, so a key missing from
  the JS payload is wiped on every save.
- **titledb is loaded on demand and unloaded 30s later.** `load_titledb()` increments a counter but
  `unload_titledb()` never decrements it — the caller must. Both upstream call sites do it without
  `try/finally` and leak the counter on any exception; ours uses `try/finally`, with the load
  *inside* the try since the counter is incremented before the files are opened.
- **`get_game_info()` is a full linear scan of titledb**, and returns `None` when it is unloaded.
  Never call it on a request path — that is why the shop cannot compute organized names on the fly.
- Upstream still runs the **Flask development server** in production. Unfixed, noted.

---

## Upstream: what lands at 2.4.0

Surveyed 2026-08-06. **Upstream develops on `develop`, not `master`.** `upstream/master` has not
moved since `7ca28d5` (2026-03-25, our fork point) — it only advances at releases. `develop` is
122 commits ahead, `+5768/-1401` over 51 files. So `git merge upstream/master` returns nothing for
months, then a whole release at once. The quiet is an illusion, not a dead project.

**Do not track `develop`.** The foundations it reworks are the exact ones both features hook into,
and they are still moving. Porting onto them now means porting twice. Wait for 2.4.0 on `master`.

**Cost, in order of attack. Start with the organizer** — it is what decides whether the merge is
feasible at all; the rest is bookkeeping.

| Area | Effort |
|---|---|
| `index.html`, downloader-only files, Alembic | **none.** `develop` does not touch `index.html` at all, so the UI rework merges clean. And the no-migration bet pays: we added zero revisions, so upstream's four new ones chain under `78c33e9bffce` with no second head |
| `add_missing_apps_to_db()` (moved to `library.py`), deleted workflows | minutes — imports, modify/delete conflicts |
| `app.py`, `settings.py` (191 lines changed), `settings.html` (240) | tedious, line-by-line |
| titledb calls in the downloader | rewrite against the new API |
| **hardlink organizer** | **full re-port**, see below |

**The organizer was rewritten.** `process_library_organization()` no longer exists. Organizing lives
in `organize_file()` (`library.py`), driven by `organize_library_task` / `organize_file_task` in the
new task queue, and every row now carries `Files.organized`. Our hardlink patch is grafted onto a
function that is gone — git will not hand us a conflict to arbitrate, the block simply vanished.
Open question to settle then: what `organized` means when the source file never moves.

**Keep NSZ compression off.** The headline feature of 2.4.0 (9 commits: compress, verify
bit-identical, live progress, settings UI) rewrites files in place, and the pipeline chains
organize → compress (`tasks.py`, *"organize_file re-triggers compression once placed"*). Our files
must keep seeding — see the constraint at the top of this file. It is opt-in and off by default, so
the real risk is enabling it out of curiosity later, having forgotten why not.

**What we gain — more than bug fixes.** This release *simplifies* the fork:

- **titledb moved into SQL (#318).** `get_game_info()` became a shim over a SQL lookup, and
  `load_titledb()` / `unload_titledb()` are gone. Two notes above become obsolete, our defensive
  `try/finally` around the leaking counter can be deleted, and the shop *can* compute organized
  names on the fly after this.
- **Task queue + Gunicorn.** Parallel scans, configurable workers, per-group concurrency caps,
  stoppable tasks — and the Flask development server finally replaced.
- **Six organizer fixes** in our exact area: duplicate renaming, duplicate handling, a regression,
  filenames, multicontent removal, leftovers when deleting a library.
- Upstream also fixed Sphaira twice, but for other causes (reverse-proxy client detection, and an
  organizer bug). Our `folder` → `filepath` fix looks distinct and still needed — verify, don't assume.

Irrelevant to us, all Docker-shaped concerns: pip/uv packaging, PyPI publish, Windows path limits,
opening a browser at startup, LAN IP on the setup page.

## Operations

- Image: `ghcr.io/exoenjoi/ownfoil:latest`, public, amd64 + arm64. Rebuilt by GitHub Actions on
  every push to `master` (`.github/workflows/docker.yml`, uses the built-in token, no secret).
- **`downloader` has no `latest`.** The workflow only auto-builds `master`, so a testable image of
  the branch comes from pushing a tag: `git tag -a 2.4.0-downloader.N -m '…' && git push origin
  2.4.0-downloader.N` builds `ghcr.io/exoenjoi/ownfoil:2.4.0-downloader.N` (the workflow's tag
  filter is `*.*.*`). Bump N, never move an existing tag — the running instance pins one.
- Dropped two upstream-only workflows: the stale-issue bot, and the titledb build — the app pulls
  titledb from upstream's repo (`TITLEDB_ARTEFACTS_URL` in `constants.py`).
- Sync with upstream: `git fetch upstream && git merge upstream/master`. Watch `upstream/develop`
  for what is coming, but merge only `master` — see the 2.4.0 section above for why.
- Merge `master` into `downloader` after every UI session. Both touch `app/templates/index.html`,
  so the conflicts are structural: ten small ones beat one unreadable one.
- Tests, no framework, no network: `python app/test_organizer.py`, `python app/test_titles.py`,
  `python app/test_downloader.py` (the last one on the `downloader` branch).
