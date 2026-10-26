"""Claudius Multimedia - building blocks of the main window: header + ribbon, transport bar, video view,
synced lyrics view, track table (column chooser, star ratings, F2 editing, dragging), album / video tiles,
sidebar and queue drop targets, folder tree."""
import json
import os
import time
import weakref

from PySide6.QtCore import (QAbstractTableModel, QByteArray, QMimeData, QModelIndex, QPointF, QRectF, QSize, Qt,
                            QTimer, Signal)
from PySide6.QtGui import (QAction, QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QPixmap,
                           QStandardItemModel)
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QButtonGroup, QFrame, QGraphicsPixmapItem,
                               QGraphicsScene, QGraphicsSimpleTextItem, QGraphicsView, QHBoxLayout, QLabel, QLineEdit,
                               QListView, QListWidget, QListWidgetItem, QMenu, QPushButton, QSizePolicy, QSlider,
                               QStackedWidget, QStyle, QStyledItemDelegate, QStyleOptionViewItem, QTableView, QToolButton, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget, QGraphicsItem)

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


def wrap_label(text, limit=13):
    """Long ribbon labels go onto two lines (split at the space nearest the middle)."""
    text = text.replace("&", "")
    if len(text) <= limit or " " not in text:
        return text
    mid = len(text) // 2
    spaces = [i for i, ch in enumerate(text) if ch == " "]
    i = min(spaces, key=lambda k: abs(k - mid))
    return text[:i] + "\n" + text[i + 1:]


class RibbonButton(QToolButton):
    def __init__(self, action, menu=None):
        super().__init__()
        self.setObjectName("RibbonBtn")
        self.setDefaultAction(action)
        self.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.setIconSize(QSize(40, 40))
        self.setFixedHeight(80)
        self._wrap()
        self.setAutoRaise(True)
        self.setCursor(Qt.PointingHandCursor)
        if menu is not None:
            self.setMenu(menu)
            self.setPopupMode(QToolButton.InstantPopup)

    def _wrap(self):
        a = self.defaultAction()
        if a is not None:
            self.setText(wrap_label(a.text()))
            self.setToolTip(a.text().replace("&", ""))

    def actionEvent(self, e):
        super().actionEvent(e)
        self._wrap()


