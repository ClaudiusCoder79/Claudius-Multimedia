"""Claudius Multimedia - music & video library (SQLite database in %APPDATA%\\Claudius Multimedia).

Version 1.1 adds: albums kept apart by album artist (or folder), hidden items that rescans don't bring back,
missing files (kept with their ratings until located or removed), Recycle Bin delete, listening history,
smart playlists, resume positions, folder tree, statistics, backup and restore."""
import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
import threading
import time
import zipfile

import cm_tags
from cm_core import APP_NAME, APP_VERSION, AUDIO_EXT, VIDEO_EXT, data_dir
from cm_parse import title_from_filename

SCHEMA = """
CREATE TABLE IF NOT EXISTS tracks (
  path TEXT PRIMARY KEY, title TEXT, artist TEXT, albumartist TEXT, album TEXT, genre TEXT, year TEXT,
  track_no INTEGER, disc_no INTEGER, duration REAL, codec TEXT, bitrate INTEGER, samplerate INTEGER, bits INTEGER,
  has_cover INTEGER, has_lyrics INTEGER, rating INTEGER DEFAULT 0, favourite INTEGER DEFAULT 0,
  play_count INTEGER DEFAULT 0, last_played REAL DEFAULT 0, added REAL, mtime REAL, size INTEGER, kind TEXT, folder TEXT,
  album_key TEXT DEFAULT '', missing INTEGER DEFAULT 0, hidden INTEGER DEFAULT 0, hidden_at REAL DEFAULT 0,
  resume_ms INTEGER DEFAULT 0);
CREATE INDEX IF NOT EXISTS ix_album ON tracks(album);
CREATE INDEX IF NOT EXISTS ix_artist ON tracks(artist);
CREATE TABLE IF NOT EXISTS playlists (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, created REAL);
CREATE TABLE IF NOT EXISTS playlist_items (playlist INTEGER, pos INTEGER, path TEXT);
CREATE TABLE IF NOT EXISTS smart_playlists (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, spec TEXT, created REAL);
CREATE TABLE IF NOT EXISTS listens (path TEXT, ts REAL, seconds REAL);
CREATE INDEX IF NOT EXISTS ix_listens_ts ON listens(ts);
"""
NEW_COLUMNS = {"album_key": "TEXT DEFAULT ''", "missing": "INTEGER DEFAULT 0", "hidden": "INTEGER DEFAULT 0",
               "hidden_at": "REAL DEFAULT 0", "resume_ms": "INTEGER DEFAULT 0"}
SCHEMA_VERSION = 2
_migrate_lock = threading.Lock()
_migrated = set()


def db_path():
    return os.path.join(data_dir(), "library.db")


def connect():
    path = db_path()
    con = sqlite3.connect(path, timeout=30)
    con.row_factory = sqlite3.Row
    if path not in _migrated:
        with _migrate_lock:
            if path not in _migrated:
                con.executescript(SCHEMA)
                con.execute("PRAGMA journal_mode=WAL")
                _migrate(con)
                _migrated.add(path)
    return con


def _migrate(con):
    """Bring a 1.0 database up to date (new columns, album keys)."""
    cols = {r[1] for r in con.execute("PRAGMA table_info(tracks)")}
    for col, decl in NEW_COLUMNS.items():
        if col not in cols:
            con.execute(f"ALTER TABLE tracks ADD COLUMN {col} {decl}")
    con.execute("CREATE INDEX IF NOT EXISTS ix_album_key ON tracks(album_key)")
    con.execute("CREATE INDEX IF NOT EXISTS ix_folder ON tracks(folder)")
    if con.execute("PRAGMA user_version").fetchone()[0] < SCHEMA_VERSION:
        rows = con.execute("SELECT path, album, albumartist, folder FROM tracks").fetchall()
        con.executemany("UPDATE tracks SET album_key=? WHERE path=?",
                        [(album_key(r["album"], r["albumartist"], r["folder"]), r["path"]) for r in rows])
        con.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
    con.commit()


def forget_connection_cache():
    """After a restore the database file is new: run the migration check again."""
    _migrated.clear()


def _int(text):
    try:
        return int(str(text).split("/")[0].strip() or 0)
    except ValueError:
        return 0


_DISC_DIR = re.compile(r"^(cd|disc|disk|dysk|p[lł]yta|disque|disco)[\s_.\-]*\d+\b", re.I)


def album_key(album, albumartist, folder):
    """Albums are told apart by album artist. Without an album artist the folder decides, so two different
    "Greatest Hits" stay apart while a compilation (many artists, one folder) stays together. CD1 / CD2
    sub-folders count as one album."""
    album = (album or "").strip()
    if not album:
        return ""
    if (albumartist or "").strip():
        return album.lower() + "\x1f" + albumartist.strip().lower()
    folder = folder or ""
    if _DISC_DIR.match(os.path.basename(folder)):
        folder = os.path.dirname(folder)
    return album.lower() + "\x1fdir:" + os.path.normcase(folder)


