# Claudius Multimedia

**Free music & video player for Windows 11 (64-bit)** - freeware, source on GitHub (licence: GNU GPL v3, see `LICENSE`).
Created by **Michal Czapla & Claude AI**.

Plays almost any music or video file (built-in FFmpeg engine, no codec packs needed), keeps a music library like
MusicBee / AIMP, edits MP3/FLAC/M4A tags, downloads album covers and synced lyrics, and shows subtitles like
PotPlayer / VLC. Ribbon interface with System / Light / Dark theme and six languages
(English, Polski, Deutsch, Français, Italiano, Español).

![Library with synced lyrics](docs/screenshots/app-library-light-en.png)

| Video with subtitles (dark theme) | Tag editor |
|---|---|
| ![Video](docs/screenshots/app-video-dark-en.png) | ![Tag editor](docs/screenshots/app-tag-editor-light-en.png) |
| **About tab** | **Polish, dark theme** |
| ![About](docs/screenshots/app-about-light-en.png) | ![Polski](docs/screenshots/app-library-dark-pl.png) |

## Download the installer (built by GitHub)

1. Open the **Actions** tab -> latest green run of "Build Claudius Multimedia for Windows" -> **Artifacts**
   -> download `Claudius-Multimedia-installer` (Claudius-Multimedia-Setup-1.0.0.exe) or
   `Claudius-Multimedia-windows-x64` (portable zip: unzip anywhere, start `Claudius Multimedia.exe`).
2. Or, for a public download page: create a tag `v1.0.0` (see below); the installer then appears under **Releases**.

The installer puts the program in `C:\Program Files (x86)\Claudius Multimedia`, creates the Start Menu folder
**Claudius Multimedia** (program, Uninstall, Freeware notice, Read me), an optional desktop icon and optional
file associations, and registers the uninstaller in Windows Settings › Apps.

## Features

| | |
|---|---|
| **Playback** | Audio: MP3, FLAC (hi-res), M4A/AAC/ALAC, OGG, Opus, WAV, WMA, AIFF, APE, WavPack… Video: MP4, MKV, AVI, MOV, WMV, WebM, MPG, TS, FLV… Internet streams (http/https/rtsp). Play queue, shuffle, repeat all / one, speed 0.25–4×, snapshot (F12), aspect ratio, audio-track choice |
| **Subtitles** | SRT / WebVTT loaded automatically when they sit next to the video (`movie.srt`, `movie.pl.srt`), or by hand; embedded subtitle tracks |
| **Library** | Watches your music & video folders (SQLite, fast), album strip with covers, browse by artist / album / genre / track, search, ratings, favourites, play counts, smart lists (recently added, most played, missing cover, missing lyrics), playlists, M3U/M3U8/PLS import & export |
| **Tags** | Tag editor for one file or many at once (only changed fields are written) - ID3v2.4, Vorbis comments, MP4 atoms, APEv2. MusicBrainz look-up, tags from file name, rename files from tags |
| **Album covers** | Search iTunes, Deezer and MusicBrainz / Cover Art Archive, pick one, embed it - or fetch missing covers for the whole library in one go |
| **Lyrics** | Synced (karaoke-style, click a line to jump there) and plain lyrics from LRCLIB; saved as `.lrc` next to the track and/or inside the file; timing adjust; batch download |
| **Look** | Ribbon like the reference design, glossy icons, System / Light / Dark theme (follows Windows live), 6 accent colours, mini player, full screen, always on top |
| **Languages** | EN, PL, DE, FR, IT, ES - translation files in `lang\*.json`, editable |
| **Windows** | Splash screen while starting, single instance (double-click a file in Explorer and it plays in the open window), media keys while the window is active, drag & drop, "Play with Claudius Multimedia" on folders |

Online look-ups send only artist, album, title and length, and can be switched off in **Settings › Online**.

## How to build from scratch on GitHub

1. Create a new repository on github.com (e.g. `Claudius-Multimedia`).
2. Upload **all** files of this folder, keeping the structure (including the `lang` folder and the hidden folder `.github/workflows/`).
   Easiest: `git clone`, copy the files in, then `git add . && git commit -m "Claudius Multimedia 1.0.0" && git push`.
3. Push to `main` -> the build starts automatically (Actions tab, about 10 minutes). Also use *Run workflow* to start it by hand.
   The build also starts the finished program once (`--selftest`) to check that it opens and plays a test tone.
4. Release: `git tag v1.0.0 && git push origin v1.0.0` -> the workflow also creates a GitHub Release with
   `Claudius-Multimedia-Setup-1.0.0.exe`, `Claudius-Multimedia-portable-1.0.0.zip` and `SHA256SUMS.txt`.

## Build on your own PC

* Run from source: install Python 3.12 (64-bit), then `python -m pip install -r requirements.txt` and `python claudius_multimedia.py` (or `run.bat`).
* EXE: `build_exe.bat` -> `dist\Claudius Multimedia\Claudius Multimedia.exe` (a folder; keep it together).
* Installer: `build_installer.bat` (needs the free Inno Setup 6) -> `installer\Claudius-Multimedia-Setup-1.0.0.exe`.

## Keyboard shortcuts

`Space` play/pause · `←/→` seek 5 s · `Ctrl+←/→` 30 s · `↑/↓` volume · `M` mute · `N`/`P` next/previous · `S` stop ·
`[`/`]` speed · `F11`/`Enter` full screen · `Esc` leave full screen / mini player · `Ctrl+M` mini player ·
`Ctrl+O` open · `Ctrl+U` open URL · `Ctrl+T` tag editor · `Ctrl+L` lyrics · `Ctrl+F` search · `F5` rescan library · `F12` snapshot

## Files

| File | Purpose |
|---|---|
| `claudius_multimedia.py` | start-up: splash screen, single instance, self-test |
| `cm_main.py` | main window (ribbon tabs, library, now playing, About tab) |
| `cm_widgets.py`, `cm_dialogs.py` | ribbon, transport bar, video view, lyrics view; tag editor, cover / lyrics / MusicBrainz search, settings |
| `cm_player.py` | playback engine and play queue (Qt Multimedia + FFmpeg) |
| `cm_library.py`, `cm_tags.py`, `cm_online.py`, `cm_parse.py` | library database, tags, online services, LRC / SRT / M3U parsing |
| `cm_core.py`, `cm_theme.py`, `cm_icons.py` | version, settings, translations; themes; glossy icons and logo |
| `lang\*.json` | translations (en, pl, de, fr, it, es) |
| `claudius.ico`, `splash.png`, `version_info.txt` | program icon, splash screen, Windows version info |
| `FREEWARE.txt`, `LICENSE` | freeware notice shown by the installer; the licence (GNU GPL v3) |
| `build_exe.bat`, `build_installer.bat`, `installer.iss`, `run.bat` | local builds and start from source |
| `.github/workflows/build.yml` | automatic build on GitHub |
| `tools/check_translations.py` | checks that every language has every text |
| `docs/` | screenshots of the program and the original design mock-ups |

Settings, library database and cover cache are stored in `%APPDATA%\Claudius Multimedia`.
