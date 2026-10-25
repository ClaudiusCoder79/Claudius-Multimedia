"""Claudius Multimedia - building blocks of the main window: header + ribbon, transport bar, video view,
synced lyrics view, track table and album strip."""
import os
import weakref

from PySide6.QtCore import (QAbstractTableModel, QModelIndex, QPointF, QRectF, QSize, Qt, QTimer, Signal)
from PySide6.QtGui import QAction, QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QFrame, QGraphicsPixmapItem, QGraphicsScene,
                               QGraphicsSimpleTextItem, QGraphicsView, QHBoxLayout, QLabel, QLineEdit, QListView,
                               QListWidget, QListWidgetItem, QMenu, QPushButton, QSizePolicy, QSlider, QStackedWidget,
                               QStyle, QTableView, QToolButton, QVBoxLayout, QWidget, QGraphicsItem)

import cm_icons
import cm_theme
from cm_core import fmt_time, tr
from cm_parse import lrc_index, parse_lrc

# ------------------------------------------------------------------ translation registry
_bound = []


def bind(obj, key, method="setText", **kw):
    """Remember that obj.method(tr(key)) must be called again when the language changes."""
    getattr(obj, method)(tr(key, **kw))
    _bound.append((weakref.ref(obj), key, method, kw))
    return obj


def retranslate_all():
    alive = []
    for ref, key, method, kw in _bound:
        obj = ref()
        if obj is None:
            continue
        try:
            getattr(obj, method)(tr(key, **kw))
            alive.append((ref, key, method, kw))
        except RuntimeError:  # the C++ object is gone
            continue
    _bound[:] = alive


def vline():
    f = QFrame()
    f.setObjectName("VSep")
    f.setFixedWidth(1)
    return f


def muted(text=""):
    lab = QLabel(text)
    lab.setObjectName("Muted")
    return lab


# ------------------------------------------------------------------ header + ribbon
class Header(QWidget):
    tabChanged = Signal(str)

    def __init__(self, tabs, quick_actions, parent=None):
        super().__init__(parent)
        self.setObjectName("Header")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(52)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(8)
        logo = QLabel()
        logo.setPixmap(cm_icons.logo_pixmap(28))
        lay.addWidget(logo)
        brand = QLabel("CLAUDIUS")
        brand.setObjectName("Brand")
        lay.addWidget(brand)
        small = QLabel("MULTIMEDIA")
        small.setObjectName("BrandSmall")
        lay.addWidget(small)
        lay.addSpacing(8)
        for act, glyph, colour in quick_actions:
            b = QPushButton()
            b.setObjectName("Round")
            b.setIcon(cm_icons.glossy(glyph, colour, 30, True))
            b.setIconSize(QSize(30, 30))
            b.setFixedSize(32, 32)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(act.trigger)
            b.setToolTip(act.text())
            act.changed.connect(lambda b=b, a=act: b.setToolTip(a.text().replace("&", "")))
            lay.addWidget(b)
        lay.addSpacing(6)
        sep = QFrame()
        sep.setObjectName("QuickSep")
        sep.setFixedSize(1, 28)
        lay.addWidget(sep)
        lay.addSpacing(6)
        self.group = QButtonGroup(self)
        self.buttons = {}
        for key in tabs:
            b = QPushButton()
            b.setObjectName("TabBtn")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            bind(b, "tab." + key)
            b.clicked.connect(lambda _=False, k=key: self.tabChanged.emit(k))
            self.group.addButton(b)
            self.buttons[key] = b
            lay.addWidget(b)
        lay.addStretch(1)
        self.search = QLineEdit()
        self.search.setObjectName("Search")
        self.search.setClearButtonEnabled(True)
        self.search.addAction(cm_icons.flat("search", "#8a93a3", 16), QLineEdit.LeadingPosition)
        bind(self.search, "search.placeholder", "setPlaceholderText")
        lay.addWidget(self.search)

    def select(self, key):
        if key in self.buttons:
            self.buttons[key].setChecked(True)