def row_from_file(path, st=None):
    st = st or os.stat(path)
    ext = os.path.splitext(path)[1].lower()
    video = ext in VIDEO_EXT
    info = cm_tags.read(path) if (ext in AUDIO_EXT or ext in (".mp4", ".m4v", ".mov")) else {}
    guess = title_from_filename(path)
    title = info.get("title") or guess.get("title") or os.path.splitext(os.path.basename(path))[0]
    lrc = os.path.isfile(cm_tags.lrc_path(path))
    has_cover = bool(info.get("has_cover")) or (not video and cm_tags.folder_cover(path) is not None)
    folder = os.path.dirname(path)
    album = info.get("album", "")
    albumartist = info.get("albumartist", "")
    return {
        "path": path, "title": title, "artist": info.get("artist") or ("" if video else guess.get("artist", "")),
        "albumartist": albumartist, "album": album, "genre": info.get("genre", ""),
        "year": info.get("year", ""), "track_no": _int(info.get("track") or guess.get("track", "")),
        "disc_no": _int(info.get("disc", "")), "duration": info.get("duration", 0.0),
        "codec": info.get("codec") or ext.lstrip(".").upper(), "bitrate": info.get("bitrate", 0),
        "samplerate": info.get("samplerate", 0), "bits": info.get("bits", 0),
        "has_cover": int(has_cover), "has_lyrics": int(bool(info.get("lyrics")) or lrc),
        "mtime": st.st_mtime, "size": st.st_size, "kind": "video" if video else "audio",
        "folder": folder, "album_key": "" if video else album_key(album, albumartist, folder), "missing": 0,
    }


def upsert(con, row):
    existing = con.execute("SELECT added FROM tracks WHERE path=?", (row["path"],)).fetchone()
    row = dict(row)
    row.setdefault("added", existing["added"] if existing else time.time())
    if existing:
        sets = ", ".join(f"{k}=?" for k in row if k != "path")
        con.execute(f"UPDATE tracks SET {sets} WHERE path=?", [v for k, v in row.items() if k != "path"] + [row["path"]])
    else:
        keys = ", ".join(row)
        con.execute(f"INSERT INTO tracks ({keys}) VALUES ({', '.join('?' * len(row))})", list(row.values()))


SKIP_DIRS = ("$recycle.bin", "system volume information")


def _inside(path, folders):
    p = os.path.normcase(os.path.abspath(path))
    for f in folders:
        f = os.path.normcase(os.path.abspath(f)).rstrip("\\/")
        if p == f or p.startswith(f + os.sep):
            return True
    return False


def scan(folders, progress=None, task=None):
    """Add new / changed media files of the folders. Files that disappeared are marked as missing (not deleted:
    their ratings and play counts stay until the user locates or removes them). Hidden files are left alone.
    Runs on a worker thread."""
    con = connect()
    known = {r["path"]: (r["mtime"], r["missing"]) for r in con.execute("SELECT path, mtime, missing FROM tracks")}
    found, todo, back = set(), [], []
    for folder in folders:
        for root, dirs, files in os.walk(folder):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d.lower() not in SKIP_DIRS]
            for name in files:
                ext = os.path.splitext(name)[1].lower()
                if ext in AUDIO_EXT or ext in VIDEO_EXT:
                    p = os.path.join(root, name)
                    found.add(p)
                    try:
                        st = os.stat(p)
                    except OSError:
                        continue
                    old = known.get(p)
                    if old is None or old[0] != st.st_mtime:
                        todo.append((p, st))
                    elif old[1]:
                        back.append(p)
            if task is not None and task.cancelled:
                con.close()
                return {"added": 0, "missing": 0, "back": 0}
    added = 0
    for i, (p, st) in enumerate(todo):
        if task is not None and task.cancelled:
            break
        try:
            upsert(con, row_from_file(p, st))
            added += 1
        except Exception:
            pass
        if progress and (i % 25 == 0 or i == len(todo) - 1):
            progress(i + 1, len(todo), os.path.basename(p))
            con.commit()
    con.executemany("UPDATE tracks SET missing=0 WHERE path=?", [(p,) for p in back])
    newly_missing = 0
    for p, (_mtime, was_missing) in known.items():
        if p in found:
            continue
        if _inside(p, folders) or not os.path.exists(p):
            if not was_missing and not os.path.exists(p):
                con.execute("UPDATE tracks SET missing=1 WHERE path=?", (p,))
                newly_missing += 1
    con.commit()
    con.close()
    return {"added": added, "missing": newly_missing, "back": len(back)}


