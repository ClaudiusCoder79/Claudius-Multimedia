"""Claudius Multimedia - reading and writing tags, cover art and lyrics (MP3, FLAC, OGG, Opus, M4A/MP4, WAV, AIFF, WMA)."""
import base64
import os

import mutagen
from mutagen.flac import FLAC, Picture
from mutagen.id3 import (APIC, COMM, ID3, TALB, TBPM, TCOM, TCON, TDRC, TIT2, TPE1, TPE2, TPOS, TRCK, USLT,
                         ID3NoHeaderError)
from mutagen.mp4 import MP4, MP4Cover

FIELDS = ["title", "artist", "albumartist", "album", "year", "genre", "track", "disc", "composer", "bpm", "comment"]

ID3_FRAMES = {"title": TIT2, "artist": TPE1, "albumartist": TPE2, "album": TALB, "year": TDRC, "genre": TCON,
              "track": TRCK, "disc": TPOS, "composer": TCOM, "bpm": TBPM}
VORBIS_KEYS = {"title": "title", "artist": "artist", "albumartist": "albumartist", "album": "album", "year": "date",
               "genre": "genre", "track": "tracknumber", "disc": "discnumber", "composer": "composer", "bpm": "bpm",
               "comment": "comment"}
MP4_KEYS = {"title": "\xa9nam", "artist": "\xa9ART", "albumartist": "aART", "album": "\xa9alb", "year": "\xa9day",
            "genre": "\xa9gen", "composer": "\xa9wrt", "comment": "\xa9cmt"}
APE_KEYS = {"title": "Title", "artist": "Artist", "albumartist": "Album Artist", "album": "Album", "year": "Year",
            "genre": "Genre", "track": "Track", "disc": "Disc", "composer": "Composer", "bpm": "BPM", "comment": "Comment"}
ASF_KEYS = {"title": "Title", "artist": "Author", "albumartist": "WM/AlbumArtist", "album": "WM/AlbumTitle",
            "year": "WM/Year", "genre": "WM/Genre", "track": "WM/TrackNumber", "composer": "WM/Composer",
            "comment": "Description", "bpm": "WM/BeatsPerMinute"}


def _open(path):
    try:
        return mutagen.File(path)
    except Exception:
        return None


def _family(f):
    if f is None:
        return None
    name = type(f).__name__
    if isinstance(f, MP4):
        return "mp4"
    if name == "ASF":
        return "asf"
    if isinstance(getattr(f, "tags", None), ID3) or name in ("MP3", "WAVE", "AIFF", "TrueAudio", "EasyMP3"):
        return "id3"
    if name in ("FLAC", "OggVorbis", "OggOpus", "OggFLAC", "OggSpeex", "APEv2File", "MonkeysAudio", "WavPack", "Musepack"):
        return "vorbis" if name.startswith(("FLAC", "Ogg")) else "ape"
    return None


def can_write(path):
    return _family(_open(path)) in ("id3", "vorbis", "mp4", "ape")


def _first(value):
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        value = value[0] if value else ""
    return str(value).strip()


def read(path):
    """Return a dict with the tag fields plus technical info, lyrics and cover flags."""
    info = {k: "" for k in FIELDS}
    info.update(lyrics="", has_cover=False, duration=0.0, bitrate=0, samplerate=0, bits=0, channels=0,
                codec=os.path.splitext(path)[1].lstrip(".").upper(), writable=False)
    f = _open(path)
    if f is None:
        return info
    fam = _family(f)
    info["writable"] = fam in ("id3", "vorbis", "mp4", "ape")
    i = getattr(f, "info", None)
    if i is not None:
        info["duration"] = float(getattr(i, "length", 0) or 0)
        info["bitrate"] = int(getattr(i, "bitrate", 0) or 0) // 1000
        info["samplerate"] = int(getattr(i, "sample_rate", 0) or 0)
        info["bits"] = int(getattr(i, "bits_per_sample", 0) or 0)
        info["channels"] = int(getattr(i, "channels", 0) or 0)
        codec = getattr(i, "codec", None)
        if isinstance(codec, str) and codec:
            info["codec"] = {"mp4a.40.2": "AAC", "alac": "ALAC"}.get(codec, codec.upper())
    t = f.tags
    if t is None:
        return info
    try:
        if fam == "id3":
            for key, frame in ID3_FRAMES.items():
                fr = t.get(frame.__name__)
                if fr is not None:
                    info[key] = _first(fr.text)
            comms = t.getall("COMM")
            info["comment"] = _first(next((c.text for c in comms if c.desc == ""), comms[0].text if comms else ""))
            uslt = t.getall("USLT")
            if uslt:
                info["lyrics"] = uslt[0].text
            info["has_cover"] = bool(t.getall("APIC"))
        elif fam in ("vorbis", "ape"):
            lower = {k.lower(): v for k, v in t.items()}
            keymap = VORBIS_KEYS if fam == "vorbis" else {k: v.lower() for k, v in APE_KEYS.items()}
            for key, vk in keymap.items():
                if vk in lower:
                    info[key] = _first(lower[vk])
            if not info["year"] and "year" in lower:
                info["year"] = _first(lower["year"])
            for lk in ("lyrics", "unsyncedlyrics", "unsynced lyrics"):
                if lk in lower:
                    val = lower[lk]
                    info["lyrics"] = "\n".join(map(str, val)) if isinstance(val, list) else str(val)
                    break
            info["has_cover"] = bool(getattr(f, "pictures", None)) or "metadata_block_picture" in lower \
                or "cover art (front)" in lower
        elif fam == "mp4":
            for key, mk in MP4_KEYS.items():
                if mk in t:
                    info[key] = _first(t[mk])
            if "trkn" in t and t["trkn"]:
                n, tot = t["trkn"][0]
                info["track"] = f"{n}/{tot}" if tot else str(n or "")
            if "disk" in t and t["disk"]:
                n, tot = t["disk"][0]
                info["disc"] = f"{n}/{tot}" if tot else str(n or "")
            if "tmpo" in t and t["tmpo"]:
                info["bpm"] = str(t["tmpo"][0])
            if "\xa9lyr" in t:
                info["lyrics"] = _first(t["\xa9lyr"])
            info["has_cover"] = bool(t.get("covr"))
        elif fam == "asf":
            for key, ak in ASF_KEYS.items():
                if ak in t:
                    info[key] = _first(t[ak])
            if "WM/Lyrics" in t:
                info["lyrics"] = _first(t["WM/Lyrics"])
            info["has_cover"] = "WM/Picture" in t
    except Exception:
        pass
    if info["year"][:4].isdigit():
        info["year"] = info["year"][:4]
    return info


