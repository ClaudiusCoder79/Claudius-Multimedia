"""Claudius Multimedia - version, folders, settings and translations."""
import json
import os
import sys

APP_NAME = "Claudius Multimedia"
APP_VERSION = "1.1.0"
APP_AUTHORS = "Michal Czapla & Claude AI"
APP_URL = "https://github.com/ClaudiusCoder79/Claudius-Multimedia"
USER_AGENT = f"ClaudiusMultimedia/{APP_VERSION} ( {APP_URL} )"

AUDIO_EXT = {".mp3", ".flac", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".wav", ".wma", ".aiff", ".aif",
             ".ape", ".wv", ".mka", ".ac3", ".dts", ".mpc", ".m4b", ".alac"}
VIDEO_EXT = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm", ".m4v", ".mpg", ".mpeg", ".ts", ".m2ts", ".mts",
             ".flv", ".3gp", ".ogv", ".vob", ".divx", ".asf"}
PLAYLIST_EXT = {".m3u", ".m3u8", ".pls"}
SUBTITLE_EXT = {".srt", ".vtt"}
MEDIA_EXT = AUDIO_EXT | VIDEO_EXT


def is_media(path):
    return os.path.splitext(path)[1].lower() in MEDIA_EXT


def is_video(path):
    return os.path.splitext(path)[1].lower() in VIDEO_EXT


def is_url(text):
    return "://" in text[:12]


def resource_dir():
    """Folder with the program's own files (lang\\, splash.png) - also inside the PyInstaller build."""
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


def data_dir():
    """Per-user folder for settings, library database and cover cache."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    path = os.path.join(base, APP_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def fmt_time(seconds):
    seconds = int(max(0, seconds or 0))
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


# ---------------------------------------------------------------- settings
DEFAULTS = {
    "theme": "system",            # system / light / dark
    "accent": "#2563eb",
    "language": "",               # empty = take it from Windows the first time
    "volume": 72,
    "muted": False,
    "rate": 1.0,
    "shuffle": False,
    "repeat": "off",              # off / all / one
    "library_folders": [],
    "scan_on_start": True,
    "online": True,               # covers / lyrics / MusicBrainz lookups
    "auto_lyrics": True,          # fetch lyrics for the playing track when it has none
    "save_lrc_file": True,
    "embed_lyrics": True,
    "lyrics_font": 13,
    "show_sidebar": True,
    "show_right": True,
    "remember_queue": True,
    "queue": [],
    "queue_index": -1,
    "geometry": "",
    "always_on_top": False,
    "snapshot_dir": "",
    # 1.1 - library
    "watch_folders": True,        # notice new / changed files in the library folders by itself
    "resume": True,               # continue videos and long recordings where they were stopped
    "album_view": "strip",        # strip (one row above the tracks) / grid (full page of covers)
    "tile_size": 124,
    "album_sort": "artist",       # artist / title / year / added / plays
    "browse": "albums",           # artists / albums / genres / folders / tracks
    "table_header": "",           # track table columns: order, widths, hidden
}


class Settings(dict):
    def __init__(self):
        super().__init__(DEFAULTS)
        self.path = os.path.join(data_dir(), "settings.json")
        try:
            with open(self.path, encoding="utf-8") as f:
                stored = json.load(f)
            if isinstance(stored, dict):
                self.update({k: v for k, v in stored.items() if k in DEFAULTS})
        except (OSError, ValueError):
            pass

    def save(self):
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)
        except OSError:
            pass


settings = Settings()

# ---------------------------------------------------------------- translations
LANGUAGES = [("en", "English"), ("pl", "Polski"), ("de", "Deutsch"),
             ("fr", "Français"), ("it", "Italiano"), ("es", "Español")]
_strings = {}
_english = {}
current_language = "en"


def _load_file(code):
    path = os.path.join(resource_dir(), "lang", f"{code}.json")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return {k: v for k, v in data.items() if isinstance(v, str)}
    except (OSError, ValueError):
        return {}


def system_language():
    try:
        from PySide6.QtCore import QLocale
        code = QLocale.system().name()[:2].lower()
    except Exception:
        code = "en"
    return code if code in dict(LANGUAGES) else "en"


def set_language(code):
    global _strings, _english, current_language
    if code not in dict(LANGUAGES):
        code = "en"
    if not _english:
        _english = _load_file("en")
    _strings = _english if code == "en" else _load_file(code)
    current_language = code


def tr(key, **kw):
    text = _strings.get(key) or _english.get(key) or key
    if kw:
        try:
            return text.format(**kw)
        except (KeyError, IndexError, ValueError):
            return text
    return text
