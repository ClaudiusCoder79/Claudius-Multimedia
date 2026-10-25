"""Claudius Multimedia - LRC lyrics, SRT/VTT subtitles and M3U/PLS playlists."""
import os
import re
from urllib.parse import unquote, urlparse

_LRC_TIME = re.compile(r"\[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?\]")
_LRC_TAG = re.compile(r"^\[([a-zA-Z]+):(.*)\]\s*$")


def parse_lrc(text):
    """Return (lines, synced). lines = [(milliseconds or None, text)], sorted when synced."""
    lines, offset, synced = [], 0, False
    for raw in (text or "").replace("\r", "").split("\n"):
        stamps = list(_LRC_TIME.finditer(raw))
        if stamps:
            words = _LRC_TIME.sub("", raw).strip()
            words = re.sub(r"<\d{1,3}:\d{1,2}(?:[.:]\d{1,3})?>", "", words).strip()  # enhanced (word) timing
            for m in stamps:
                frac = m.group(3) or "0"
                ms = int(m.group(1)) * 60000 + int(m.group(2)) * 1000 + int(frac.ljust(3, "0")[:3])
                lines.append((ms, words))
            synced = True
            continue
        tag = _LRC_TAG.match(raw.strip())
        if tag:
            if tag.group(1).lower() == "offset":
                try:
                    offset = int(tag.group(2).strip())
                except ValueError:
                    pass
            continue
        lines.append((None, raw.strip()))
    if synced:
        lines = sorted(((ms - offset if ms is not None else 0, t) for ms, t in lines if ms is not None), key=lambda x: x[0])
        lines = [(max(0, ms), t) for ms, t in lines]
    else:
        while lines and not lines[0][1]:
            lines.pop(0)
        while lines and not lines[-1][1]:
            lines.pop()
    return lines, synced


def lrc_index(lines, position_ms):
    """Index of the line that should be highlighted at position_ms (-1 before the first line)."""
    lo, hi, idx = 0, len(lines) - 1, -1
    while lo <= hi:
        mid = (lo + hi) // 2
        if lines[mid][0] <= position_ms:
            idx, lo = mid, mid + 1
        else:
            hi = mid - 1
    return idx


def shift_lrc(text, delta_ms):
    """Move every time stamp of an LRC text by delta_ms."""
    def repl(m):
        frac = m.group(3) or "0"
        ms = int(m.group(1)) * 60000 + int(m.group(2)) * 1000 + int(frac.ljust(3, "0")[:3]) + delta_ms
        ms = max(0, ms)
        return f"[{ms // 60000:02d}:{(ms // 1000) % 60:02d}.{(ms % 1000) // 10:02d}]"
    return _LRC_TIME.sub(repl, text)


_SRT_TIME = re.compile(r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})\s*-->\s*(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})")
_VTT_SHORT = re.compile(r"(?:(\d{1,2}):)?(\d{2}):(\d{2})\.(\d{3})\s*-->\s*(?:(\d{1,2}):)?(\d{2}):(\d{2})\.(\d{3})")


def read_text(path):
    for enc in ("utf-8-sig", "cp1250", "latin-1"):
        try:
            with open(path, encoding=enc) as fh:
                return fh.read()
        except UnicodeDecodeError:
            continue
    return ""


def parse_subtitles(text):
    """SRT or WebVTT -> [(start_ms, end_ms, text)]."""
    cues = []
    blocks = re.split(r"\n\s*\n", (text or "").replace("\r", ""))
    for block in blocks:
        rows = [r for r in block.split("\n") if r.strip() != ""]
        for i, row in enumerate(rows):
            m = _SRT_TIME.search(row)
            if m:
                g = [int(x or 0) for x in m.groups()]
                start = ((g[0] * 60 + g[1]) * 60 + g[2]) * 1000 + int(str(g[3]).ljust(3, "0")[:3])
                end = ((g[4] * 60 + g[5]) * 60 + g[6]) * 1000 + int(str(g[7]).ljust(3, "0")[:3])
            else:
                m = _VTT_SHORT.search(row)
                if not m:
                    continue
                g = [int(x or 0) for x in m.groups()]
                start = ((g[0] * 60 + g[1]) * 60 + g[2]) * 1000 + g[3]
                end = ((g[4] * 60 + g[5]) * 60 + g[6]) * 1000 + g[7]
            body = "\n".join(rows[i + 1:])
            body = re.sub(r"<[^>]+>", "", body)          # <i>, <b>, <font ...>
            body = re.sub(r"\{\\[^}]*\}", "", body)     # {\an8}
            cues.append((start, end, body.strip()))
            break
    cues.sort(key=lambda c: c[0])
    return cues


def subtitle_at(cues, ms):
    for start, end, body in cues:
        if start <= ms < end:
            return body
        if start > ms:
            break
    return ""


def read_playlist(path):
    """M3U/M3U8/PLS -> list of absolute paths or URLs."""
    text = read_text(path)
    base = os.path.dirname(os.path.abspath(path))
    items = []
    if path.lower().endswith(".pls"):
        for line in text.splitlines():
            key, _, value = line.partition("=")
            if key.strip().lower().startswith("file") and value.strip():
                items.append(value.strip())
    else:
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                items.append(line)
    out = []
    for item in items:
        if item.lower().startswith("file://"):
            item = unquote(urlparse(item).path)
            if re.match(r"^/[A-Za-z]:", item):
                item = item[1:]
        if "://" in item[:12]:
            out.append(item)
            continue
        item = item.replace("\\", os.sep) if os.sep != "\\" else item
        out.append(os.path.normpath(item if os.path.isabs(item) else os.path.join(base, item)))
    return out


def write_m3u(path, entries):
    """entries: [(path, title, seconds)]"""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("#EXTM3U\n")
        for p, title, secs in entries:
            fh.write(f"#EXTINF:{int(secs or -1)},{title or os.path.basename(p)}\n{p}\n")


def title_from_filename(path):
    """'03 - Artist - Title.mp3' -> {'track': '3', 'artist': 'Artist', 'title': 'Title'}"""
    name = os.path.splitext(os.path.basename(path))[0].replace("_", " ").strip()
    out = {}
    m = re.match(r"^(\d{1,3})[\s.\-_)]+(.*)$", name)
    if m:
        out["track"] = str(int(m.group(1)))
        name = m.group(2).strip()
    parts = [p.strip() for p in re.split(r"\s+-\s+", name) if p.strip()]
    if len(parts) >= 2:
        out["artist"], out["title"] = parts[0], " - ".join(parts[1:])
    elif parts:
        out["title"] = parts[0]
    return out