def _like_prefix(folder):
    prefix = os.path.abspath(folder).rstrip("\\/") + os.sep
    return prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def remove_folder(folder):
    """A library folder was taken off the list: its entries leave the library."""
    con = connect()
    con.execute("DELETE FROM tracks WHERE path LIKE ? ESCAPE '\\'", (_like_prefix(folder),))
    con.commit()
    con.close()


def refresh_file(path):
    con = connect()
    try:
        upsert(con, row_from_file(path))
        con.commit()
    finally:
        con.close()


def ensure(paths):
    """Make sure files that are being played appear in the library tables (for ratings / play counts)."""
    con = connect()
    for p in paths:
        if os.path.isfile(p) and not con.execute("SELECT 1 FROM tracks WHERE path=?", (p,)).fetchone():
            try:
                upsert(con, row_from_file(p))
            except Exception:
                pass
    con.commit()
    con.close()


# --------------------------------------------------------------- queries used by the views
VIEWS = ["music", "videos", "favourites", "recent", "most", "nocover", "nolyrics", "missing", "hidden"]
WHERE = {
    "music": "kind='audio'", "videos": "kind='video'", "favourites": "favourite=1",
    "recent": "added > strftime('%s','now') - 30*86400", "most": "play_count > 0",
    "nocover": "kind='audio' AND has_cover=0 AND missing=0", "nolyrics": "kind='audio' AND has_lyrics=0 AND missing=0",
    "missing": "missing=1", "all": "1=1",
}
ORDER = {"recent": "added DESC", "most": "play_count DESC, last_played DESC", "videos": "lower(title)"}
DEFAULT_ORDER = "lower(COALESCE(NULLIF(albumartist,''), artist)), lower(album), disc_no, track_no, lower(title)"


def view_where(view):
    if view == "hidden":
        return "hidden=1"
    return f"hidden=0 AND ({WHERE.get(view, '1=1')})"


def query(view="music", search="", artist=None, album_key=None, genre=None, playlist=None, folder=None, smart=None):
    con = connect()
    try:
        params = []
        limit = 0
        if playlist is not None:
            sql = "SELECT t.* FROM playlist_items i JOIN tracks t ON t.path=i.path WHERE i.playlist=? AND t.hidden=0"
            params.append(playlist)
            order = "i.pos"
        elif smart is not None:
            where, sparams, order, limit = smart_sql(smart)
            sql = f"SELECT * FROM tracks WHERE hidden=0 AND ({where})"
            params += sparams
        else:
            sql = f"SELECT * FROM tracks WHERE {view_where(view)}"
            order = ORDER.get(view, DEFAULT_ORDER)
            if view == "most":
                limit = 200
        if artist is not None:
            sql += " AND (artist=? OR albumartist=?)"
            params += [artist, artist]
        if album_key is not None:
            sql += " AND album_key=?"
            params.append(album_key)
        if genre is not None:
            sql += " AND genre=?"
            params.append(genre)
        if folder is not None:
            sql += " AND (folder=? OR path LIKE ? ESCAPE '\\')"
            params += [os.path.normpath(folder), _like_prefix(folder)]
        if search:
            for word in search.split():
                like = f"%{word}%"
                sql += " AND (title LIKE ? OR artist LIKE ? OR album LIKE ? OR genre LIKE ? OR path LIKE ?)"
                params += [like] * 5
        sql += f" ORDER BY {order}"
        if limit:
            sql += f" LIMIT {int(limit)}"
        return [dict(r) for r in con.execute(sql, params)]
    finally:
        con.close()


ALBUM_SORTS = ["artist", "title", "year", "added", "plays"]


def albums(view="music", sort="artist", search=""):
    """Albums: list of dicts key, album, artist (None = various artists), count, sample path, year, added, plays."""
    con = connect()
    try:
        params = []
        sql = (f"SELECT album_key, MAX(album) album, MAX(albumartist) aa, MAX(artist) a, "
               f"COUNT(DISTINCT lower(artist)) na, COUNT(*) n, MIN(path) p, MAX(year) y, MAX(added) added, "
               f"SUM(play_count) plays, SUM(duration) dur FROM tracks WHERE {view_where(view)} AND album_key<>''")
        if search:
            for word in search.split():
                sql += " AND (title LIKE ? OR artist LIKE ? OR album LIKE ? OR albumartist LIKE ?)"
                params += [f"%{word}%"] * 4
        sql += " GROUP BY album_key"
        out = []
        for r in con.execute(sql, params):
            who = r["aa"] or (None if r["na"] > 1 else r["a"]) or ""
            out.append({"key": r["album_key"], "album": r["album"], "artist": who, "count": r["n"], "sample": r["p"],
                        "year": r["y"] or "", "added": r["added"] or 0, "plays": r["plays"] or 0, "duration": r["dur"] or 0})
    finally:
        con.close()
    keyfn = {
        "artist": lambda a: ((a["artist"] or "\uffff").lower(), a["year"], a["album"].lower()),
        "title": lambda a: a["album"].lower(),
        "year": lambda a: (-_int(a["year"]), a["album"].lower()),
        "added": lambda a: -a["added"],
        "plays": lambda a: -a["plays"],
    }.get(sort)
    out.sort(key=keyfn or (lambda a: a["album"].lower()))
    return out


