"""Claudius Multimedia - online cover art, lyrics and MusicBrainz look-ups (only when the user asks, or for the
playing track when "auto lyrics" is on). Sends only artist / album / title / duration to the services below.

  - LRCLIB            https://lrclib.net           synced and plain lyrics (free, no key)
  - MusicBrainz       https://musicbrainz.org      tags (1 request per second, as their rules ask)
  - Cover Art Archive https://coverartarchive.org  covers for MusicBrainz releases
  - iTunes Search     https://itunes.apple.com     covers
  - Deezer            https://api.deezer.com       covers
"""
import json
import os
import queue
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request

from PySide6.QtCore import QObject, Qt, Signal, Slot

from cm_core import USER_AGENT

TIMEOUT = 15
_mb_lock = threading.Lock()
_mb_last = [0.0]


class OnlineError(Exception):
    pass


def _get(url, accept="application/json", binary=False):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            data = r.read(25 * 1024 * 1024)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise OnlineError(f"{urllib.parse.urlparse(url).netloc}: HTTP {e.code}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise OnlineError(f"{urllib.parse.urlparse(url).netloc}: {getattr(e, 'reason', e)}") from e
    if binary:
        return data
    try:
        return json.loads(data.decode("utf-8"))
    except ValueError as e:
        raise OnlineError("Unexpected answer from " + urllib.parse.urlparse(url).netloc) from e


def _mb(url):
    with _mb_lock:  # MusicBrainz allows one request per second
        wait = 1.05 - (time.monotonic() - _mb_last[0])
        if wait > 0:
            time.sleep(wait)
        try:
            return _get(url)
        finally:
            _mb_last[0] = time.monotonic()


def _q(text):
    return (text or "").replace('"', " ").strip()


# ---------------------------------------------------------------- lyrics
def lyrics_best(artist, title, album="", duration=0):
    """Best LRCLIB match: dict(synced, plain, source) or None."""
    params = {"artist_name": artist, "track_name": title}
    if album:
        params["album_name"] = album
    if duration:
        params["duration"] = int(round(duration))
    data = _get("https://lrclib.net/api/get?" + urllib.parse.urlencode(params))
    if not data and (album or duration):
        found = lyrics_search(artist, title)
        if duration:
            found.sort(key=lambda r: abs((r.get("duration") or 0) - duration))
        found.sort(key=lambda r: not r.get("synced"))
        return found[0] if found else None
    if not data or data.get("instrumental") and not (data.get("syncedLyrics") or data.get("plainLyrics")):
        return None
    return _lrclib_row(data)


def _lrclib_row(d):
    return {"source": "LRCLIB", "artist": d.get("artistName") or "", "title": d.get("trackName") or "",
            "album": d.get("albumName") or "", "duration": d.get("duration") or 0,
            "synced": d.get("syncedLyrics") or "", "plain": d.get("plainLyrics") or "",
            "instrumental": bool(d.get("instrumental"))}


def lyrics_search(artist, title):
    params = {"track_name": title}
    if artist:
        params["artist_name"] = artist
    data = _get("https://lrclib.net/api/search?" + urllib.parse.urlencode(params)) or []
    rows = [_lrclib_row(d) for d in data if isinstance(d, dict)]
    return [r for r in rows if r["synced"] or r["plain"]][:20]


# ---------------------------------------------------------------- covers
def cover_candidates(artist, album, title=""):
    """List of dicts: source, label, url (full size), thumb (small). Errors of one service do not stop the others."""
    out, errors = [], []
    term = " ".join(x for x in (artist, album or title) if x)
    try:
        q = urllib.parse.urlencode({"term": term, "entity": "album", "limit": 6})
        for r in (_get("https://itunes.apple.com/search?" + q) or {}).get("results", []):
            art = r.get("artworkUrl100")
            if art:
                out.append({"source": "iTunes", "label": f'{r.get("artistName", "")} - {r.get("collectionName", "")}',
                            "url": art.replace("100x100bb", "1200x1200bb"), "thumb": art.replace("100x100bb", "300x300bb")})
    except OnlineError as e:
        errors.append(str(e))
    try:
        q = urllib.parse.urlencode({"q": f'artist:"{_q(artist)}" album:"{_q(album or title)}"', "limit": 6})
        for r in (_get("https://api.deezer.com/search/album?" + q) or {}).get("data", []):
            if r.get("cover_xl"):
                out.append({"source": "Deezer", "label": f'{(r.get("artist") or {}).get("name", "")} - {r.get("title", "")}',
                            "url": r["cover_xl"], "thumb": r.get("cover_medium") or r["cover_xl"]})
    except OnlineError as e:
        errors.append(str(e))
    try:
        if album:
            q = urllib.parse.urlencode({"query": f'release:"{_q(album)}" AND artist:"{_q(artist)}"', "fmt": "json", "limit": 4})
            for r in (_mb("https://musicbrainz.org/ws/2/release/?" + q) or {}).get("releases", []):
                mbid = r.get("id")
                if mbid and (r.get("cover-art-archive") or {}).get("front", True):
                    out.append({"source": "Cover Art Archive", "label": f'{r.get("title", "")} ({r.get("date", "")[:4]})',
                                "url": f"https://coverartarchive.org/release/{mbid}/front-1200",
                                "thumb": f"https://coverartarchive.org/release/{mbid}/front-250"})
    except OnlineError as e:
        errors.append(str(e))
    if not out and errors:
        raise OnlineError("\n".join(errors))
    return out


def download(url):
    data = _get(url, accept="image/*", binary=True)
    if not data:
        raise OnlineError("Image not found")
    return data


def cover_best(artist, album, title=""):
    for c in cover_candidates(artist, album, title):
        try:
            return download(c["url"])
        except OnlineError:
            continue
    return None


# ---------------------------------------------------------------- MusicBrainz tags
def musicbrainz_lookup(artist, title, album="", duration=0):
    parts = [f'recording:"{_q(title)}"']
    if artist:
        parts.append(f'artist:"{_q(artist)}"')
    if album:
        parts.append(f'release:"{_q(album)}"')
    q = urllib.parse.urlencode({"query": " AND ".join(parts), "fmt": "json", "limit": 10})
    data = _mb("https://musicbrainz.org/ws/2/recording/?" + q) or {}
    out = []
    for rec in data.get("recordings", []):
        credit = "".join((a.get("name") or "") + (a.get("joinphrase") or "") for a in rec.get("artist-credit", []))
        length = (rec.get("length") or 0) / 1000
        for rel in (rec.get("releases") or [{}])[:3]:
            media = (rel.get("media") or [{}])[0]
            track = (media.get("track") or [{}])[0]
            num = track.get("number") or ""
            total = media.get("track-count") or ""
            ac = rel.get("artist-credit") or []
            album_artist = "".join((a.get("name") or "") + (a.get("joinphrase") or "") for a in ac) or credit
            out.append({
                "title": rec.get("title") or "", "artist": credit, "album": rel.get("title") or "",
                "albumartist": album_artist, "year": (rel.get("date") or "")[:4],
                "track": f"{num}/{total}" if num and total else str(num),
                "genre": ((rec.get("tags") or [{}])[0].get("name") or "").title() if rec.get("tags") else "",
                "score": int(rec.get("score") or 0), "length": length,
                "country": rel.get("country") or "", "release_id": rel.get("id") or "",
            })
    if duration:
        for r in out:
            if r["length"] and abs(r["length"] - duration) > 10:
                r["score"] -= 25
    out.sort(key=lambda r: -r["score"])
    return out[:15]


# ---------------------------------------------------------------- running work in the background
class _Dispatcher(QObject):
    """Lives on the GUI thread for the whole run of the program and is never deleted. Workers hand it small
    functions (results, progress) that it runs on the GUI thread. Nothing Qt-related is created or destroyed on a
    worker thread - that was the cause of crashes when many downloads (e.g. a cover search) finished together."""
    call = Signal(object)

    def __init__(self):
        super().__init__()
        self.call.connect(self._run, Qt.QueuedConnection)

    @Slot(object)
    def _run(self, fn):
        try:
            fn()
        except RuntimeError:
            pass        # the window / item that asked for the result was closed meanwhile
        except Exception:
            traceback.print_exc()


_dispatcher = None
_jobs = queue.Queue()
_workers = []
_workers_lock = threading.Lock()
WORKERS = max(4, min(8, os.cpu_count() or 4))


def _to_gui(fn):
    try:
        _dispatcher.call.emit(fn)
    except RuntimeError:
        pass            # program is closing


def _worker():
    while True:
        task = _jobs.get()
        try:
            task.execute()
        except Exception:
            traceback.print_exc()


def _ensure_workers():
    with _workers_lock:
        while len(_workers) < WORKERS:
            t = threading.Thread(target=_worker, name=f"claudius-worker-{len(_workers)}", daemon=True)
            t.start()
            _workers.append(t)


class Task:
    """fn(*args) on a background thread; done(result) / failed(message) / progress(i, n, text) are called on the
    GUI thread. Long jobs get progress= and task= arguments and stop early when task.cancelled is set."""

    def __init__(self, fn, args, done=None, failed=None, progress=None):
        self.fn, self.args = fn, args
        self.done_cb, self.failed_cb, self.progress_cb = done, failed, progress
        self.cancelled = False

    def execute(self):
        try:
            if self.progress_cb is not None:
                result = self.fn(*self.args, progress=self._progress, task=self)
            else:
                result = self.fn(*self.args)
        except OnlineError as e:
            self._fail(str(e))
        except Exception as e:  # keep the program running whatever happens in the worker
            traceback.print_exc()
            self._fail(f"{type(e).__name__}: {e}")
        else:
            if self.done_cb is not None:
                cb = self.done_cb
                _to_gui(lambda: cb(result))

    def _fail(self, msg):
        if self.failed_cb is not None:
            cb = self.failed_cb
            _to_gui(lambda: cb(msg))

    def _progress(self, i, n, text=""):
        if self.progress_cb is not None:
            cb = self.progress_cb
            _to_gui(lambda: cb(i, n, text))


def run(fn, *args, done=None, failed=None, progress=None):
    """Start fn(*args) in the background. Must be called from the GUI thread."""
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = _Dispatcher()
    _ensure_workers()
    task = Task(fn, args, done, failed, progress)
    _jobs.put(task)
    return task
