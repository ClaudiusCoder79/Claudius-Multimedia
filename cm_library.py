"""Claudius Multimedia - music & video library (SQLite database in %APPDATA%\\Claudius Multimedia)."""
import hashlib
import os
import sqlite3
import time

import cm_tags
from cm_core import AUDIO_EXT, VIDEO_EXT, data_dir
from cm_parse import title_from_filename

COLUMNS = ["path", "title", "artist", "albumartist", "album", "genre", "year", "track_no", "disc_no", "duration",
           "codec", "bitrate", "samplerate", "bits", "has_cover", "has_lyrics", "rating", "favourite", "play_count",
           "last_played", "added", "mtime", "size", "kind", "folder"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS tracks (
  path TEXT PRIMARY KEY, title TEXT, artist TEXT, albumartist TEXT, album TEXT, genre TEXT, year TEXT,
  track_no INTEGER, disc_no INTEGER, duration REAL, codec TEXT, bitrate INTEGER, samplerate INTEGER, bits INTEGER,
  has_cover INTEGER, has_lyrics INTEGER, rating INTEGER DEFAULT 0, favourite INTEGER DEFAULT 0,
  play_count INTEGER DEFAULT 0, last_played REAL DEFAULT 0, added REAL, mtime REAL, size INTEGER, kind TEXT, folder TEXT);
CREATE INDEX IF NOT EXISTS ix_album ON tracks(album);
CREATE INDEX IF NOT EXISTS ix_artist ON tracks(artist);
CREATE TABLE IF NOT EXISTS playlists (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, created REAL);
CREATE TABLE IF NOT EXISTS playlist_items (playlist INTEGER, pos INTEGER, path TEXT);
"""


def db_path():
    return os.path.join(data_dir(), "library.db")


def connect():
    con = sqlite3.connect(db_path(), timeout=30)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    con.execute("PRAGMA journal_mode=WAL")
    return con


def _int(text):
    try:
        return int(str(text).split("/")[0].strip() or 0)
    except ValueError:
        return 0


def row_from_file(path, st=None):
    st = st or os.stat(path)
    ext = os.path.splitext(path)[1].lower()
    video = ext in VIDEO_EXT
    info = cm_tags.read(path) if (ext in AUDIO_EXT or ext in (".mp4", ".m4v", ".mov")) else {}
    guess = title_from_filename(path)
    title = info.get("title") or guess.get("title") or os.path.splitext(os.path.basename(path))[0]
    lrc = os.path.isfile(cm_tags.lrc_path(path))
    has_cover = bool(info.get("has_cover")) or (not video and cm_tags.folder_cover(path) is not None)
    return {
        "path": path, "title": title, "artist": info.get("artist") or ("" if video else guess.get("artist", "")),
        "albumartist": info.get("albumartist", ""), "album": info.get("album", ""), "genre": info.get("genre", ""),
        "year": info.get("year", ""), "track_no": _int(info.get("track") or guess.get("track", "")),
        "disc_no": _int(info.get("disc", "")), "duration": info.get("duration", 0.0),
        "codec": info.get("codec") or ext.lstrip(".").upper(), "bitrate": info.get("bitrate", 0),
        "samplerate": info.get("samplerate", 0), "bits": info.get("bits", 0),
        "has_cover": int(has_cover), "has_lyrics": int(bool(info.get("lyrics")) or lrc),
        "mtime": st.st_mtime, "size": st.st_size, "kind": "video" if video else "audio",
        "folder": os.path.dirname(path),
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


def scan(folders, progress=None, task=None):
    """Add new / changed media files of the folders and drop entries whose files are gone. Runs on a worker thread."""
    con = connect()
    known = {r["path"]: r["mtime"] for r in con.execute("SELECT path, mtime FROM tracks")}
    found, todo = set(), []
    for folder in folders:
        for root, dirs, files in os.walk(folder):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d.lower() not in ("$recycle.bin", "system volume information")]
            for name in files:
                ext = os.path.splitext(name)[1].lower()
                if ext in AUDIO_EXT or ext in VIDEO_EXT:
                    p = os.path.join(root, name)
                    found.add(p)
                    try:
                        st = os.stat(p)
                    except OSError:
                        continue
                    if known.get(p) != st.st_mtime:
                        todo.append((p, st))
            if task is not None and task.cancelled:
                return {"added": 0, "removed": 0}
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
    norm = [os.path.normcase(os.path.abspath(f)) for f in folders]
    removed = 0
    for p in known:
        inside = any(os.path.normcase(p).startswith(f.rstrip("\\/") + os.sep) for f in norm)
        if p not in found and (inside or not os.path.exists(p)):
            con.execute("DELETE FROM tracks WHERE path=?", (p,))
            removed += 1
    con.commit()
    con.close()
    return {"added": added, "removed": removed}


def remove_folder(folder):
    con = connect()
    prefix = os.path.abspath(folder).rstrip("\\/") + os.sep
    con.execute("DELETE FROM tracks WHERE path LIKE ? ESCAPE '\\'",
                (prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%",))
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
VIEWS = ["music", "videos", "favourites", "recent", "most", "nocover", "nolyrics"]
WHERE = {
    "music": "kind='audio'", "videos": "kind='video'", "favourites": "favourite=1",
    "recent": "added > strftime('%s','now') - 30*86400", "most": "play_count > 0",
    "nocover": "kind='audio' AND has_cover=0", "nolyrics": "kind='audio' AND has_lyrics=0",
}
ORDER = {"recent": "added DESC", "most": "play_count DESC, last_played DESC"}
DEFAULT_ORDER = "lower(COALESCE(NULLIF(albumartist,''), artist)), lower(album), disc_no, track_no, lower(title)"


def query(view="music", search="", artist=None, album=None, genre=None, playlist=None):
    con = connect()
    try:
        params = []
        if playlist is not None:
            sql = ("SELECT t.* FROM playlist_items i JOIN tracks t ON t.path=i.path WHERE i.playlist=?")
            params.append(playlist)
            order = "i.pos"
        else:
            sql = f"SELECT * FROM tracks WHERE {WHERE.get(view, '1=1')}"
            order = ORDER.get(view, DEFAULT_ORDER)
        if artist is not None:
            sql += " AND (artist=? OR albumartist=?)"
            params += [artist, artist]
        if album is not None:
            sql += " AND album=?"
            params.append(album)
        if genre is not None:
            sql += " AND genre=?"
            params.append(genre)
        if search:
            for word in search.split():
                like = f"%{word}%"
                sql += " AND (title LIKE ? OR artist LIKE ? OR album LIKE ? OR genre LIKE ? OR path LIKE ?)"
                params += [like] * 5
        sql += f" ORDER BY {order}"
        if view == "most":
            sql += " LIMIT 200"
        return [dict(r) for r in con.execute(sql, params)]
    finally:
        con.close()


def groups(kind, view="music"):
    """Distinct artists / albums / genres with counts. albums -> (album, artist, count, sample path)."""
    con = connect()
    try:
        where = WHERE.get(view, "kind='audio'")
        if kind == "albums":
            sql = (f"SELECT album, COALESCE(NULLIF(MAX(albumartist),''), MAX(artist)) AS who, COUNT(*) n, MIN(path) p, "
                   f"MAX(year) y FROM tracks WHERE {where} AND album<>'' GROUP BY album ORDER BY lower(who), y, lower(album)")
            return [(r["album"], r["who"] or "", r["n"], r["p"]) for r in con.execute(sql)]
        col = {"artists": "COALESCE(NULLIF(albumartist,''), artist)", "genres": "genre"}[kind]
        sql = f"SELECT {col} AS g, COUNT(*) n FROM tracks WHERE {where} AND {col}<>'' GROUP BY g ORDER BY lower(g)"
        return [(r["g"], r["n"]) for r in con.execute(sql)]
    finally:
        con.close()


def stats():
    con = connect()
    try:
        r = con.execute("SELECT COUNT(*) n, SUM(kind='audio') a, SUM(kind='video') v, COUNT(DISTINCT album) al, "
                        "SUM(size) s, SUM(has_cover) c, SUM(has_lyrics) l FROM tracks").fetchone()
        return {k: (r[k] or 0) for k in ("n", "a", "v", "al", "s", "c", "l")}
    finally:
        con.close()


def counts():
    con = connect()
    try:
        return {v: con.execute(f"SELECT COUNT(*) FROM tracks WHERE {WHERE[v]}").fetchone()[0] for v in VIEWS}
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


def played(path, duration=0):
    con = connect()
    try:
        con.execute("UPDATE tracks SET play_count=play_count+1, last_played=?, "
                    "duration=CASE WHEN duration>0 THEN duration ELSE ? END WHERE path=?", (time.time(), duration, path))
        con.commit()
    finally:
        con.close()


def rename_path(old, new):
    con = connect()
    try:
        con.execute("UPDATE tracks SET path=?, folder=? WHERE path=?", (new, os.path.dirname(new), old))
        con.execute("UPDATE playlist_items SET path=? WHERE path=?", (new, old))
        con.commit()
    finally:
        con.close()


# --------------------------------------------------------------- playlists
def playlists():
    con = connect()
    try:
        return [(r["id"], r["name"], r["n"]) for r in con.execute(
            "SELECT p.id, p.name, (SELECT COUNT(*) FROM playlist_items i WHERE i.playlist=p.id) n FROM playlists p ORDER BY lower(p.name)")]
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


# --------------------------------------------------------------- album cover thumbnails (disk cache)
def thumb_path(key):
    folder = os.path.join(data_dir(), "covers")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, hashlib.sha1(key.encode("utf-8", "replace")).hexdigest() + ".jpg")


def forget_thumb(key):
    try:
        os.remove(thumb_path(key))
    except OSError:
        pass
