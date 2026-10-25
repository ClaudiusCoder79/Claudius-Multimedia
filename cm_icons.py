"""Claudius Multimedia - glossy ribbon icons and the program logo, drawn from SVG (no image files needed)."""
from functools import lru_cache

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

# 24x24 glyphs, drawn white on the glossy tiles (or in the text colour for flat icons)
GLYPHS = {
    "open": '<path d="M3 7h6l2 2h10v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "folderplus": '<path d="M3 7h6l2 2h10v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M12 12v5M9.5 14.5h5"/>',
    "url": '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
    "disc": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="2.5"/>',
    "play": '<path d="M8 5v14l11-7z" fill="@" stroke="none"/>',
    "pause": '<path d="M7 5h3.5v14H7zM13.5 5H17v14h-3.5z" fill="@" stroke="none"/>',
    "stop": '<rect x="6" y="6" width="12" height="12" rx="1.5" fill="@" stroke="none"/>',
    "prev": '<path d="M6 6h2.4v12H6zM19 6v12L9 12z" fill="@" stroke="none"/>',
    "next": '<path d="M15.6 6H18v12h-2.4zM5 6v12l10-6z" fill="@" stroke="none"/>',
    "volume": '<path d="M4 9h4l5-4v14l-5-4H4z" fill="@"/><path d="M16.5 9a4 4 0 0 1 0 6M19 6.5a8 8 0 0 1 0 11"/>',
    "mute": '<path d="M4 9h4l5-4v14l-5-4H4z" fill="@"/><path d="M16 9l6 6M22 9l-6 6"/>',
    "voldown": '<path d="M4 9h4l5-4v14l-5-4H4z" fill="@"/><path d="M16 12h5"/>',
    "volup": '<path d="M4 9h4l5-4v14l-5-4H4z" fill="@"/><path d="M16 12h5M18.5 9.5v5"/>',
    "eq": '<path d="M6 20v-8M6 8V4M12 20v-4M12 12V4M18 20v-6M18 10V4"/><path d="M4 10h4M10 14h4M16 12h4"/>',
    "sub": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M7 15h4M13 15h4M7 11h10"/>',
    "camera": '<path d="M4 8h3l2-3h6l2 3h3v11H4z"/><circle cx="12" cy="13" r="3.5"/>',
    "aspect": '<rect x="3" y="6" width="18" height="12" rx="2"/><path d="M7 11V9.5h2.5M17 13v1.5h-2.5"/>',
    "full": '<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>',
    "mini": '<rect x="3" y="5" width="18" height="14" rx="2"/><rect x="12" y="12" width="6" height="4.5" fill="@"/>',
    "playlist": '<path d="M4 6h12M4 11h12M4 16h7"/><path d="M15 14v6l5-3z" fill="@"/>',
    "add": '<path d="M12 5v14M5 12h14"/>',
    "remove": '<path d="M5 12h14"/>',
    "trash": '<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/>',
    "scan": '<path d="M20 12a8 8 0 1 1-2.3-5.6"/><path d="M20 4v5h-5"/>',
    "tag": '<path d="M3 12V4h8l10 10-8 8z"/><circle cx="7.5" cy="8" r="1.4"/>',
    "image": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 16l5-5 4 4 3-3 6 6"/><circle cx="15.5" cy="8.5" r="1.5"/>',
    "lyrics": '<path d="M9 18V5l10-2v13"/><circle cx="6.5" cy="18" r="2.5"/><circle cx="16.5" cy="16" r="2.5"/>',
    "search": '<circle cx="11" cy="11" r="6"/><path d="M20 20l-4.5-4.5"/>',
    "convert": '<path d="M4 8h14l-3-3M20 16H6l3 3"/>',
    "gear": '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9 7 7M17 17l2.1 2.1M4.9 19.1 7 17M17 7l2.1-2.1"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.3"/>',
    "globe": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
    "theme": '<circle cx="12" cy="12" r="8"/><path d="M12 4a8 8 0 0 1 0 16z" fill="@"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.4 1.4M17.6 17.6 19 19M5 19l1.4-1.4M17.6 6.4 19 5"/>',
    "moon": '<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/>',
    "shuffle": '<path d="M4 7h3l10 10h3M4 17h3l3-3M14 10l3-3h3M18 5l2 2-2 2M18 15l2 2-2 2"/>',
    "repeat": '<path d="M4 11V9a2 2 0 0 1 2-2h13M16 4l3 3-3 3M20 13v2a2 2 0 0 1-2 2H5M8 20l-3-3 3-3"/>',
    "repeatone": '<path d="M4 11V9a2 2 0 0 1 2-2h13M16 4l3 3-3 3M20 13v2a2 2 0 0 1-2 2H5M8 20l-3-3 3-3"/><path d="M11.5 10.5l1.5-1v5"/>',
    "heart": '<path d="M12 20s-7-4.5-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.5-7 10-7 10z"/>',
    "heartf": '<path d="M12 20s-7-4.5-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.5-7 10-7 10z" fill="@"/>',
    "speed": '<path d="M4.5 18a8.5 8.5 0 1 1 15 0"/><path d="M12 14l4-5"/>',
    "slower": '<path d="M4.5 18a8.5 8.5 0 1 1 15 0"/><path d="M12 14l-4-5"/>',
    "save": '<path d="M5 4h11l3 3v13H5z"/><path d="M8 4v5h7V4M8 20v-6h8v6"/>',
    "undo": '<path d="M9 14 4 9l5-5"/><path d="M4 9h10a6 6 0 0 1 0 12h-3"/>',
    "star": '<path d="M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9z"/>',
    "cloud": '<path d="M7 18a4 4 0 0 1-.5-8A6 6 0 0 1 18 9a4.5 4.5 0 0 1-.5 9z"/><path d="M12 11v6M9.5 14.5 12 17l2.5-2.5"/>',
    "album": '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    "list": '<path d="M8 6h13M8 12h13M8 18h13M3.5 6h.5M3.5 12h.5M3.5 18h.5"/>',
    "grid": '<rect x="4" y="4" width="7" height="7" rx="1"/><rect x="13" y="4" width="7" height="7" rx="1"/><rect x="4" y="13" width="7" height="7" rx="1"/><rect x="13" y="13" width="7" height="7" rx="1"/>',
    "video": '<rect x="3" y="6" width="13" height="12" rx="2"/><path d="M16 10l5-3v10l-5-3z"/>',
    "key": '<circle cx="8" cy="15" r="4"/><path d="M11 12l9-9M17 6l3 3"/>',
    "back10": '<path d="M4 12a8 8 0 1 0 2.3-5.6"/><path d="M4 4v5h5"/><path d="M10 10v5M13 10h2.5v5H13z"/>',
    "fwd10": '<path d="M20 12a8 8 0 1 1-2.3-5.6"/><path d="M20 4v5h-5"/><path d="M9 10v5M12 10h2.5v5H12z"/>',
    "pin": '<path d="M9 4h6l-1 6 3 3H7l3-3zM12 13v7"/>',
    "exit": '<path d="M14 4h5v16h-5M10 8l-4 4 4 4M6 12h9"/>',
    "file": '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4"/>',
    "sort": '<path d="M7 4v16M4 17l3 3 3-3M14 6h7M14 11h5M14 16h3"/>',
    "fontup": '<path d="M4 19 9 5l5 14M6 14h6M18 8v6M15 11h6"/>',
    "fontdown": '<path d="M4 19 9 5l5 14M6 14h6M15 11h6"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "edit": '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="M13 7l4 4"/>',
    "export": '<path d="M12 15V3M8 7l4-4 4 4"/><path d="M4 14v6h16v-6"/>',
    "keyboard": '<rect x="2" y="6" width="20" height="12" rx="2"/><path d="M6 10h.5M10 10h.5M14 10h.5M18 10h.5M7 14h10"/>',
    "lang": '<path d="M4 5h9M8.5 3v2M11 5c-1 4-4 7-7 8M6 9c1.5 2 3.5 3.5 6 4"/><path d="M13 21l4-10 4 10M14.5 17.5h5"/>',
    "sidebar": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16"/>',
    "panel": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M15 4v16"/>',
    "library": '<path d="M4 4v16M8 4v16M12 5l4 15M17 4l3 16"/>',
}