def write(path, values, cover=None, lyrics=None):
    """Save tag values. `values` may hold only some fields. cover: None = keep, b"" = remove, bytes = set.
    lyrics: None = keep, "" = remove, str = set."""
    f = _open(path)
    fam = _family(f)
    if fam is None:
        raise ValueError("This file type cannot be tagged.")
    if fam == "id3":
        _write_id3(path, f, values, cover, lyrics)
    elif fam in ("vorbis", "ape"):
        _write_vorbis(f, fam, values, cover, lyrics)
    elif fam == "mp4":
        _write_mp4(f, values, cover, lyrics)
    else:
        raise ValueError("This file type cannot be tagged.")


def _mime(data):
    return "image/png" if data[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"


def _write_id3(path, f, values, cover, lyrics):
    if f.tags is None:
        try:
            f.add_tags()
        except Exception:
            pass
    t = f.tags
    if t is None:
        try:
            t = ID3(path)
        except ID3NoHeaderError:
            t = ID3()
    for key, frame in ID3_FRAMES.items():
        if key in values:
            t.delall(frame.__name__)
            if values[key]:
                t.add(frame(encoding=3, text=[values[key]]))
    if "comment" in values:
        t.delall("COMM")
        if values["comment"]:
            t.add(COMM(encoding=3, lang="eng", desc="", text=[values["comment"]]))
    if lyrics is not None:
        t.delall("USLT")
        if lyrics:
            t.add(USLT(encoding=3, lang="eng", desc="", text=lyrics))
    if cover is not None:
        t.delall("APIC")
        if cover:
            t.add(APIC(encoding=3, mime=_mime(cover), type=3, desc="Cover", data=cover))
    if f.tags is t:
        f.save(v2_version=4) if type(f).__name__ == "MP3" else f.save()
    else:
        t.save(path, v2_version=4)


def _write_vorbis(f, fam, values, cover, lyrics):
    if f.tags is None:
        f.add_tags()
    t = f.tags
    existing = {k.lower(): k for k in t.keys()}
    keymap = VORBIS_KEYS if fam == "vorbis" else APE_KEYS
    for key, vk in keymap.items():
        if key in values:
            real = existing.get(vk.lower())
            if real is not None:
                del t[real]
            if values[key]:
                t[vk] = [values[key]] if fam == "vorbis" else values[key]
    if lyrics is not None:
        for lk in ("lyrics", "unsyncedlyrics"):
            if lk in existing:
                del t[existing[lk]]
        if lyrics:
            t["lyrics" if fam == "vorbis" else "Lyrics"] = [lyrics] if fam == "vorbis" else lyrics
    if cover is not None and fam == "vorbis":
        pic = None
        if cover:
            pic = Picture()
            pic.type, pic.mime, pic.desc, pic.data = 3, _mime(cover), "Cover", cover
            try:
                from PySide6.QtGui import QImage
                img = QImage.fromData(cover)
                pic.width, pic.height, pic.depth = img.width(), img.height(), 24
            except Exception:
                pass
        if isinstance(f, FLAC):
            f.clear_pictures()
            if pic:
                f.add_picture(pic)
        else:
            if "metadata_block_picture" in existing:
                del t[existing["metadata_block_picture"]]
            if pic:
                t["metadata_block_picture"] = [base64.b64encode(pic.write()).decode("ascii")]
    f.save()


def _num_pair(text):
    a, _, b = str(text).partition("/")
    try:
        n = int(a.strip() or 0)
    except ValueError:
        n = 0
    try:
        tot = int(b.strip() or 0)
    except ValueError:
        tot = 0
    return n, tot


def _write_mp4(f, values, cover, lyrics):
    if f.tags is None:
        f.add_tags()
    t = f.tags
    for key, mk in MP4_KEYS.items():
        if key in values:
            if mk in t:
                del t[mk]
            if values[key]:
                t[mk] = [values[key]]
    for key, mk in (("track", "trkn"), ("disc", "disk")):
        if key in values:
            if mk in t:
                del t[mk]
            n, tot = _num_pair(values[key])
            if n:
                t[mk] = [(n, tot)]
    if "bpm" in values:
        if "tmpo" in t:
            del t["tmpo"]
        try:
            if values["bpm"]:
                t["tmpo"] = [int(float(values["bpm"]))]
        except ValueError:
            pass
    if lyrics is not None:
        if "\xa9lyr" in t:
            del t["\xa9lyr"]
        if lyrics:
            t["\xa9lyr"] = [lyrics]
    if cover is not None:
        if "covr" in t:
            del t["covr"]
        if cover:
            fmt = MP4Cover.FORMAT_PNG if _mime(cover) == "image/png" else MP4Cover.FORMAT_JPEG
            t["covr"] = [MP4Cover(cover, imageformat=fmt)]
    f.save()


COVER_FILES = ("cover", "folder", "front", "album", "albumart", "albumartsmall")


def folder_cover(path):
    folder = os.path.dirname(path)
    try:
        names = os.listdir(folder)
    except OSError:
        return None
    lookup = {n.lower(): n for n in names}
    for base in COVER_FILES:
        for ext in (".jpg", ".jpeg", ".png", ".webp"):
            if base + ext in lookup:
                return os.path.join(folder, lookup[base + ext])
    return None


def cover(path):
    """Embedded front cover (or cover.jpg / folder.jpg next to the file) as bytes, or None."""
    f = _open(path)
    fam = _family(f)
    data = None
    try:
        t = f.tags if f is not None else None
        if t is not None:
            if fam == "id3":
                pics = t.getall("APIC")
                front = [p for p in pics if p.type == 3]
                data = (front or pics)[0].data if pics else None
            elif fam == "vorbis":
                if isinstance(f, FLAC) and f.pictures:
                    front = [p for p in f.pictures if p.type == 3]
                    data = (front or f.pictures)[0].data
                else:
                    lower = {k.lower(): v for k, v in t.items()}
                    if "metadata_block_picture" in lower:
                        data = Picture(base64.b64decode(lower["metadata_block_picture"][0])).data
            elif fam == "mp4" and t.get("covr"):
                data = bytes(t["covr"][0])
            elif fam == "asf" and "WM/Picture" in t:
                raw = t["WM/Picture"][0].value
                # WM/Picture: type(1) size(4) mime(utf16z) desc(utf16z) data
                pos = 5
                for _ in range(2):
                    end = raw.find(b"\x00\x00", pos)
                    while end != -1 and (end - pos) % 2:
                        end = raw.find(b"\x00\x00", end + 1)
                    pos = end + 2
                data = raw[pos:]
            elif fam == "ape":
                lower = {k.lower(): v for k, v in t.items()}
                if "cover art (front)" in lower:
                    raw = lower["cover art (front)"].value
                    data = raw.split(b"\x00", 1)[1] if b"\x00" in raw else raw
    except Exception:
        data = None
    if not data:
        external = folder_cover(path)
        if external:
            try:
                with open(external, "rb") as fh:
                    data = fh.read()
            except OSError:
                data = None
    return data or None


def lrc_path(path):
    return os.path.splitext(path)[0] + ".lrc"


def lyrics(path):
    """Lyrics from a .lrc file next to the track (preferred: it is usually synced) or from the tags."""
    lp = lrc_path(path)
    if os.path.isfile(lp):
        for enc in ("utf-8-sig", "cp1250", "latin-1"):
            try:
                with open(lp, encoding=enc) as fh:
                    return fh.read()
            except (UnicodeDecodeError, OSError):
                continue
    try:
        return read(path).get("lyrics", "")
    except Exception:
        return ""


def save_lyrics(path, text, embed=True, lrc_file=True):
    errors = []
    if lrc_file:
        try:
            with open(lrc_path(path), "w", encoding="utf-8") as fh:
                fh.write(text)
        except OSError as e:
            errors.append(str(e))
    if embed and can_write(path):
        try:
            write(path, {}, lyrics=text)
        except Exception as e:
            errors.append(str(e))
    return errors
