# <img src="https://github.com/user-attachments/assets/3cfdf010-50c3-41ae-aa86-e31b22466686" height="28"> Ownfoil
[![Static Badge](https://img.shields.io/badge/github-repo-blue?logo=github)](https://github.com/a1ex4/ownfoil)
[![Latest Release](https://img.shields.io/docker/v/a1ex4/ownfoil?sort=semver)](https://github.com/a1ex4/ownfoil/releases/latest)
[![Docker Image Size (latest semver)](https://img.shields.io/docker/image-size/a1ex4/ownfoil?sort=date&arch=amd64)](https://hub.docker.com/r/a1ex4/ownfoil/tags)  
[![Docker Pulls](https://img.shields.io/docker/pulls/a1ex4/ownfoil?)](https://hub.docker.com/r/a1ex4/ownfoil)
[![Unraid downloads](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fca.unraid.net%2Fapi%2Fsearch%3Fquery%3Downfoil%26type%3Ddocker&query=%24.hits%5B0%5D.chartData.totalDownloadsChart.data%5B6%5D&label=unraid%20downloads&color=F15A2C)](https://preview.ca.unraid.net/apps?q=ownfoil&app=v2fayr)  
![Image archs](https://img.shields.io/badge/platforms-amd64%20%7C%20%20arm64%2Fv8%20%7C%20arm%2Fv7%20%7C%20arm%2Fv6-8A2BE2)  
[![Tinfoil Version](https://img.shields.io/badge/Tinfoil-v20.0-da1c5c)](https://tinfoil.io/Download)
[![Sphaira Version](https://img.shields.io/badge/Sphaira-v1.0.0-%233cd57a)](https://github.com/ITotalJustice/sphaira)
[![CyberFoil Version](https://img.shields.io/badge/CyberFoil-v1.4.1-firebrick)](https://github.com/luketanti/CyberFoil)

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
> It also adds an [auto-downloader](#auto-downloader): Ownfoil already knows which updates and DLCs
> your library is missing, so it can search them through Prowlarr and hand the release to Prowlarr's
> own download client. Combined with the hardlink mode, the whole chain closes on itself: grab,
> seed, hardlink into a clean library.
>
> See [Organizer destination (hardlink mode)](#organizer-destination-hardlink-mode) for setup, and
> [`ghcr.io/exoenjoi/ownfoil`](https://github.com/exoenjoi/ownfoil/pkgs/container/ownfoil) for the
> image built from this fork.
>
> Everything else is upstream's work - the original README follows.

Ownfoil is a Nintendo Switch library manager, that will also turn your library into a fully customizable and self-hosted Shop, supporting multiple clients. The goal of this project is to manage your library, identify any missing content (DLCs or updates) and provide a user friendly way to browse and install your content. Some of the features include:
- [x] multi user authentication
- [x] web interface for configuration and browsing the library
- [x] content identification using content decryption or filename
- [x] automatic library organization
- [x] console keys management
- [x] multiple clients support
- [x] shop customization

# Installation

- [Using Docker](#using-docker)
- [Using Python](#using-python)
- [Using Unraid](https://preview.ca.unraid.net/apps?q=ownfoil&app=v2fayr)
- [Using Helm chart](./chart)

> [!CAUTION]
> There is __no website associated with this project__, only this GitHub repo.  
> Ownfoil is __not released as an application or an executable file__ - DO NOT download or execute anything related to Ownfoil outside of this repository and its instructions.

## Using Docker
Ownfoil is shipped as a docker container for easy deployment, data persistency and updates. If you are unfamiliar with Docker, check [the installation documentation here](https://docs.docker.com/engine/install/).  
### Docker run

<details>

Running this command will start the shop on local port `8465` with the library in `/your/game/directory`, and persist the `data` and `config` directories:
```
docker run -d -p 8465:8465 \
   -v /your/game/directory:/games \
   -v ./config:/app/config \
   -v ./data:/app/data \
   --name ownfoil \
   a1ex4/ownfoil
```
To see the logs of the container:  

      docker logs -f ownfoil

</details>

### Docker compose
<details>

Create a file named `docker-compose.yml` with the following content:
```
---
services:
  ownfoil:
    container_name: ownfoil
    image: a1ex4/ownfoil
   # environment:
   #   # For write permission in config directory
   #   - PUID=1000
   #   - PGID=1000
   #   # to create/update an admin user at startup
   #   - USER_ADMIN_NAME=admin
   #   - USER_ADMIN_PASSWORD=asdvnf!546
   #   # to create/update a regular user at startup
   #   - USER_GUEST_NAME=guest
   #   - USER_GUEST_PASSWORD=oerze!@8981
    volumes:
      - /your/game/directory:/games
      - ./data:/app/data
      - ./config:/app/config
    ports:
      - "8465:8465"
```
> [!TIP]
> You can control the `UID` and `GID` of the user running the app in the container with the `PUID` and `PGID` environment variables. By default the user is created with `1000:1000`. If you want to have the same ownership for mounted directories, you need to set those variables with the UID and GID returned by the `id` command.

You can then create and start the container with the command (executed in the same directory as the docker-compose file):

    docker-compose up -d

This is usefull if you don't want to remember the `docker run` command and have a persistent and reproductible container configuration.
</details>

## Using Python
This requires Python to be installed on your system. If that's not the case [you can use uv](https://docs.astral.sh/uv/getting-started/) to [install a Python environment](https://docs.astral.sh/uv/guides/install-python).
<details>
Download the repository as a zip archive, extract it, install the dependencies and you're good to go!

1. Download the repository code on GitHub:
   1. __Make sure you are visiting the official repo URL__ at https://github.com/a1ex4/ownfoil
   2. Above the list of files, click `<> Code`.
   3. Click `Download ZIP`.
2. Extract the zip archive and navigate to the `ownfoil-master` directory
3. Open a terminal in this folder (on Windows, `Right click` → `Open command window here`)
4. Install dependencies and run Ownfoil:
```
$ pip install -r requirements.txt
$ python app/app.py
```
</details>

# Usage
Once Ownfoil is running, the Shop Web UI is now accessible with your computer/server IP and port, by navigating to `http://<computer/server IP>:8465`, i.e. `http://localhost:8465` from the same computer or `http://192.168.1.100:8465` from a device in your network.

## Clients supported

Ownfoil supports multiple clients to install content on your Nintendo Switch:
### [Tinfoil:](https://tinfoil.io/Download)
- ✅ `HTTP` / `HTTPS` protocol support
- ✅ User authentication
- ✅ Shop browsing with icons and banners
- ✅ Content filtering (games, updates, DLC, XCI) based on URL
- ✅ New games, DLC, Updates, Recommended and XCI sections
- ✅ Compressed content (NSZ and XCZ) support
- ✅ Encrypted shop support
- ✅ Client side Host verification for secure connections
- ✅ Tinfoil shop customization

### [Sphaira:](https://github.com/ITotalJustice/sphaira)
- ✅ `HTTP` / `HTTPS` protocol support
- ✅ User authentication
- ✅ Directory-based file browsing
- ✅ Content filtering (games, updates, DLC, XCI) based on URL
- ✅ Compressed content (NSZ and XCZ) support

### [CyberFoil:](https://github.com/luketanti/CyberFoil)
- ✅ `HTTP` / `HTTPS` protocol support
- ✅ User authentication
- ✅ Shop browsing with icons and Sections (Updates, DLC)
- ✅ Compressed content (NSZ and XCZ) support
- ✅ Client side Host verification for secure connections
- ✅ Custom welcome message (MOTD)

> [!TIP]
> Check the `Setup` page in the Web UI for specific instructions on configuring each app, using local or remote access.

## User administration
Ownfoil requires an `admin` user to be created to enable Authentication for your Shop. Go to the `Settings` to create a first user that will have admin rights. Then you can add more users to your shop the same way.

## Library administration
In the `Settings` page under the `Library` section, you can add directories containing your content. You can then manually trigger the library scan: Ownfoil will scan the content of the directories and try to identify every supported file (currently `nsp`, `nsz`, `xci`, `xcz`).

> [!TIP]
> There is watchdog in place for all your configured libraries: files moved, renamed, added or removed will be reflected directly in your library.

The automatic library organization can be configured in the `Organizer` section to set your own templates, enable removing older updates...

### Organizer destination (hardlink mode)

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

#### Setup with docker compose

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

## Auto-downloader

Ownfoil already knows what your library is missing: every update and DLC that exists upstream but
has no file is listed as missing content. The downloader turns that list into actual downloads,
through [Prowlarr](https://prowlarr.com/).

Prowlarr does the grabbing itself: Ownfoil sends it a release, Prowlarr passes it to *its own*
download client. So **Prowlarr must have a download client configured** (Settings > Download
Clients). Ownfoil never adds or removes a torrent.

Configure it in `Settings` under `Downloader`:

| Field | Notes |
| --- | --- |
| Prowlarr URL / API key | The key is in Prowlarr under Settings > General. `Test connection` checks it. |
| Categories | Optional Newznab category ids. There is no standard category for the Switch, so this is empty by default and every indexer is searched. |
| qBittorrent URL / credentials | Optional, **read only**, used to show download progress on the `Downloads` page. |
| Minimum seeders / Maximum size | Releases outside these bounds are never grabbed. |
| Maximum grabs per run | The safety net. On a large library the first run could otherwise queue hundreds of torrents. |
| Preferred extensions | Best first. A release whose extension is not listed is never grabbed. |
| Run interval | `0` disables the automatic job while keeping manual searches. |

**The automatic job only grabs updates**, and only the latest missing one of each game whose base
game you own. DLCs are searched manually: on a game with missing content, the
<kbd>🔍</kbd> badge opens a list of releases with a `Grab` button on each.

That list is also the best way to judge the matching before enabling anything: releases the
automatic job would refuse are greyed out with the reason. Most refusals are the important one —
an update release that carries no version marker in its name, which is usually the base game.

> [!TIP]
> Point your download client's save path at the directory you configured as an Ownfoil library. With
> a hardlink [destination folder](#organizer-destination-hardlink-mode), the chain closes on itself:
> Prowlarr grabs, qBittorrent downloads into the library and keeps seeding, and the organizer
> hardlinks a properly named copy into your clean library.

A download is marked `completed` when the file has landed in your library and been identified, not
when the torrent finishes: the library is the source of truth. The history lives in
`config/downloads.json`.

## Titles configuration
In the `Settings` page under the `Titles` section is where you specify the language of your Shop (currently the same for all users).

This is where you can also upload your `console keys` file to enable content identification using decryption, instead of only using filenames. If you do not provide keys, Ownfoil expects the files to be named `[APP_ID][vVERSION]`.

Ownfoil will warn you if any master key is invalid or missing, to ensure all backups can be decrypted and identified.

## Shop customization
In the `Settings` page under the `Shop` section is where you customize your Shop, like the message displayed when successfully accessing the shop from Tinfoil or if the shop is private or public.