def groups(kind, view="music"):
    """Distinct artists / genres with counts."""
    con = connect()
    try:
        col = {"artists": "COALESCE(NULLIF(albumartist,''), artist)", "genres": "genre"}[kind]
        sql = f"SELECT {col} AS g, COUNT(*) n FROM tracks WHERE {view_where(view)} AND {col}<>'' GROUP BY g ORDER BY lower(g)"
        return [(r["g"], r["n"]) for r in con.execute(sql)]
    finally:
        con.close()


def folders(view="music"):
    """Distinct folders that hold tracks of the view, with the number of tracks directly in each."""
    con = connect()
    try:
        return [(r["folder"], r["n"]) for r in con.execute(
            f"SELECT folder, COUNT(*) n FROM tracks WHERE {view_where(view)} GROUP BY folder ORDER BY lower(folder)")]
    finally:
        con.close()


def stats():
    con = connect()
    try:
        r = con.execute("SELECT COUNT(*) n, SUM(kind='audio') a, SUM(kind='video') v, "
                        "COUNT(DISTINCT CASE WHEN album_key<>'' THEN album_key END) al, "
                        "SUM(size) s, SUM(has_cover) c, SUM(has_lyrics) l FROM tracks WHERE hidden=0").fetchone()
        return {k: (r[k] or 0) for k in ("n", "a", "v", "al", "s", "c", "l")}
    finally:
        con.close()


def counts():
    con = connect()
    try:
        return {v: con.execute(f"SELECT COUNT(*) FROM tracks WHERE {view_where(v)}").fetchone()[0] for v in VIEWS}
    finally:
        con.close()


def update_fields(path, **fields):
    if not fields:
        return
    con = connect()
    try:
        con.execute(f"UPDATE tracks SET {', '.join(f'{k}=?' for k in fields)} WHERE path=?", list(fields.values()) + [path])
        con.commit()
    finally:
        con.close()


def get(path):
    con = connect()
    try:
        r = con.execute("SELECT * FROM tracks WHERE path=?", (path,)).fetchone()
        return dict(r) if r else None
    finally:
        con.close()


def get_many(paths):
    con = connect()
    try:
        out = {}
        paths = list(paths)
        for i in range(0, len(paths), 500):
            chunk = paths[i:i + 500]
            for r in con.execute(f"SELECT * FROM tracks WHERE path IN ({','.join('?' * len(chunk))})", chunk):
                out[r["path"]] = dict(r)
        return out
    finally:
        con.close()


def played(path, duration=0):
    con = connect()
    try:
        con.execute("UPDATE tracks SET play_count=play_count+1, last_played=?, "
                    "duration=CASE WHEN duration>0 THEN duration ELSE ? END WHERE path=?", (time.time(), duration, path))
        con.commit()
    finally:
        con.close()


def record_listen(path, seconds):
    """Listening history (for statistics): how long a track was actually listened to."""
    if seconds < 5:
        return
    con = connect()
    try:
        con.execute("INSERT INTO listens(path, ts, seconds) VALUES (?,?,?)", (path, time.time(), float(seconds)))
        con.commit()
    finally:
        con.close()


def set_resume(path, ms):
    update_fields(path, resume_ms=int(max(0, ms)))


def rename_path(old, new):
    """A file got a new path (renamed / located). If the new path is already in the library the two entries are
    merged, keeping the ratings, favourites and play counts of both."""
    if old == new:
        return
    con = connect()
    try:
        a = con.execute("SELECT * FROM tracks WHERE path=?", (old,)).fetchone()
        b = con.execute("SELECT * FROM tracks WHERE path=?", (new,)).fetchone()
        if a is not None and b is not None:
            con.execute("UPDATE tracks SET rating=MAX(rating,?), favourite=MAX(favourite,?), play_count=play_count+?, "
                        "last_played=MAX(last_played,?), added=MIN(added,?), hidden=0, missing=0 WHERE path=?",
                        (a["rating"] or 0, a["favourite"] or 0, a["play_count"] or 0, a["last_played"] or 0,
                         a["added"] or time.time(), new))
            con.execute("DELETE FROM tracks WHERE path=?", (old,))
        elif a is not None:
            con.execute("UPDATE tracks SET path=?, folder=?, missing=0 WHERE path=?", (new, os.path.dirname(new), old))
        con.execute("UPDATE playlist_items SET path=? WHERE path=?", (new, old))
        con.execute("UPDATE listens SET path=? WHERE path=?", (new, old))
        con.commit()
    finally:
        con.close()
    if os.path.isfile(new):
        try:
            refresh_file(new)
        except Exception:
            pass


