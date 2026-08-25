# <img src="https://github.com/user-attachments/assets/3cfdf010-50c3-41ae-aa86-e31b22466686" height="28"> Ownfoil
[![Static Badge](https://img.shields.io/badge/github-repo-blue?logo=github)](https://github.com/a1ex4/ownfoil)
[![Latest Release](https://img.shields.io/docker/v/a1ex4/ownfoil?sort=semver)](https://github.com/a1ex4/ownfoil/releases/latest)
[![Docker Image Size (latest semver)](https://img.shields.io/docker/image-size/a1ex4/ownfoil?sort=date&arch=amd64)](https://hub.docker.com/r/a1ex4/ownfoil/tags)  
[![Docker Pulls](https://img.shields.io/docker/pulls/a1ex4/ownfoil?)](https://hub.docker.com/r/a1ex4/ownfoil)
[![Unraid downloads](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fca.unraid.net%2Fapi%2Fsearch%3Fquery%3Downfoil%26type%3Ddocker&query=%24.hits%5B0%5D.chartData.totalDownloadsChart.data%5B6%5D&label=unraid%20downloads&color=F15A2C)](https://ca.unraid.net/apps/ownfoil-19wo90o0t5ul8s)  
![Image archs](https://img.shields.io/badge/platforms-amd64%20%7C%20%20arm64%2Fv8%20%7C%20arm%2Fv7%20%7C%20arm%2Fv6-8A2BE2)  
[![Tinfoil Version](https://img.shields.io/badge/Tinfoil-v20.0-da1c5c)](https://tinfoil.io/Download)
[![Sphaira Version](https://img.shields.io/badge/Sphaira-v1.0.6-%233cd57a)](https://github.com/NaGaa95/sphaira)
[![CyberFoil Version](https://img.shields.io/badge/CyberFoil-v1.4.5-firebrick)](https://github.com/luketanti/CyberFoil)

> [!IMPORTANT]
> ## This is a fork [![Made with Claude Code](https://img.shields.io/badge/made%20with-Claude%20Code-D97757?logo=anthropic&logoColor=white)](https://claude.com/claude-code)
>
> Fork of [a1ex4/ownfoil](https://github.com/a1ex4/ownfoil) adding a **hardlink mode to the
> organizer**, for libraries whose files cannot be renamed - typically torrents that are still
> being seeded.
>
> Upstream, the organizer renames and moves your files in place. Here, setting an
> `Organizer > Destination folder` in the settings makes Ownfoil build the templated tree with
> **hardlinks** in that folder instead: the source files are never renamed, never moved, never
> deleted, and the destination folder becomes your clean, organized library. Hardlinks cost no
> extra disk space, both names point at the same data.
>
> The destination folder is deliberately *not* an Ownfoil library: it is never scanned nor
> watched, so each game stays a single entry in the shop and is identified only once. The shop
> publishes the organized names while downloads keep serving the same file.
>
> It also adds a [downloader](#downloader): Ownfoil already knows which updates and DLCs your
> library is missing, so it searches them through Prowlarr and hands the release *you pick* to
> Prowlarr's own download client. Nothing is ever grabbed without your click. Combined with the
> hardlink mode, the whole chain closes on itself: grab, seed, hardlink into a clean library.
>
> See [Organizer destination (hardlink mode)](#organizer-destination-hardlink-mode) for setup, and
> [`ghcr.io/exoenjoi/ownfoil`](https://github.com/exoenjoi/ownfoil/pkgs/container/ownfoil) for the
> image built from this fork.
>
> Everything else is upstream's work - the original README follows.

Ownfoil is a Nintendo Switch library manager, that will also turn your library into a fully customizable and self-hosted Shop, supporting multiple clients. The goal of this project is to manage your library, identify any missing content (DLCs or updates) and provide a user friendly way to browse and install your content. Some of the features include:
- multi user authentication
- web interface for configuration and browsing the library
- content identification using content decryption or filename
- automatic library organization, verification and compression
- console keys management
- multiple clients support
- shop customization

# Installation

Head over to [Install.md](./Install.md) for the full instructions:

- [Using Docker](./Install.md#using-docker)
- [Using uv (Windows users do this)](./Install.md#using-uv)
- [Using Unraid](./Install.md#using-unraid)
- [Using Proxmox LXC](./Install.md#using-proxmox-lxc)
- [Using the Helm chart](./Install.md#using-the-helm-chart)

> [!CAUTION]
> There is __no website associated with this project__, only this GitHub repo.  
> Ownfoil is __not released as an application or an executable file__ - DO NOT download or execute anything related to Ownfoil outside of this repository and its instructions.

# Usage

Configuring your shop, your clients and every setting available is documented in [Usage.md](./Usage.md). Start with [First steps](./Usage.md#first-steps), or jump straight to the [settings reference](./Usage.md#settings-reference).

# Credits

Thanks to the following projects and their maintainers for making Ownfoil possible:
- [@blawar](https://github.com/blawar) for Tinfoil, Fs, the nsz format, TitleDB
- [@nicoboss](https://github.com/nicoboss) for [nsz](https://github.com/nicoboss/nsz)
- [@seiya-dev](https://github.com/seiya-dev) for [NSTools](https://github.com/seiya-dev/NSTools)

# This fork

Two features upstream does not have. Why they exist and how they are built is in [FORK.md](./FORK.md).

## Organizer destination (hardlink mode)

By default the organizer renames and moves the files inside their library. If your files must keep
their name on disk - typically torrents that are still being seeded - set a `Destination folder` in
the `Organizer` section: Ownfoil then creates **hardlinks** with the templated names in that folder
and never touches the source files. The destination folder becomes your organized library, and the
shop publishes the games under their organized names.

Requirements:
- the destination folder must be **outside** of every configured library, otherwise the links would
  be scanned and every game would show up twice;
- it must be on the **same filesystem** as the sources, hardlinks cannot cross filesystems. In
  Docker, mount their common parent as a single volume, e.g. `-v /mnt/nas/switch:/games` with
  `/games/torrents` (library) and `/games/organized` (destination). Two separate `-v` mounts, even
  from the same NFS server, will fail with `EXDEV`;
- `Remove empty folders` is ignored in this mode, and `Delete older updates` only removes the link,
  never the source file.

> [!NOTE]
> Stale links are not cleaned up: changing a template or deleting a source file leaves the old link
> behind in the destination folder.

### Setup with docker compose

```yaml
services:
  ownfoil:
    container_name: ownfoil
    image: ghcr.io/exoenjoi/ownfoil:latest
    environment:
      - PUID=1000
      - PGID=1000
    volumes:
      # One single mount holding both directories, hardlinks cannot cross filesystems
      - /mnt/nas/switch:/games
      - ./config:/app/config
      - ./data:/app/data
    ports:
      - "8465:8465"
```

Then, in `Settings`:
1. add `/games/torrents` (where your torrent client downloads) as a library path;
2. under `Organizer`, tick `Enable organizer` and set `Destination folder` to `/games/organized`;
3. hit `Submit`, then `Scan library`.

`/games/organized` now holds the templated tree, and `/games/torrents` is untouched and still
seeding. Check it with `ls -li`: a source and its link share the same inode number and a link
count of 2.

## Downloader

Ownfoil already knows what your library is missing: every update and DLC that exists upstream but
has no file is listed as missing content. The downloader searches that content on your trackers
through [Prowlarr](https://prowlarr.com/) — and on the `Discover` page, any Switch game at all,
whether you own something of it or not.

**Nothing downloads by itself.** Every grab is a release you picked from a list. There is no
scheduled job.

Prowlarr does the grabbing: Ownfoil sends it a release, Prowlarr passes it to *its own* download
client. So **Prowlarr must have a download client configured** (Settings > Download Clients).
Ownfoil never adds or removes a torrent.

Configure it in `Settings` under `Downloader`:

| Field | Notes |
| --- | --- |
| Prowlarr URL / API key | The key is in Prowlarr under Settings > General. `Test connection` checks it. |
| Categories | Optional Newznab category ids. There is no standard category for the Switch, so this is empty by default and every indexer is searched. |
| qBittorrent URL / credentials | Optional, **read only**, used to show download progress on the `Downloads` page. |
| Minimum seeders / Maximum size | Releases outside these bounds are greyed out in the list, with the reason. |
| Preferred extensions | Best first, used to rank the list. |

Two ways in:

- the <kbd>🔍</kbd> badge on a game with missing content, in the library;
- the `Discover` page, which searches every game titledb knows by name — the words you type can be
  scattered through the title, so `zelda breath of the wild` finds
  `The Legend of Zelda: Breath of the Wild`. Each card carries the title id, the release date and
  the publisher, to tell two same-named games apart.

Both open the same list of releases, sortable by name, size, seeders or date. Each release name
links to its page on the tracker. Releases that failed a filter are greyed out **with the reason**
and can still be grabbed — the filters are advice, you have the last word. A release with no seeder
at all is dropped from the list rather than greyed out: it cannot be downloaded.

> [!TIP]
> Point your download client's save path at the directory you configured as an Ownfoil library. With
> a hardlink [destination folder](#organizer-destination-hardlink-mode), the chain closes on itself:
> Prowlarr grabs, qBittorrent downloads into the library and keeps seeding, and the organizer
> hardlinks a properly named copy into your clean library.

A download is marked `completed` when the file has landed in your library and been identified, not
when the torrent finishes: the library is the source of truth. The history lives in
`config/downloads.json`.