class RibbonButton(QToolButton):
    def __init__(self, action, menu=None):
        super().__init__()
        self.setObjectName("RibbonBtn")
        self.setDefaultAction(action)
        self.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.setIconSize(QSize(40, 40))
        self.setFixedHeight(70)
        self.setAutoRaise(True)
        self.setCursor(Qt.PointingHandCursor)
        if menu is not None:
            self.setMenu(menu)
            self.setPopupMode(QToolButton.InstantPopup)


class Ribbon(QStackedWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Ribbon")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(100)
        self.pages = {}

    def add_page(self, key, groups, actions, menus):
        page = QWidget()
        lay = QHBoxLayout(page)
        lay.setContentsMargins(6, 6, 6, 0)
        lay.setSpacing(0)
        for gi, (label_key, ids) in enumerate(groups):
            if gi:
                lay.addWidget(vline())
            g = QWidget()
            gl = QVBoxLayout(g)
            gl.setContentsMargins(4, 0, 4, 2)
            gl.setSpacing(0)
            row = QHBoxLayout()
            row.setSpacing(2)
            for aid in ids:
                row.addWidget(RibbonButton(actions[aid], menus.get(aid)))
            gl.addLayout(row)
            gl.addStretch(1)
            lab = QLabel()
            lab.setObjectName("RibbonGroupLabel")
            lab.setAlignment(Qt.AlignHCenter)
            bind(lab, "group." + label_key)
            gl.addWidget(lab)
            lay.addWidget(g)
        lay.addStretch(1)
        self.pages[key] = self.addWidget(page)

    def show_page(self, key):
        if key in self.pages:
            self.setCurrentIndex(self.pages[key])


# ------------------------------------------------------------------ transport bar
class SeekSlider(QSlider):
    """Slider that jumps to the clicked position."""
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.maximum() > self.minimum():
            value = QStyle.sliderValueFromPosition(self.minimum(), self.maximum(), int(e.position().x()), self.width())
            self.setValue(value)
            self.sliderMoved.emit(value)
        super().mousePressEvent(e)


class CoverLabel(QLabel):
    def __init__(self, size, radius=8):
        super().__init__()
        self.size_ = size
        self.radius = radius
        self.setFixedSize(size, size)
        self.set_cover(None)

    def set_cover(self, data, seed=""):
        pm = QPixmap()
        if data:
            pm.loadFromData(data)
        if pm.isNull():
            pm = cm_icons.placeholder_cover(self.size_, seed)
        self.setPixmap(rounded(pm, self.size_, self.radius))


def rounded(pm, size, radius):
    ratio = 2.0
    px = int(size * ratio)
    src = pm.scaled(px, px, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    src.setDevicePixelRatio(1.0)
    out = QPixmap(px, px)
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, px, px), radius * ratio, radius * ratio)
    p.setClipPath(path)
    p.drawPixmap(int((px - src.width()) / 2), int((px - src.height()) / 2), src)
    p.end()
    out.setDevicePixelRatio(ratio)
    return out