def relocate(old, new):
    """The user found a missing file at `new`. Works out which folder moved (e.g. D:\\Music -> E:\\Music, or one
    album folder) and finds the other missing files there too. Returns how many other files were found."""
    rename_path(old, new)
    o_prefix, n_prefix, steps = old, new, 0
    while steps < 60:
        ob, nb = os.path.basename(o_prefix), os.path.basename(n_prefix)
        od, nd = os.path.dirname(o_prefix), os.path.dirname(n_prefix)
        if ob and nb and ob.lower() == nb.lower() and od and nd and od != o_prefix and nd != n_prefix:
            o_prefix, n_prefix, steps = od, nd, steps + 1
        else:
            break
    if steps == 0:  # the file itself was renamed: only its folder can be matched
        o_prefix, n_prefix = os.path.dirname(old), os.path.dirname(new)
    con = connect()
    try:
        rows = [r["path"] for r in con.execute("SELECT path FROM tracks WHERE missing=1")]
    finally:
        con.close()
    base = os.path.normcase(o_prefix.rstrip("\\/"))
    found = 0
    for p in rows:
        np_ = os.path.normcase(p)
        if np_.startswith(base + os.sep) or np_.startswith(base + "/"):
            cand = os.path.normpath(os.path.join(n_prefix, p[len(base) + 1:]))
            if os.path.isfile(cand):
                rename_path(p, cand)
                found += 1
    return found


def hide(paths):
    """Remove from the library without touching the files. Rescans don't bring them back; Tools > Hidden items
    restores them (with their ratings, play counts and playlist places)."""
    con = connect()
    try:
        now = time.time()
        con.executemany("UPDATE tracks SET hidden=1, hidden_at=? WHERE path=?", [(now, p) for p in paths])
        con.commit()
    finally:
        con.close()


def unhide(paths):
    con = connect()
    try:
        con.executemany("UPDATE tracks SET hidden=0, hidden_at=0 WHERE path=?", [(p,) for p in paths])
        con.commit()
    finally:
        con.close()


def forget(paths):
    """Remove entries completely (files deleted, or missing files the user gave up on)."""
    con = connect()
    try:
        rows = [(p,) for p in paths]
        con.executemany("DELETE FROM tracks WHERE path=?", rows)
        con.executemany("DELETE FROM playlist_items WHERE path=?", rows)
        con.commit()
    finally:
        con.close()


LEFTOVER_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".lrc", ".txt", ".nfo", ".cue", ".log", ".m3u",
                ".m3u8", ".sfv", ".md5", ".ffp", ".accurip", ".ini", ".db", ".url"}


def _move_to_trash(path):
    from PySide6.QtCore import QFile
    try:
        return bool(QFile.moveToTrash(path))
    except Exception:
        return False


def trash(paths):
    """Move files to the Recycle Bin (never deletes for good: if the Recycle Bin can't take a file, it stays).
    Their .lrc / subtitle files go too, and a folder that is left with only covers / logs goes to the
    Recycle Bin as well. Returns (moved paths, failed [(path, reason)])."""
    done, failed, dirs = [], [], set()
    for p in paths:
        if not os.path.exists(p):
            done.append(p)
            continue
        if _move_to_trash(p):
            done.append(p)
            dirs.add(os.path.dirname(p))
            stem = os.path.splitext(p)[0]
            for side in (".lrc", ".srt", ".vtt"):
                if os.path.exists(stem + side):
                    _move_to_trash(stem + side)
        else:
            failed.append((p, "Recycle Bin"))
    for d in dirs:
        try:
            names = os.listdir(d)
        except OSError:
            continue
        if any(os.path.isdir(os.path.join(d, n)) for n in names):
            continue
        if all(os.path.splitext(n)[1].lower() in LEFTOVER_EXT for n in names):
            _move_to_trash(d)
    forget(done)
    return done, failed


def hidden_rows():
    con = connect()
    try:
        return [dict(r) for r in con.execute("SELECT * FROM tracks WHERE hidden=1 ORDER BY hidden_at DESC, lower(path)")]
    finally:
        con.close()


