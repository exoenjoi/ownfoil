# Release list controls

Drop dead torrents from the release modal, let the user sort it, and show each release's date.

## Why

The modal lists every release Prowlarr returns, ranked, with the ones the automatic job would refuse
greyed out and annotated. That is deliberate — a human can override a rejection the job never would.
But a release with zero seeders is not an override opportunity, it is undownloadable, so it is pure
noise. And with the noise gone, the remaining list is worth sorting and worth dating: which release
is newest, or biggest, is information the score alone does not carry.

## Decisions taken

- **Only zero-seeder releases are hidden.** Everything else the job would refuse stays visible and
  greyed with its reason. "Two seeders when your minimum is three" is a legitimate override; "no
  seeders at all" is not.
- **The default order stays the score.** The ranking is the feature; sorting is an explicit act.
- **The date is shown raw** (`2019-04-23`), not as a relative age. A date is readable on sight and
  costs no code. Relative age can come later if it turns out to be missed.

## Components

### Server: `rank_releases()` in `app/downloader.py`

Skip any release with zero seeders before annotating. The drop is **unconditional** — independent of
the `min_seeders` filter, because a zero-seeder release is dead even when the user sets their minimum
to zero.

This is the one place both callers route through: the automatic job (`best_release`) and the modal
(`search_releases`). The job never took a rejected release anyway, so its behaviour does not change —
only the list gets shorter. Log the number dropped so an empty result is diagnosable.

`search_releases()` needs no change: its `if any(not r['rejected'] ...)` retry logic is unaffected,
since dropped releases were already rejected.

### Client: `renderReleaseSearch()` in `app/templates/release_modal.html`

- A `Date` column showing `publish_date.slice(0, 10)`. The field already travels from
  `prowlarr._release()` to the browser; it is simply not displayed today.
- Clickable headers on Release, Size, S/L and Date. First click sorts, second reverses. A `releaseSort`
  module variable holds `{key, dir}`; the active header shows a caret.
- **The sort mutates `releaseSearchResults` in place.** `grabRelease(index, button)` looks the release
  up by its index in that array, so sorting a copy would make the Grab button download the wrong
  release. This is the one real trap in this change.
- The empty-list message becomes "No usable release found." — with dead torrents dropped server-side,
  "Prowlarr returned no result" would be false when it returned only dead ones.

## Testing

- `app/test_downloader.py` — `rank_releases` drops a zero-seeder release, keeps a one-seeder release
  that is merely below `min_seeders`, and still drops it when `min_seeders` is zero.
- The sorting and the column are JavaScript, and this project has no JS test framework. Verified the
  way the Discover page was: build the standalone preview from the real template, then assert on the
  DOM — sort order, reversal, and above all that Grab still targets the right release after a sort.

## Out of scope

Relative ages, sorting on the indexer column, persisting the sort between searches, and any new
setting.