class Transport(QWidget):
    def __init__(self, player, actions, parent=None):
        super().__init__(parent)
        self.player = player
        self.setObjectName("Transport")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(80)
        self._dragging = False
        self._playing = False
        self._flat = []
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 6, 14, 6)
        lay.setSpacing(16)

        left = QHBoxLayout()
        left.setSpacing(10)
        self.cover = CoverLabel(52, 6)
        left.addWidget(self.cover)
        txt = QVBoxLayout()
        txt.setSpacing(1)
        txt.addStretch(1)
        self.title = QLabel()
        self.title.setStyleSheet("font-weight:700;")
        self.sub = muted()
        for lab in (self.title, self.sub):
            lab.setMaximumWidth(230)
            lab.setMinimumWidth(60)
        txt.addWidget(self.title)
        txt.addWidget(self.sub)
        txt.addStretch(1)
        left.addLayout(txt)
        self.heart = self._flat_btn(actions["favourite"], "heart")
        left.addWidget(self.heart)
        lw = QWidget()
        lw.setLayout(left)
        lw.setFixedWidth(330)
        lay.addWidget(lw)

        mid = QVBoxLayout()
        mid.setSpacing(4)
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addStretch(1)
        self.shuffle = self._flat_btn(actions["shuffle"], "shuffle")
        self.prev = self._flat_btn(actions["prev"], "prev")
        self.play = QToolButton()
        self.play.setObjectName("PlayBtn")
        self.play.clicked.connect(actions["play"].trigger)
        self.play.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.play.setIconSize(QSize(40, 40))
        self.play.setFixedSize(44, 44)
        self.play.setCursor(Qt.PointingHandCursor)
        self.next = self._flat_btn(actions["next"], "next")
        self.repeat = self._flat_btn(actions["repeat"], "repeat")
        for w in (self.shuffle, self.prev, self.play, self.next, self.repeat):
            row.addWidget(w)
        row.addStretch(1)
        mid.addLayout(row)
        seek = QHBoxLayout()
        self.pos_lab = muted("0:00")
        self.len_lab = muted("0:00")
        for lab in (self.pos_lab, self.len_lab):
            lab.setMinimumWidth(48)
        self.pos_lab.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.slider = SeekSlider(Qt.Horizontal)
        self.slider.setRange(0, 0)
        self.slider.sliderPressed.connect(lambda: setattr(self, "_dragging", True))
        self.slider.sliderReleased.connect(self._released)
        self.slider.sliderMoved.connect(lambda v: self.pos_lab.setText(fmt_time(v / 1000)))
        seek.addWidget(self.pos_lab)
        seek.addWidget(self.slider, 1)
        seek.addWidget(self.len_lab)
        mid.addLayout(seek)
        lay.addLayout(mid, 1)

        right = QHBoxLayout()
        right.setSpacing(6)
        right.addStretch(1)
        self.speed = QToolButton()
        self.speed.setObjectName("Flat")
        self.speed.setPopupMode(QToolButton.InstantPopup)
        self.speed.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.speed.setIconSize(QSize(18, 18))
        right.addWidget(self.speed)
        self.mute = self._flat_btn(actions["mute"], "volume")
        right.addWidget(self.mute)
        self.volume = QSlider(Qt.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setFixedWidth(110)
        self.volume.setValue(player.volume())
        self.volume.valueChanged.connect(self._volume)
        right.addWidget(self.volume)
        self.vol_lab = muted(f"{player.volume()}%")
        self.vol_lab.setFixedWidth(34)
        right.addWidget(self.vol_lab)
        self.restore = self._flat_btn(actions["mini"], "mini")
        self.restore.hide()
        right.addWidget(self.restore)
        rw = QWidget()
        rw.setLayout(right)
        rw.setFixedWidth(330)
        lay.addWidget(rw)
        self.rw, self.lw = rw, lw

        player.positionChanged.connect(self._position)
        player.durationChanged.connect(self._duration)
        self.refresh_icons()

    def _flat_btn(self, action, glyph=None):
        b = QToolButton()
        b.setObjectName("Flat")
        b.setToolButtonStyle(Qt.ToolButtonIconOnly)
        b.setIconSize(QSize(20, 20))
        b.setCursor(Qt.PointingHandCursor)
        b.glyph = glyph
        b.setCheckable(action.isCheckable())
        b.setChecked(action.isChecked())
        b.clicked.connect(lambda _=False, a=action: a.trigger())
        action.toggled.connect(b.setChecked)

        def sync(b=b, a=action):
            b.setToolTip(a.text().replace("&", "") + (f"  ({a.shortcut().toString()})" if not a.shortcut().isEmpty() else ""))
        action.changed.connect(sync)
        sync()
        self._flat.append(b)
        return b

    def refresh_icons(self):
        c = cm_theme.colours()
        for b in self._flat:
            colour = c["accent"] if b.isChecked() and b.glyph not in ("heart", "heartf") else c["muted"]
            if b.glyph in ("heartf",):
                colour = "#e5484d"
            b.setIcon(cm_icons.flat(b.glyph, colour, 20))
        self.speed.setIcon(cm_icons.flat("speed", c["muted"], 18))
        self.play.setIcon(cm_icons.glossy("pause" if self._playing else "play", "blue", 40, True))

    def set_glyph(self, button, glyph):
        button.glyph = glyph
        self.refresh_icons()

    def set_playing(self, playing):
        self._playing = playing
        self.play.setIcon(cm_icons.glossy("pause" if playing else "play", "blue", 40, True))

    def _volume(self, v):
        self.player.set_volume(v)
        self.vol_lab.setText(f"{v}%")

    def _released(self):
        self._dragging = False
        self.player.seek(self.slider.value())

    def _position(self, ms):
        if not self._dragging:
            self.slider.blockSignals(True)
            self.slider.setValue(ms)
            self.slider.blockSignals(False)
            self.pos_lab.setText(fmt_time(ms / 1000))

    def _duration(self, ms):
        self.slider.setRange(0, max(0, ms))
        self.len_lab.setText(fmt_time(ms / 1000) if ms > 0 else "--:--")

    def set_track(self, title, sub, cover, seed):
        fm = QFontMetrics(self.title.font())
        self.title.setText(fm.elidedText(title, Qt.ElideRight, 228))
        self.title.setToolTip(title)
        fm = QFontMetrics(self.sub.font())
        self.sub.setText(fm.elidedText(sub, Qt.ElideRight, 228))
        self.sub.setToolTip(sub)
        self.cover.set_cover(cover, seed)

    def set_mini(self, on):
        self.restore.setVisible(on)
        self.lw.setFixedWidth(210 if on else 330)
        self.rw.setFixedWidth(84 if on else 330)
        for w in (self.speed, self.volume, self.vol_lab, self.shuffle, self.repeat, self.heart, self.pos_lab, self.len_lab):
            w.setVisible(not on)


# ------------------------------------------------------------------ video / now playing view
class VideoView(QGraphicsView):
    doubleClicked = Signal()
    filesDropped = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("VideoView")
        self.scene_ = QGraphicsScene(self)
        self.setScene(self.scene_)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.NoFrame)
        self.setBackgroundBrush(QColor("#000"))
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setAcceptDrops(True)
        self.video = QGraphicsVideoItem()
        self.video.setAspectRatioMode(Qt.KeepAspectRatio)
        self.scene_.addItem(self.video)
        self.cover = QGraphicsPixmapItem()
        self.cover.setTransformationMode(Qt.SmoothTransformation)
        self.scene_.addItem(self.cover)
        self.caption = QGraphicsSimpleTextItem()
        self.caption.setBrush(QColor("#ffffff"))
        self.scene_.addItem(self.caption)
        self.caption2 = QGraphicsSimpleTextItem()
        self.caption2.setBrush(QColor("#b8c0cc"))
        self.scene_.addItem(self.caption2)
        self.sub_bg = self.scene_.addRect(QRectF(), QPen(Qt.NoPen), QColor(0, 0, 0, 150))
        self.sub_text = SubtitleItem()
        self.scene_.addItem(self.sub_text)
        self.osd = QGraphicsSimpleTextItem()
        self.osd.setBrush(QColor("#ffffff"))
        f = QFont()
        f.setPointSize(14)
        f.setBold(True)
        self.osd.setFont(f)
        self.osd_bg = self.scene_.addRect(QRectF(), QPen(Qt.NoPen), QColor(0, 0, 0, 140))
        self.osd_bg.setZValue(5)
        self.osd.setZValue(6)
        self.osd_timer = QTimer(self, singleShot=True, interval=1400, timeout=self._hide_osd)
        self._hide_osd()
        self.sub_bg.setZValue(3)
        self.sub_text.setZValue(4)
        self._cover_pm = None
        self._mode_video = False
        self.video.nativeSizeChanged.connect(lambda _s: self._layout())
        self.set_subtitle("")

    def set_audio_mode(self, cover_pm, title, sub):
        self._mode_video = False
        self.video.hide()
        self._cover_pm = cover_pm
        self.cover.show()
        f = QFont()
        f.setPointSize(18)
        f.setBold(True)
        self.caption.setFont(f)
        self.caption.setText(title)
        f2 = QFont()
        f2.setPointSize(12)
        self.caption2.setFont(f2)
        self.caption2.setText(sub)
        self.caption.show()
        self.caption2.show()
        self._layout()

    def set_video_mode(self):
        self._mode_video = True
        self.video.show()
        self.cover.hide()
        self.caption.hide()
        self.caption2.hide()
        self._layout()

    def set_subtitle(self, text):
        self.sub_text.set_text(text)
        self.sub_text.setVisible(bool(text))
        self.sub_bg.setVisible(False)
        self._layout_sub()

    def show_osd(self, text):
        self.osd.setText(text)
        r = self.osd.boundingRect()
        self.osd.setPos(24, 20)
        self.osd_bg.setRect(QRectF(14, 12, r.width() + 20, r.height() + 16))
        self.osd.show()
        self.osd_bg.show()
        self.osd_timer.start()

    def _hide_osd(self):
        self.osd.hide()
        self.osd_bg.hide()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._layout()

    def _layout(self):
        w, h = max(1, self.viewport().width()), max(1, self.viewport().height())
        self.scene_.setSceneRect(0, 0, w, h)
        self.video.setPos(0, 0)
        self.video.setSize(QSize(w, h).toSizeF())
        if self._cover_pm is not None and not self._mode_video:
            side = int(min(w * 0.55, h * 0.62, 520))
            side = max(side, 60)
            pm = rounded(self._cover_pm, side, 14)
            ratio = pm.devicePixelRatio()
            self.cover.setPixmap(pm)
            self.cover.setScale(1.0)
            total = side + 70
            top = max(10, (h - total) / 2)
            self.cover.setPos((w - pm.width() / ratio) / 2, top)
            r1 = self.caption.boundingRect()
            r2 = self.caption2.boundingRect()
            self.caption.setPos((w - r1.width()) / 2, top + side + 16)
            self.caption2.setPos((w - r2.width()) / 2, top + side + 16 + r1.height() + 2)
        self._layout_sub()

    def _layout_sub(self):
        w, h = max(1, self.viewport().width()), max(1, self.viewport().height())
        self.sub_text.set_width(w * 0.9)
        r = self.sub_text.boundingRect()
        self.sub_text.setPos((w - r.width()) / 2, h - r.height() - max(24, h * 0.06))

    def mouseDoubleClickEvent(self, e):
        self.doubleClicked.emit()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        self.filesDropped.emit([u.toLocalFile() or u.toString() for u in e.mimeData().urls()])