# --------------------------------------------------------------- playlists
def playlists():
    con = connect()
    try:
        return [(r["id"], r["name"], r["n"]) for r in con.execute(
            "SELECT p.id, p.name, (SELECT COUNT(*) FROM playlist_items i JOIN tracks t ON t.path=i.path "
            "WHERE i.playlist=p.id AND t.hidden=0) n FROM playlists p ORDER BY lower(p.name)")]
    finally:
        con.close()


def create_playlist(name):
    con = connect()
    try:
        cur = con.execute("INSERT OR IGNORE INTO playlists(name, created) VALUES (?,?)", (name, time.time()))
        con.commit()
        if cur.lastrowid and cur.rowcount:
            return cur.lastrowid
        return con.execute("SELECT id FROM playlists WHERE name=?", (name,)).fetchone()["id"]
    finally:
        con.close()


def add_to_playlist(pid, paths):
    ensure(paths)
    con = connect()
    try:
        pos = con.execute("SELECT COALESCE(MAX(pos), -1) FROM playlist_items WHERE playlist=?", (pid,)).fetchone()[0]
        con.executemany("INSERT INTO playlist_items(playlist, pos, path) VALUES (?,?,?)",
                        [(pid, pos + 1 + i, p) for i, p in enumerate(paths)])
        con.commit()
    finally:
        con.close()


def remove_from_playlist(pid, paths):
    con = connect()
    try:
        con.executemany("DELETE FROM playlist_items WHERE playlist=? AND path=?", [(pid, p) for p in paths])
        con.commit()
    finally:
        con.close()


def rename_playlist(pid, name):
    con = connect()
    try:
        con.execute("UPDATE playlists SET name=? WHERE id=?", (name, pid))
        con.commit()
    finally:
        con.close()


def delete_playlist(pid):
    con = connect()
    try:
        con.execute("DELETE FROM playlist_items WHERE playlist=?", (pid,))
        con.execute("DELETE FROM playlists WHERE id=?", (pid,))
        con.commit()
    finally:
        con.close()


# --------------------------------------------------------------- smart playlists (rules -> SQL)
# field: (type, SQL expression). Only these expressions ever reach SQL; values always go in as parameters.
SMART_FIELDS = {
    "title": ("text", "title"), "artist": ("text", "artist"), "album": ("text", "album"),
    "albumartist": ("text", "albumartist"), "genre": ("text", "genre"), "path": ("text", "path"),
    "format": ("text", "codec"), "year": ("number", "CAST(NULLIF(year,'') AS INTEGER)"), "rating": ("number", "rating"),
    "plays": ("number", "play_count"), "duration": ("number", "(duration/60.0)"), "bitrate": ("number", "bitrate"),
    "added": ("date", "added"), "last_played": ("date", "last_played"), "favourite": ("bool", "favourite"),
    "has_cover": ("bool", "has_cover"), "has_lyrics": ("bool", "has_lyrics"), "kind": ("kind", "kind"),
}
SMART_OPS = {
    "text": ["contains", "not_contains", "is", "is_not", "starts"],
    "number": ["eq", "ne", "gt", "lt", "ge", "le"],
    "date": ["within", "not_within"],
    "bool": ["yes", "no"],
    "kind": ["music", "video"],
}
SMART_ORDERS = {
    "random": "RANDOM()", "most_played": "play_count DESC, last_played DESC", "least_played": "play_count, lower(title)",
    "recently_added": "added DESC", "recently_played": "last_played DESC", "rating": "rating DESC, play_count DESC",
    "title": "lower(title)", "artist": DEFAULT_ORDER,
}
_NUM_OPS = {"eq": "=", "ne": "<>", "gt": ">", "lt": "<", "ge": ">=", "le": "<="}