COLORS = {
    "blue": ("#5aa2ff", "#1d5fd8"),
    "green": ("#4fd17a", "#178a3e"),
    "orange": ("#ffc24a", "#e3820b"),
    "purple": ("#c58cff", "#7c2bd6"),
    "teal": ("#66cdf5", "#1b88c6"),
    "red": ("#ff7b7b", "#cc2a2a"),
    "indigo": ("#9aa4ff", "#4b4fd8"),
    "pink": ("#ff8ac6", "#c9237a"),
    "gray": ("#b9c2cf", "#6b7686"),
}


def _glyph(name, colour):
    return GLYPHS.get(name, GLYPHS["info"]).replace("@", colour)


def glossy_svg(glyph, colour="blue", round_=False):
    top, bottom = COLORS.get(colour, COLORS["blue"])
    shape = ('<circle cx="24" cy="24" r="22.5" fill="url(#g)" stroke="#000" stroke-opacity=".22" stroke-width="1"/>'
             if round_ else
             '<rect x="1.5" y="1.5" width="45" height="45" rx="11" fill="url(#g)" stroke="#000" stroke-opacity=".22" stroke-width="1"/>')
    shine = ('<path d="M6 18 A19 19 0 0 1 42 18 Q24 26 6 18Z" fill="url(#h)"/>' if round_ else
             '<path d="M3 14 Q3 3 14 3 H34 Q45 3 45 14 V20 Q24 27 3 20Z" fill="url(#h)"/>')
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48">'
        '<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{top}"/><stop offset="1" stop-color="{bottom}"/></linearGradient>'
        '<linearGradient id="h" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".55"/>'
        '<stop offset="1" stop-color="#fff" stop-opacity=".06"/></linearGradient></defs>'
        f'{shape}{shine}'
        '<g transform="translate(12 12)" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        f'{_glyph(glyph, "#fff")}</g></svg>')