class SubtitleItem(QGraphicsItem):
    """Outlined white subtitle text, wrapped and centred (like PotPlayer / VLC)."""
    def __init__(self):
        super().__init__()
        self.text = ""
        self.width = 800
        self.font = QFont()
        self.font.setPointSize(22)
        self.font.setBold(True)
        self._lines = []
        self._rect = QRectF()

    def set_width(self, w):
        self.prepareGeometryChange()
        self.width = max(100, w)
        size = max(14, min(34, int(self.width / 38)))
        self.font.setPointSize(size)
        self._relayout()

    def set_text(self, text):
        self.prepareGeometryChange()
        self.text = text or ""
        self._relayout()

    def _relayout(self):
        fm = QFontMetrics(self.font)
        lines = []
        for para in self.text.split("\n"):
            words, cur = para.split(" "), ""
            for wd in words:
                trial = (cur + " " + wd).strip()
                if fm.horizontalAdvance(trial) > self.width and cur:
                    lines.append(cur)
                    cur = wd
                else:
                    cur = trial
            lines.append(cur)
        self._lines = lines
        widest = max([fm.horizontalAdvance(x) for x in lines] + [1])
        self._rect = QRectF(0, 0, widest + 8, fm.height() * len(lines) + 8)
        self.update()

    def boundingRect(self):
        return self._rect

    def paint(self, p, _opt, _w=None):
        if not self.text:
            return
        fm = QFontMetrics(self.font)
        p.setRenderHint(QPainter.Antialiasing)
        for i, line in enumerate(self._lines):
            x = (self._rect.width() - fm.horizontalAdvance(line)) / 2
            y = 4 + fm.ascent() + i * fm.height()
            path = QPainterPath()
            path.addText(QPointF(x, y), self.font, line)
            p.strokePath(path, QPen(QColor(0, 0, 0, 230), max(3, self.font.pointSize() / 5), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.fillPath(path, QColor("#ffffff"))


# ------------------------------------------------------------------ synced lyrics
class LyricsView(QListWidget):
    seekRequested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Lyrics")
        self.setWordWrap(True)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setFocusPolicy(Qt.NoFocus)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.lines, self.synced, self.current = [], False, -1
        self.offset = 0
        self.font_size = 13
        self.itemClicked.connect(self._clicked)

    def set_font_size(self, size):
        self.font_size = max(9, min(28, size))
        self._restyle()

    def set_lyrics(self, text, placeholder=""):
        self.clear()
        self.current = -1
        self.offset = 0
        self.lines, self.synced = parse_lrc(text) if text else ([], False)
        if not self.lines:
            it = QListWidgetItem(placeholder)
            it.setFlags(Qt.NoItemFlags)
            self.addItem(it)
        for ms, line in self.lines:
            it = QListWidgetItem(line or "♪")
            if not self.synced:
                it.setFlags(Qt.ItemIsEnabled)
            self.addItem(it)
        self._restyle()
        self.scrollToTop()

    def _restyle(self):
        c = cm_theme.colours()
        for i in range(self.count()):
            it = self.item(i)
            f = QFont()
            f.setPointSize(self.font_size + (2 if i == self.current else 0))
            f.setBold(i == self.current)
            it.setFont(f)
            if not self.lines:
                it.setForeground(QColor(c["muted"]))
            elif i == self.current:
                it.setForeground(QColor(c["accent"]))
            elif not self.synced or i == self.current + 1:
                it.setForeground(QColor(c["text"]))
            else:
                it.setForeground(QColor(c["muted"]))

    def update_position(self, ms):
        if not self.synced or not self.lines:
            return
        idx = lrc_index(self.lines, ms + self.offset)
        if idx != self.current:
            self.current = idx
            self._restyle()
            if idx >= 0:
                self.scrollToItem(self.item(idx), QAbstractItemView.PositionAtCenter)

    def _clicked(self, it):
        if self.synced and self.lines:
            row = self.row(it)
            if 0 <= row < len(self.lines):
                self.seekRequested.emit(max(0, self.lines[row][0] - self.offset))


# ------------------------------------------------------------------ track table
class TrackModel(QAbstractTableModel):
    COLS = ["col.no", "col.title", "col.artist", "col.album", "col.time", "col.format", "col.cover", "col.lyrics",
            "col.rating", "col.plays"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []
        self.playing = None

    def set_rows(self, rows):
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return len(self.COLS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return tr(self.COLS[section])
        return None

    def set_playing(self, path):
        self.playing = path
        if self.rows:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self.rows) - 1, len(self.COLS) - 1))

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        r = self.rows[index.row()]
        col = index.column()
        playing = r["path"] == self.playing
        if role == Qt.DisplayRole:
            if col == 0:
                return "▶" if playing else (str(r["track_no"]) if r.get("track_no") else "")
            if col == 1:
                return r.get("title") or os.path.basename(r["path"])
            if col == 2:
                return r.get("artist") or ""
            if col == 3:
                return r.get("album") or ""
            if col == 4:
                return fmt_time(r["duration"]) if r.get("duration") else ""
            if col == 5:
                parts = [r.get("codec") or ""]
                if r.get("bits") and r.get("samplerate"):
                    parts.append(f'{r["bits"]}/{r["samplerate"] // 1000}')
                elif r.get("bitrate"):
                    parts.append(f'{r["bitrate"]} kbps')
                return " ".join(p for p in parts if p)
            if col == 6:
                return "✓" if r.get("has_cover") else "—"
            if col == 7:
                return "✓" if r.get("has_lyrics") else "—"
            if col == 8:
                n = int(r.get("rating") or 0)
                return ("♥ " if r.get("favourite") else "") + "★" * n + "☆" * (5 - n)
            if col == 9:
                return str(r.get("play_count") or "")
        if role == Qt.ForegroundRole:
            c = cm_theme.colours()
            if playing and col in (0, 1):
                return QColor(c["accent"])
            if col in (6, 7):
                return QColor("#16a34a") if (r.get("has_cover") if col == 6 else r.get("has_lyrics")) else QColor(c["muted"])
            if col == 8:
                return QColor("#f5a524")
            if col in (0, 4, 5, 9):
                return QColor(c["muted"])
        if role == Qt.FontRole and playing:
            f = QFont()
            f.setBold(True)
            return f
        if role == Qt.TextAlignmentRole and col in (0, 4, 6, 7, 9):
            return int(Qt.AlignCenter)
        if role == Qt.ToolTipRole:
            return r["path"]
        return None

    def sort(self, column, order=Qt.AscendingOrder):
        keys = {0: lambda r: (r.get("disc_no") or 0, r.get("track_no") or 0), 1: lambda r: (r.get("title") or "").lower(),
                2: lambda r: (r.get("artist") or "").lower(), 3: lambda r: ((r.get("album") or "").lower(), r.get("track_no") or 0),
                4: lambda r: r.get("duration") or 0, 5: lambda r: (r.get("codec") or "", r.get("bitrate") or 0),
                6: lambda r: r.get("has_cover") or 0, 7: lambda r: r.get("has_lyrics") or 0,
                8: lambda r: (r.get("rating") or 0, r.get("favourite") or 0), 9: lambda r: r.get("play_count") or 0}
        self.layoutAboutToBeChanged.emit()
        self.rows.sort(key=keys.get(column, keys[1]), reverse=order == Qt.DescendingOrder)
        self.layoutChanged.emit()


class TrackTable(QTableView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.model_ = TrackModel(self)
        self.setModel(self.model_)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setAlternatingRowColors(True)
        self.setShowGrid(False)
        self.setSortingEnabled(True)
        self.setWordWrap(False)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.verticalHeader().hide()
        self.verticalHeader().setDefaultSectionSize(30)
        h = self.horizontalHeader()
        h.setHighlightSections(False)
        h.setStretchLastSection(False)
        for col, w in enumerate([38, 200, 160, 180, 56, 116, 56, 50, 88, 52]):
            self.setColumnWidth(col, w)
        for col in (1, 2, 3):
            h.setSectionResizeMode(col, h.ResizeMode.Stretch)
        h.setMinimumSectionSize(36)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setDragEnabled(False)

    def selected_rows(self):
        return [self.model_.rows[i.row()] for i in sorted(self.selectionModel().selectedRows(), key=lambda i: i.row())]

    def selected_paths(self):
        return [r["path"] for r in self.selected_rows()]


class AlbumStrip(QListView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("AlbumStrip")
        self.setViewMode(QListView.IconMode)
        self.setFlow(QListView.LeftToRight)
        self.setWrapping(False)
        self.setIconSize(QSize(124, 124))
        self.setGridSize(QSize(146, 182))
        self.setUniformItemSizes(True)
        self.setMovement(QListView.Static)
        self.setResizeMode(QListView.Adjust)
        self.setWordWrap(True)
        self.setTextElideMode(Qt.ElideRight)
        self.setFixedHeight(200)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setSelectionMode(QAbstractItemView.SingleSelection)

    def wheelEvent(self, e):
        # a normal mouse wheel scrolls the album strip sideways
        bar = self.horizontalScrollBar()
        bar.setValue(bar.value() - e.angleDelta().y() - e.angleDelta().x())
        e.accept()


class SideList(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SideList")
        self.setIconSize(QSize(20, 20))
        self.setFocusPolicy(Qt.NoFocus)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setContextMenuPolicy(Qt.CustomContextMenu)

    def heading(self, key):
        it = QListWidgetItem(tr(key).upper())
        it.setFlags(Qt.NoItemFlags)
        f = QFont()
        f.setPointSize(7)
        f.setBold(True)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 1.0)
        it.setFont(f)
        it.setForeground(QColor(cm_theme.colours()["muted"]))
        it.setSizeHint(QSize(10, 30))
        self.addItem(it)
        return it

    def entry(self, text, icon, data, count=None):
        it = QListWidgetItem(icon, text + (f"   ({count})" if count else ""))
        it.setData(Qt.UserRole, data)
        it.setSizeHint(QSize(10, 32))
        self.addItem(it)
        return it


def make_action(parent, key, glyph, colour, slot, shortcut=None, checkable=False):
    a = QAction(cm_icons.glossy(glyph, colour, 40), tr(key), parent)
    a.setData(key)
    a.setIconVisibleInMenu(True)
    bind(a, key)
    if slot:
        a.triggered.connect(slot)
    if shortcut:
        a.setShortcut(shortcut)
        a.setShortcutContext(Qt.WindowShortcut)
    a.setCheckable(checkable)
    parent.addAction(a)
    return a


def popup_menu(parent=None):
    return QMenu(parent)


def size_policy_expanding(w):
    w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    return w