def _esc_like(text):
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def smart_sql(spec):
    """spec = {"match": "all"|"any", "rules": [{"field", "op", "value"}], "limit": int, "order": key}
    -> (where, params, order, limit)"""
    parts, params = [], []
    for rule in spec.get("rules", []):
        field = SMART_FIELDS.get(rule.get("field"))
        if not field:
            continue
        typ, col = field
        op = rule.get("op")
        val = str(rule.get("value", "")).strip()
        if typ == "text":
            low = val.lower()
            if op == "contains":
                parts.append(f"lower(COALESCE({col},'')) LIKE ? ESCAPE '\\'")
                params.append(f"%{_esc_like(low)}%")
            elif op == "not_contains":
                parts.append(f"lower(COALESCE({col},'')) NOT LIKE ? ESCAPE '\\'")
                params.append(f"%{_esc_like(low)}%")
            elif op == "is":
                parts.append(f"lower(COALESCE({col},''))=?")
                params.append(low)
            elif op == "is_not":
                parts.append(f"lower(COALESCE({col},''))<>?")
                params.append(low)
            elif op == "starts":
                parts.append(f"lower(COALESCE({col},'')) LIKE ? ESCAPE '\\'")
                params.append(f"{_esc_like(low)}%")
        elif typ == "number" and op in _NUM_OPS:
            try:
                num = float(val.replace(",", "."))
            except ValueError:
                continue
            parts.append(f"COALESCE({col},0) {_NUM_OPS[op]} ?")
            params.append(num)
        elif typ == "date" and op in ("within", "not_within"):
            try:
                days = float(val.replace(",", "."))
            except ValueError:
                continue
            if op == "within":
                parts.append(f"{col} > 0 AND {col} > strftime('%s','now') - ?")
            else:
                parts.append(f"COALESCE({col},0) <= strftime('%s','now') - ?")
            params.append(days * 86400)
        elif typ == "bool" and op in ("yes", "no"):
            parts.append(f"COALESCE({col},0)={1 if op == 'yes' else 0}")
        elif typ == "kind" and op in ("music", "video"):
            parts.append(f"{col}=?")
            params.append("audio" if op == "music" else "video")
    joiner = " OR " if spec.get("match") == "any" else " AND "
    where = joiner.join(f"({p})" for p in parts) if parts else "1=1"
    order = SMART_ORDERS.get(spec.get("order"), DEFAULT_ORDER)
    try:
        limit = max(0, int(spec.get("limit") or 0))
    except (TypeError, ValueError):
        limit = 0
    return where, params, order, limit


def smart_playlists():
    con = connect()
    try:
        return [(r["id"], r["name"], json.loads(r["spec"] or "{}")) for r in
                con.execute("SELECT id, name, spec FROM smart_playlists ORDER BY lower(name)")]
    finally:
        con.close()


def get_smart(sid):
    con = connect()
    try:
        r = con.execute("SELECT id, name, spec FROM smart_playlists WHERE id=?", (sid,)).fetchone()
        return (r["id"], r["name"], json.loads(r["spec"] or "{}")) if r else None
    finally:
        con.close()


def save_smart(sid, name, spec):
    con = connect()
    try:
        if sid:
            con.execute("UPDATE smart_playlists SET name=?, spec=? WHERE id=?", (name, json.dumps(spec), sid))
        else:
            cur = con.execute("INSERT INTO smart_playlists(name, spec, created) VALUES (?,?,?)",
                              (name, json.dumps(spec), time.time()))
            sid = cur.lastrowid
        con.commit()
        return sid
    finally:
        con.close()


def delete_smart(sid):
    con = connect()
    try:
        con.execute("DELETE FROM smart_playlists WHERE id=?", (sid,))
        con.commit()
    finally:
        con.close()


def smart_count(spec):
    where, params, _order, limit = smart_sql(spec)
    con = connect()
    try:
        n = con.execute(f"SELECT COUNT(*) FROM tracks WHERE hidden=0 AND ({where})", params).fetchone()[0]
        return min(n, limit) if limit else n
    finally:
        con.close()


# --------------------------------------------------------------- statistics
def statistics():
    con = connect()
    try:
        s = dict(con.execute(
            "SELECT COUNT(*) tracks, SUM(kind='audio') music, SUM(kind='video') videos, SUM(size) size, "
            "SUM(duration) duration, SUM(play_count) plays, "
            "COUNT(DISTINCT CASE WHEN album_key<>'' THEN album_key END) albums, "
            "COUNT(DISTINCT CASE WHEN kind='audio' AND COALESCE(NULLIF(albumartist,''), artist)<>'' "
            "THEN lower(COALESCE(NULLIF(albumartist,''), artist)) END) artists "
            "FROM tracks WHERE hidden=0").fetchone())
        s = {k: (v or 0) for k, v in s.items()}
        s["listened"] = con.execute("SELECT COALESCE(SUM(seconds),0) FROM listens").fetchone()[0]
        s["top_artists"] = [(r["who"], r["plays"]) for r in con.execute(
            "SELECT COALESCE(NULLIF(albumartist,''), artist) who, SUM(play_count) plays FROM tracks "
            "WHERE hidden=0 AND kind='audio' AND play_count>0 AND COALESCE(NULLIF(albumartist,''), artist)<>'' "
            "GROUP BY lower(who) ORDER BY plays DESC LIMIT 10")]
        s["top_tracks"] = [(f'{r["artist"]} - {r["title"]}' if r["artist"] else r["title"], r["play_count"]) for r in
                           con.execute("SELECT artist, title, play_count FROM tracks WHERE hidden=0 AND play_count>0 "
                                       "ORDER BY play_count DESC, last_played DESC LIMIT 10")]
        s["top_albums"] = [(r["album"], r["plays"]) for r in con.execute(
            "SELECT MAX(album) album, SUM(play_count) plays FROM tracks WHERE hidden=0 AND album_key<>'' "
            "AND play_count>0 GROUP BY album_key ORDER BY plays DESC LIMIT 10")]
        s["top_genres"] = [(r["genre"], r["plays"]) for r in con.execute(
            "SELECT genre, SUM(play_count) plays FROM tracks WHERE hidden=0 AND genre<>'' AND play_count>0 "
            "GROUP BY lower(genre) ORDER BY plays DESC LIMIT 8")]
        months = []
        now = time.localtime()
        y, m = now.tm_year, now.tm_mon
        for _ in range(12):
            months.append((y, m))
            m -= 1
            if m == 0:
                y, m = y - 1, 12
        months.reverse()
        per = {(int(r["y"]), int(r["m"])): r["s"] for r in con.execute(
            "SELECT strftime('%Y', ts, 'unixepoch', 'localtime') y, strftime('%m', ts, 'unixepoch', 'localtime') m, "
            "SUM(seconds) s FROM listens WHERE ts > strftime('%s','now') - 400*86400 GROUP BY y, m")}
        s["months"] = [(y, m, per.get((y, m), 0) or 0) for y, m in months]
        first = con.execute("SELECT MIN(ts) FROM listens").fetchone()[0]
        s["history_since"] = first or 0
        return s
    finally:
        con.close()