def flat_svg(glyph, colour):
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><g fill="none" '
            f'stroke="{colour}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{_glyph(glyph, colour)}</g></svg>')


LOGO_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
    '<defs><linearGradient id="lg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#5aa8ff"/>'
    '<stop offset="1" stop-color="#1846c4"/></linearGradient>'
    '<linearGradient id="hl" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".55"/>'
    '<stop offset="1" stop-color="#fff" stop-opacity=".05"/></linearGradient></defs>'
    '<rect x="2" y="2" width="60" height="60" rx="15" fill="url(#lg)" stroke="#0f3a9e" stroke-width="1.5"/>'
    '<path d="M4 18 Q4 4 18 4 H46 Q60 4 60 18 V26 Q32 34 4 26Z" fill="url(#hl)"/>'
    '<path d="M44.5 21.5 A15 15 0 1 0 44.5 42.5" fill="none" stroke="#fff" stroke-width="6" stroke-linecap="round"/>'
    '<path d="M28 24.5 L40.5 32 L28 39.5Z" fill="#fff"/>'
    '<circle cx="47.5" cy="32" r="3" fill="#ffc24a"/></svg>')


def render_svg(svg, size, ratio=2.0):
    """Render SVG text into a QPixmap of `size` logical pixels (sharp on high-DPI screens)."""
    px = int(size * ratio)
    img = QImage(px, px, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    QSvgRenderer(QByteArray(svg.encode("utf-8"))).render(p, QRectF(0, 0, px, px))
    p.end()
    pm = QPixmap.fromImage(img)
    pm.setDevicePixelRatio(ratio)
    return pm


@lru_cache(maxsize=512)
def glossy(glyph, colour="blue", size=40, round_=False):
    return QIcon(render_svg(glossy_svg(glyph, colour, round_), size))


@lru_cache(maxsize=512)
def flat(glyph, colour="#6b7584", size=20):
    return QIcon(render_svg(flat_svg(glyph, colour), size))


@lru_cache(maxsize=16)
def logo_pixmap(size=64):
    return render_svg(LOGO_SVG, size)


def logo_icon():
    icon = QIcon()
    for s in (16, 20, 24, 32, 40, 48, 64, 128, 256):
        icon.addPixmap(render_svg(LOGO_SVG, s, 1.0))
    return icon


def placeholder_cover(size, seed_text=""):
    """A soft gradient tile used when a track has no cover art."""
    palettes = [("#ffd27a", "#f0682d", "#5b1f6e"), ("#0f9b8e", "#0b3d6b", "#062033"), ("#009ffd", "#2a2a72", "#14143a"),
                ("#ff9a9e", "#a18cd1", "#5e4b8b"), ("#c9a227", "#5c6b73", "#232526"), ("#5aa8ff", "#1846c4", "#0b1f5c")]
    a, b, c = palettes[sum(map(ord, seed_text or "x")) % len(palettes)]
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs><radialGradient id="r" cx=".3" cy=".3" r=".9">'
           f'<stop offset="0" stop-color="{a}"/><stop offset=".5" stop-color="{b}"/><stop offset="1" stop-color="{c}"/>'
           '</radialGradient></defs><rect width="100" height="100" fill="url(#r)"/>'
           '<g transform="translate(32 32) scale(1.5)" fill="none" stroke="#fff" stroke-opacity=".55" stroke-width="1.6" '
           'stroke-linecap="round" stroke-linejoin="round"><path d="M9 18V5l10-2v13"/><circle cx="6.5" cy="18" r="2.5"/>'
           '<circle cx="16.5" cy="16" r="2.5"/></g></svg>')
    return render_svg(svg, size)