class Ribbon(QStackedWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Ribbon")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(110)
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
TRACK_MIME = "application/x-claudius-tracks"


def tracks_mime(paths):
    md = QMimeData()
    md.setData(TRACK_MIME, QByteArray(json.dumps(list(paths)).encode("utf-8")))
    return md


def paths_from_mime(md):
    if md is None or not md.hasFormat(TRACK_MIME):
        return []
    try:
        return [p for p in json.loads(bytes(md.data(TRACK_MIME)).decode("utf-8")) if isinstance(p, str)]
    except ValueError:
        return []


LOSSLESS = {"FLAC", "ALAC", "WAV", "APE", "WV", "AIFF", "AIF", "WAVPACK", "MONKEY'S AUDIO"}

# column id, header text key, default width, shown by default
COLUMNS = [
    ("no", "col.no", 38, True), ("title", "col.title", 230, True), ("artist", "col.artist", 170, True),
    ("album", "col.album", 180, True), ("albumartist", "col.albumartist", 160, False), ("year", "col.year", 56, False),
    ("genre", "col.genre", 110, False), ("time", "col.time", 56, True), ("format", "col.format", 112, True),
    ("bitrate", "col.bitrate", 80, False), ("cover", "col.cover", 54, True), ("lyrics", "col.lyrics", 52, True),
    ("fav", "col.fav", 34, False), ("rating", "col.rating", 92, True), ("plays", "col.plays", 54, True),
    ("added", "col.added", 98, False), ("last", "col.last", 128, False), ("path", "col.path", 320, False),
]
COL_IDS = [c[0] for c in COLUMNS]
EDITABLE = {"no": "track", "title": "title", "artist": "artist", "album": "album", "albumartist": "albumartist",
            "year": "year", "genre": "genre"}
CENTERED = {"no", "time", "cover", "lyrics", "fav", "plays", "year"}
MUTED_COLS = {"no", "time", "format", "bitrate", "plays", "added", "last", "path", "year"}


def _date(ts, with_time=False):
    if not ts:
        return ""
    return time.strftime("%Y-%m-%d %H:%M" if with_time else "%Y-%m-%d", time.localtime(ts))


class TrackModel(QAbstractTableModel):
    """Rows are dicts from cm_library. edit_hook(row, field, value) -> updated row dict or None (when the tag
    could not be written); paths_hook() is not needed - drag data comes straight from the rows."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []
        self.playing = None
        self.edit_hook = None
        self.sort_col, self.sort_order = None, Qt.AscendingOrder

    def set_rows(self, rows):
        self.beginResetModel()
        self.rows = rows
        if self.sort_col is not None:
            self._sort_rows(self.sort_col, self.sort_order)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return tr(COLUMNS[section][1])
        if orientation == Qt.Horizontal and role == Qt.ToolTipRole:
            return tr("col.tip")
        return None

    def set_playing(self, path):
        self.playing = path
        if self.rows:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self.rows) - 1, len(COLUMNS) - 1))

    def row_changed(self, i):
        if 0 <= i < len(self.rows):
            self.dataChanged.emit(self.index(i, 0), self.index(i, len(COLUMNS) - 1))

    def find(self, path):
        for i, r in enumerate(self.rows):
            if r["path"] == path:
                return i
        return -1

    def flags(self, index):
        f = Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled
        if index.isValid() and COL_IDS[index.column()] in EDITABLE and not self.rows[index.row()].get("missing"):
            f |= Qt.ItemIsEditable
        return f

    def _text(self, r, cid):
        if cid == "no":
            return str(r["track_no"]) if r.get("track_no") else ""
        if cid == "title":
            return r.get("title") or os.path.basename(r["path"])
        if cid in ("artist", "album", "albumartist", "genre", "year"):
            return str(r.get(cid) or "")
        if cid == "time":
            return fmt_time(r["duration"]) if r.get("duration") else ""
        if cid == "format":
            parts = [r.get("codec") or ""]
            if r.get("bits") and r.get("samplerate"):
                parts.append(f'{r["bits"]}/{r["samplerate"] // 1000}')
            elif r.get("bitrate"):
                parts.append(f'{r["bitrate"]} kbps')
            return " ".join(p for p in parts if p)
        if cid == "bitrate":
            return f'{r["bitrate"]} kbps' if r.get("bitrate") else ""
        if cid == "cover":
            return "✓" if r.get("has_cover") else "—"
        if cid == "lyrics":
            return "✓" if r.get("has_lyrics") else "—"
        if cid == "fav":
            return "♥" if r.get("favourite") else "♡"
        if cid == "rating":
            return ""
        if cid == "plays":
            return str(r.get("play_count") or "")
        if cid == "added":
            return _date(r.get("added"))
        if cid == "last":
            return _date(r.get("last_played"), True)
        if cid == "path":
            return r["path"]
        return ""

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        r = self.rows[index.row()]
        cid = COL_IDS[index.column()]
        playing = r["path"] == self.playing
        missing = bool(r.get("missing"))
        if role == Qt.DisplayRole:
            if cid == "no" and playing:
                return "▶"
            if cid == "title" and missing:
                return "⚠ " + self._text(r, cid)
            return self._text(r, cid)
        if role == Qt.EditRole:
            if cid == "no":
                return str(r.get("track_no") or "")
            return self._text(r, cid)
        if role == Qt.UserRole:
            return int(r.get("rating") or 0)
        if role == Qt.ForegroundRole:
            c = cm_theme.colours()
            if missing:
                return QColor(c["muted"])
            if playing and cid in ("no", "title"):
                return QColor(c["accent"])
            if cid in ("cover", "lyrics"):
                on = r.get("has_cover") if cid == "cover" else r.get("has_lyrics")
                return QColor("#16a34a") if on else QColor(c["muted"])
            if cid == "fav":
                return QColor("#e5484d") if r.get("favourite") else QColor(c["muted"])
            if cid in MUTED_COLS:
                return QColor(c["muted"])
        if role == Qt.FontRole and (playing or missing):
            f = QFont()
            f.setBold(playing)
            f.setItalic(missing)
            return f
        if role == Qt.TextAlignmentRole and cid in CENTERED:
            return int(Qt.AlignCenter)
        if role == Qt.ToolTipRole:
            if missing:
                return tr("lib.missing_tip", path=r["path"])
            if cid == "rating":
                return tr("col.rating_tip")
            if cid == "fav":
                return tr("col.fav_tip")
            return r["path"]
        return None

    def setData(self, index, value, role=Qt.EditRole):
        if role != Qt.EditRole or not index.isValid() or self.edit_hook is None:
            return False
        cid = COL_IDS[index.column()]
        if cid not in EDITABLE:
            return False
        r = self.rows[index.row()]
        value = str(value).strip()
        if value == self.data(index, Qt.EditRole):
            return False
        new = self.edit_hook(r, EDITABLE[cid], value)
        if not new:
            return False
        self.rows[index.row()] = new
        self.row_changed(index.row())
        return True

    def mimeTypes(self):
        return [TRACK_MIME]

    def mimeData(self, indexes):
        rows = sorted({i.row() for i in indexes})
        return tracks_mime([self.rows[i]["path"] for i in rows if 0 <= i < len(self.rows)])

    def supportedDragActions(self):
        return Qt.CopyAction

    SORT_KEYS = {
        "no": lambda r: (r.get("disc_no") or 0, r.get("track_no") or 0),
        "title": lambda r: (r.get("title") or "").lower(), "artist": lambda r: (r.get("artist") or "").lower(),
        "album": lambda r: ((r.get("album") or "").lower(), r.get("disc_no") or 0, r.get("track_no") or 0),
        "albumartist": lambda r: (r.get("albumartist") or "").lower(), "year": lambda r: str(r.get("year") or ""),
        "genre": lambda r: (r.get("genre") or "").lower(), "time": lambda r: r.get("duration") or 0,
        "format": lambda r: ((r.get("codec") or "").upper() in LOSSLESS, r.get("bits") or 0, r.get("bitrate") or 0),
        "bitrate": lambda r: r.get("bitrate") or 0, "cover": lambda r: r.get("has_cover") or 0,
        "lyrics": lambda r: r.get("has_lyrics") or 0, "fav": lambda r: r.get("favourite") or 0,
        "rating": lambda r: (r.get("rating") or 0, r.get("favourite") or 0), "plays": lambda r: r.get("play_count") or 0,
        "added": lambda r: r.get("added") or 0, "last": lambda r: r.get("last_played") or 0,
        "path": lambda r: r["path"].lower(),
    }

    def _sort_rows(self, column, order):
        key = self.SORT_KEYS.get(COL_IDS[column], self.SORT_KEYS["title"])
        self.rows.sort(key=key, reverse=order == Qt.DescendingOrder)

    def sort(self, column, order=Qt.AscendingOrder):
        if column < 0:
            self.sort_col = None
            return
        self.sort_col, self.sort_order = column, order
        self.layoutAboutToBeChanged.emit()
        self._sort_rows(column, order)
        self.layoutChanged.emit()


class StarDelegate(QStyledItemDelegate):
    """Five stars; the rating column of the track table."""
    STAR = 14

    def paint(self, p, option, index):
        self.initStyleOption(option, index)
        option.text = ""
        QApplication.style().drawControl(QStyle.CE_ItemViewItem, option, p, option.widget)
        n = int(index.data(Qt.UserRole) or 0)
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        f = QFont(option.font)
        f.setPixelSize(13)
        p.setFont(f)
        x = option.rect.left() + 6
        y = option.rect.top()
        h = option.rect.height()
        c = cm_theme.colours()
        for i in range(5):
            p.setPen(QColor("#f5a524") if i < n else QColor(c["border"]))
            p.drawText(QRectF(x + i * self.STAR, y, self.STAR, h), Qt.AlignCenter, "★")
        p.restore()

    @classmethod
    def star_at(cls, rect, x):
        i = int((x - rect.left() - 6) // cls.STAR)
        return i + 1 if 0 <= i < 5 else None


class TrackTable(QTableView):
    ratingClicked = Signal(dict, int)
    favClicked = Signal(dict)
    removeRequested = Signal()
    trashRequested = Signal()
    layoutSaved = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.model_ = TrackModel(self)
        self.setModel(self.model_)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setAlternatingRowColors(True)
        self.setShowGrid(False)
        self.horizontalHeader().setSortIndicator(-1, Qt.AscendingOrder)
        self.setSortingEnabled(True)
        self.model_.sort_col = None
        self.setWordWrap(False)
        self.setEditTriggers(QAbstractItemView.EditKeyPressed)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.verticalHeader().hide()
        self.verticalHeader().setDefaultSectionSize(30)
        self.setItemDelegateForColumn(COL_IDS.index("rating"), StarDelegate(self))
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragOnly)
        self.setDefaultDropAction(Qt.CopyAction)
        h = self.horizontalHeader()
        h.setHighlightSections(False)
        h.setStretchLastSection(False)
        h.setSectionsMovable(True)
        h.setMinimumSectionSize(30)
        h.setContextMenuPolicy(Qt.CustomContextMenu)
        h.customContextMenuRequested.connect(self._header_menu)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.reset_columns()
        self._save_timer = QTimer(self, singleShot=True, interval=600, timeout=self._emit_layout)
        h.sectionResized.connect(lambda *_: self._save_timer.start())
        h.sectionMoved.connect(lambda *_: self._save_timer.start())

    def reset_columns(self):
        h = self.horizontalHeader()
        for logical, (_cid, _key, width, shown) in enumerate(COLUMNS):
            vis = h.visualIndex(logical)
            if vis != logical:
                h.moveSection(vis, logical)
            self.setColumnWidth(logical, width)
            self.setColumnHidden(logical, not shown)

    def restore_layout(self, state):
        """state: base64 of QHeaderView.saveState(), plus the column count it was made for."""
        try:
            count, data = state.split(":", 1)
            if int(count) != len(COLUMNS):
                return False
            return self.horizontalHeader().restoreState(QByteArray.fromBase64(data.encode()))
        except (ValueError, AttributeError):
            return False

    def layout_state(self):
        return f"{len(COLUMNS)}:" + bytes(self.horizontalHeader().saveState().toBase64()).decode()

    def _emit_layout(self):
        self.layoutSaved.emit(self.layout_state())

    def _header_menu(self, pos):
        m = QMenu(self)
        for logical, (cid, key, _w, _s) in enumerate(COLUMNS):
            if cid == "title":
                continue
            a = m.addAction(tr(key) if cid != "no" else tr("col.track_no"))
            a.setCheckable(True)
            a.setChecked(not self.isColumnHidden(logical))
            a.toggled.connect(lambda on, c=logical: (self.setColumnHidden(c, not on), self._emit_layout()))
        m.addSeparator()
        m.addAction(tr("col.reset"), lambda: (self.reset_columns(), self._emit_layout()))
        m.exec(self.horizontalHeader().mapToGlobal(pos))

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and not (e.modifiers() & (Qt.ShiftModifier | Qt.ControlModifier)):
            idx = self.indexAt(e.position().toPoint())
            if idx.isValid():
                cid = COL_IDS[idx.column()]
                row = self.model_.rows[idx.row()]
                if cid == "rating":
                    n = StarDelegate.star_at(self.visualRect(idx), e.position().x())
                    if n is not None:
                        self.selectRow(idx.row())
                        self.ratingClicked.emit(row, 0 if n == int(row.get("rating") or 0) else n)
                        return
                elif cid == "fav":
                    self.selectRow(idx.row())
                    self.favClicked.emit(row)
                    return
        super().mousePressEvent(e)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Delete and self.state() != QAbstractItemView.EditingState:
            if e.modifiers() & Qt.ShiftModifier:
                self.trashRequested.emit()
            else:
                self.removeRequested.emit()
            return
        if e.key() == Qt.Key_F2:
            idx = self.currentIndex()
            if idx.isValid() and not (self.model_.flags(idx) & Qt.ItemIsEditable):
                idx = self.model_.index(idx.row(), COL_IDS.index("title"))
                self.setCurrentIndex(idx)
            if idx.isValid():
                self.edit(idx)
            return
        super().keyPressEvent(e)

    def clear_sort(self):
        """Back to the library's own order (album / disc / track, or the playlist order)."""
        self.model_.sort_col = None
        self.horizontalHeader().setSortIndicator(-1, Qt.AscendingOrder)

    def selected_rows(self):
        return [self.model_.rows[i.row()] for i in sorted(self.selectionModel().selectedRows(), key=lambda i: i.row())]

    def selected_paths(self):
        return [r["path"] for r in self.selected_rows()]


class TileModel(QStandardItemModel):
    """Album / video tiles. resolver(list of item data) -> list of track paths (for dragging)."""
    resolver = None

    def mimeTypes(self):
        return [TRACK_MIME]

    def mimeData(self, indexes):
        keys = [i.data(Qt.UserRole) for i in indexes if i.isValid()]
        paths = self.resolver(keys) if self.resolver else []
        return tracks_mime(paths)

    def supportedDragActions(self):
        return Qt.CopyAction


class TileView(QListView):
    """Album covers / video thumbnails: a single row ("strip") above the track list, or a full page ("grid")."""
    removeRequested = Signal()
    trashRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("AlbumStrip")
        self.setViewMode(QListView.IconMode)
        self.setMovement(QListView.Static)
        self.setResizeMode(QListView.Adjust)
        self.setUniformItemSizes(True)
        self.setWordWrap(True)
        self.setTextElideMode(Qt.ElideRight)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragOnly)
        self.setDefaultDropAction(Qt.CopyAction)
        self.setSpacing(4)
        self.mode = "strip"
        self.tile = 124
        self.wide = False
        self.apply()

    def configure(self, mode=None, tile=None, wide=None):
        if mode is not None:
            self.mode = mode
        if tile is not None:
            self.tile = max(72, min(260, int(tile)))
        if wide is not None:
            self.wide = wide
        self.apply()

    def icon_size(self):
        return QSize(int(self.tile * 16 / 9), self.tile) if self.wide else QSize(self.tile, self.tile)

    def apply(self):
        ic = self.icon_size()
        self.setIconSize(ic)
        self.setGridSize(QSize(ic.width() + 22, ic.height() + 58))
        if self.mode == "grid":
            self.setFlow(QListView.LeftToRight)
            self.setWrapping(True)
            self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
            self.setMinimumHeight(0)
            self.setMaximumHeight(16777215)
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        else:
            self.setFlow(QListView.LeftToRight)
            self.setWrapping(False)
            self.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
            self.setFixedHeight(ic.height() + 76)
        self.doItemsLayout()

    def wheelEvent(self, e):
        if e.modifiers() & Qt.ControlModifier:
            # Ctrl + wheel changes the tile size
            self.configure(tile=self.tile + (12 if e.angleDelta().y() > 0 else -12))
            self.tileSizeChanged.emit(self.tile)
            e.accept()
            return
        if self.mode == "strip":
            bar = self.horizontalScrollBar()
            bar.setValue(bar.value() - e.angleDelta().y() - e.angleDelta().x())
            e.accept()
            return
        super().wheelEvent(e)

    tileSizeChanged = Signal(int)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Delete:
            (self.trashRequested if e.modifiers() & Qt.ShiftModifier else self.removeRequested).emit()
            return
        super().keyPressEvent(e)