# --------------------------------------------------------------- backup / restore
BACKUP_EXT = ".cmbackup"


def backup(dest, settings_path=None):
    """One zip file with the library database (ratings, play counts, playlists, smart playlists, history)
    and the settings."""
    tmpdir = tempfile.mkdtemp(prefix="claudius-backup-")
    try:
        copy = os.path.join(tmpdir, "library.db")
        src = connect()
        dst = sqlite3.connect(copy)
        with dst:
            src.backup(dst)
        dst.close()
        src.close()
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(copy, "library.db")
            if settings_path and os.path.isfile(settings_path):
                z.write(settings_path, "settings.json")
            z.writestr("manifest.json", json.dumps({"app": APP_NAME, "version": APP_VERSION, "created": time.time(),
                                                    "format": 1}, indent=1))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


class BackupError(Exception):
    pass


def read_backup_info(src):
    try:
        with zipfile.ZipFile(src) as z:
            names = set(z.namelist())
            if "library.db" not in names or "manifest.json" not in names:
                raise BackupError("not a Claudius Multimedia backup")
            manifest = json.loads(z.read("manifest.json").decode("utf-8"))
            if manifest.get("app") != APP_NAME:
                raise BackupError("not a Claudius Multimedia backup")
            return manifest
    except (zipfile.BadZipFile, OSError, ValueError) as e:
        raise BackupError(str(e)) from e


def restore(src):
    """Replace the library with the backup. The current library is first saved next to it as
    library-before-restore-<date>.db. Returns the settings stored in the backup (dict, may be empty)."""
    read_backup_info(src)
    tmpdir = tempfile.mkdtemp(prefix="claudius-restore-")
    try:
        with zipfile.ZipFile(src) as z:
            z.extract("library.db", tmpdir)
            settings_data = {}
            if "settings.json" in z.namelist():
                try:
                    settings_data = json.loads(z.read("settings.json").decode("utf-8"))
                except ValueError:
                    settings_data = {}
        new_db = os.path.join(tmpdir, "library.db")
        test = sqlite3.connect(new_db)
        try:
            test.execute("SELECT COUNT(*) FROM tracks").fetchone()
        except sqlite3.DatabaseError as e:
            raise BackupError(str(e)) from e
        finally:
            test.close()
        stamp = time.strftime("%Y%m%d-%H%M%S")
        keep = os.path.join(data_dir(), f"library-before-restore-{stamp}.db")
        cur = connect()
        saved = sqlite3.connect(keep)
        with saved:
            cur.backup(saved)
        saved.close()
        cur.close()
        srcc = sqlite3.connect(new_db)
        dstc = sqlite3.connect(db_path())
        with dstc:
            srcc.backup(dstc)
        srcc.close()
        dstc.close()
        forget_connection_cache()
        connect().close()
        return settings_data if isinstance(settings_data, dict) else {}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# --------------------------------------------------------------- thumbnails (disk cache)
def thumb_path(key):
    folder = os.path.join(data_dir(), "covers")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, hashlib.sha1(key.encode("utf-8", "replace")).hexdigest() + ".jpg")


def forget_thumb(key):
    try:
        os.remove(thumb_path(key))
    except OSError:
        pass


def video_thumb_path(path, mtime=0):
    return thumb_path(f"video|{path}|{int(mtime or 0)}")