class TileDelegate(QStyledItemDelegate):
    """Normal tile painting plus a red "watched so far" bar under video thumbnails (item role UserRole + 2)."""
    def paint(self, p, option, index):
        super().paint(p, option, index)
        progress = index.data(Qt.UserRole + 2) or 0
        if not progress:
            return
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        style = opt.widget.style() if opt.widget else QApplication.style()
        r = style.subElementRect(QStyle.SE_ItemViewItemDecoration, opt, opt.widget)
        if r.width() <= 0:
            return
        p.save()
        h = 4
        p.fillRect(QRectF(r.left(), r.bottom() - h + 1, r.width(), h), QColor(0, 0, 0, 150))
        p.fillRect(QRectF(r.left(), r.bottom() - h + 1, r.width() * min(1.0, float(progress)), h), QColor("#e5484d"))
        p.restore()


def tile_pixmap(pm, size, progress=0.0):
    """Cover / thumbnail cut to the tile shape, with an optional "watched so far" bar."""
    w, h = size.width(), size.height()
    ratio = 2.0
    out = QPixmap(int(w * ratio), int(h * ratio))
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, out.width(), out.height()), 8 * ratio, 8 * ratio)
    p.setClipPath(path)
    src = pm.scaled(out.width(), out.height(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    p.drawPixmap(int((out.width() - src.width()) / 2), int((out.height() - src.height()) / 2), src)
    if progress > 0:
        bar_h = 5 * ratio
        p.fillRect(QRectF(0, out.height() - bar_h, out.width(), bar_h), QColor(0, 0, 0, 150))
        p.fillRect(QRectF(0, out.height() - bar_h, out.width() * min(1.0, progress), bar_h), QColor("#e5484d"))
    p.end()
    out.setDevicePixelRatio(ratio)
    return out


class SideList(QListWidget):
    """The sidebar. Tracks dragged from the library can be dropped on a playlist, on "New playlist"
    or on Favourites."""
    tracksDropped = Signal(object, list)
    DROP_KINDS = ("playlist", "newpl", "fav")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SideList")
        self.setIconSize(QSize(20, 20))
        self.setFocusPolicy(Qt.NoFocus)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(False)
        self._hover = None

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

    def entry(self, text, icon, data, count=None, warn=False):
        it = QListWidgetItem(icon, text + (f"   ({count})" if count else ""))
        it.setData(Qt.UserRole, data)
        it.setSizeHint(QSize(10, 32))
        if warn:
            it.setForeground(QColor("#d97706"))
        self.addItem(it)
        return it

    def _target(self, pos):
        it = self.itemAt(pos)
        data = it.data(Qt.UserRole) if it else None
        if data and (data[0] in self.DROP_KINDS or data == ("view", "favourites")):
            return it
        return None

    def _set_hover(self, it):
        if self._hover is it:
            return
        if self._hover is not None:
            try:
                self._hover.setBackground(QColor(0, 0, 0, 0))
            except RuntimeError:
                pass
        self._hover = it
        if it is not None:
            it.setBackground(QColor(cm_theme.colours()["accentSoft"]))

    def dragEnterEvent(self, e):
        if e.mimeData().hasFormat(TRACK_MIME):
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragMoveEvent(self, e):
        it = self._target(e.position().toPoint())
        self._set_hover(it)
        if it is not None:
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragLeaveEvent(self, e):
        self._set_hover(None)

    def dropEvent(self, e):
        it = self._target(e.position().toPoint())
        self._set_hover(None)
        paths = paths_from_mime(e.mimeData())
        if it is not None and paths:
            e.acceptProposedAction()
            self.tracksDropped.emit(it.data(Qt.UserRole), paths)
        else:
            e.ignore()


class QueueList(QListWidget):
    """The "Up next" list: reorder by dragging, and drop tracks from the library on it."""
    tracksDropped = Signal(list, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Queue")
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setIconSize(QSize(36, 36))
        self.setAcceptDrops(True)

    def dragEnterEvent(self, e):
        if e.mimeData().hasFormat(TRACK_MIME):
            e.acceptProposedAction()
            return
        super().dragEnterEvent(e)

    def dragMoveEvent(self, e):
        if e.mimeData().hasFormat(TRACK_MIME):
            e.acceptProposedAction()
            return
        super().dragMoveEvent(e)

    def dropEvent(self, e):
        if e.mimeData().hasFormat(TRACK_MIME):
            it = self.itemAt(e.position().toPoint())
            row = self.row(it) if it is not None else self.count()
            e.acceptProposedAction()
            self.tracksDropped.emit(paths_from_mime(e.mimeData()), row)
            return
        super().dropEvent(e)


class FolderTree(QTreeWidget):
    """Library folders as a tree (Browse > Folders)."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("FolderTree")
        self.setHeaderHidden(True)
        self.setFixedWidth(260)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.setUniformRowHeights(True)
        self.setAnimated(False)
        self.setExpandsOnDoubleClick(True)

    def load(self, folders, roots, other_label, icon):
        """folders: [(folder, n)] ; roots: library folders."""
        self.clear()
        norm_roots = sorted({os.path.normpath(r) for r in roots}, key=len, reverse=True)
        nodes = {}

        def node_for(path, parent, label):
            key = os.path.normcase(path)
            if key in nodes:
                return nodes[key]
            it = QTreeWidgetItem(parent, [label])
            it.setData(0, Qt.UserRole, path)
            it.setData(0, Qt.UserRole + 1, 0)
            it.setIcon(0, icon)
            it.setToolTip(0, path)
            nodes[key] = it
            return it

        other = None
        for folder, n in folders:
            folder = os.path.normpath(folder)
            root = next((r for r in norm_roots if os.path.normcase(folder) == os.path.normcase(r) or
                         os.path.normcase(folder).startswith(os.path.normcase(r).rstrip("\\/") + os.sep)), None)
            if root is None:
                if other is None:
                    other = QTreeWidgetItem(self, [other_label])
                    other.setData(0, Qt.UserRole, None)
                    other.setData(0, Qt.UserRole + 1, 0)
                leaf = node_for(folder, other, folder)
                chain = [leaf]
            else:
                parent = node_for(root, self, root)
                chain = [parent]
                rel = os.path.relpath(folder, root)
                if rel != ".":
                    cur = root
                    for part in rel.split(os.sep):
                        cur = os.path.join(cur, part)
                        parent = node_for(cur, parent, part)
                        chain.append(parent)
            for it in chain:
                it.setData(0, Qt.UserRole + 1, (it.data(0, Qt.UserRole + 1) or 0) + n)
            if other is not None and root is None:
                other.setData(0, Qt.UserRole + 1, (other.data(0, Qt.UserRole + 1) or 0) + n)
        for it in list(nodes.values()) + ([other] if other else []):
            it.setText(0, f"{it.text(0)}  ({it.data(0, Qt.UserRole + 1)})")
        self.sortItems(0, Qt.AscendingOrder)
        for i in range(self.topLevelItemCount()):
            self.topLevelItem(i).setExpanded(True)


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
