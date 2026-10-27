"""Claudius Multimedia - dialogs: tag editor, cover / MusicBrainz / lyrics search, settings, rename, About page."""
import os
import re
import time

from PySide6.QtCore import QRectF, QSize, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout,
                               QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QStackedWidget,
                               QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

import cm_icons
import cm_library
import cm_online
import cm_tags
import cm_theme
from cm_core import (APP_AUTHORS, APP_NAME, APP_URL, APP_VERSION, LANGUAGES, fmt_time, resource_dir, settings, tr)
from cm_parse import parse_lrc, shift_lrc, title_from_filename
from cm_widgets import CoverLabel, muted


def primary(text):
    b = QPushButton(text)
    b.setObjectName("Primary")
    b.setDefault(True)
    return b


def ask_online(parent):
    if settings.get("online", True):
        return True
    QMessageBox.information(parent, APP_NAME, tr("msg.online_off"))
    return False


class Dialog(QDialog):
    def __init__(self, parent, title, glyph="info", colour="blue"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowIcon(cm_icons.glossy(glyph, colour, 32))
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)

    def showEvent(self, e):
        cm_theme.set_windows_dark_titlebar(self)
        super().showEvent(e)

    def footer(self, layout, *buttons, left=None):
        bar = QHBoxLayout()
        if left is not None:
            bar.addWidget(left, 1)
        else:
            bar.addStretch(1)
        for b in buttons:
            bar.addWidget(b)
        layout.addLayout(bar)


# ------------------------------------------------------------------ cover picker
def cover_search_fields(path, info=None):
    """(artist, album, title) to search covers with: the tags, or - when they are empty - what the file name
    ("01 - Artist - Title.mp3") and the folder name ("Artist - Album") say."""
    info = info if info is not None else (cm_tags.read(path) if path and os.path.isfile(path) else {})
    guess = title_from_filename(path) if path else {}
    artist = (info.get("artist") or info.get("albumartist") or guess.get("artist") or "").strip()
    title = (info.get("title") or guess.get("title") or "").strip()
    album = (info.get("album") or "").strip()
    if path and (not artist or not album):
        folder = os.path.basename(os.path.dirname(path))
        parts = [x.strip() for x in folder.split(" - ", 1)] if " - " in folder else []
        if len(parts) == 2:
            artist = artist or parts[0]
            album = album or re.sub(r"^\(?\d{4}\)?\s*", "", parts[1])
    return artist, album, title


class CoverPicker(Dialog):
    """Searches iTunes, Deezer and Cover Art Archive and returns the chosen image bytes in .result_data."""
    def __init__(self, parent, artist, album, title=""):
        super().__init__(parent, tr("cover.title"), "image", "pink")
        self.resize(820, 560)
        self.result_data = None
        self.cands = []
        self.closed = False
        self.busy = False
        self.generation = 0
        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        self.artist = QLineEdit(artist)
        self.title = QLineEdit(title)
        self.album = QLineEdit(album)
        for edit, key in ((self.artist, "field.artist"), (self.title, "field.title"), (self.album, "field.album")):
            col = QVBoxLayout()
            col.setSpacing(2)
            col.addWidget(muted(tr(key)))
            edit.setPlaceholderText(tr(key))
            edit.setClearButtonEnabled(True)
            edit.returnPressed.connect(self.search)
            col.addWidget(edit)
            row.addLayout(col, 1)
        search = QPushButton(tr("btn.search"))
        search.clicked.connect(self.search)
        row.addWidget(search, 0, Qt.AlignBottom)
        lay.addLayout(row)
        self.status = muted(tr("cover.sources"))
        lay.addWidget(self.status)
        self.grid = QListWidget()
        self.grid.setViewMode(QListWidget.IconMode)
        self.grid.setIconSize(QSize(170, 170))
        self.grid.setGridSize(QSize(196, 236))
        self.grid.setResizeMode(QListWidget.Adjust)
        self.grid.setMovement(QListWidget.Static)
        self.grid.setWordWrap(True)
        self.grid.itemDoubleClicked.connect(lambda _: self.accept_choice())
        lay.addWidget(self.grid, 1)
        self.ok = primary(tr("btn.use_cover"))
        self.ok.clicked.connect(self.accept_choice)
        cancel = QPushButton(tr("btn.cancel"))
        cancel.clicked.connect(self.reject)
        self.footer(lay, cancel, self.ok)
        self.search()

    def search(self):
        self.generation = getattr(self, "generation", 0) + 1      # results of an older search are ignored
        gen = self.generation
        self.grid.clear()
        self.cands = []
        self.status.setText(tr("msg.searching"))
        cm_online.run(cm_online.cover_candidates, self.artist.text().strip(), self.album.text().strip(),
                      self.title.text().strip(), done=lambda cands: self._found(cands, gen),
                      failed=lambda m: gen == self.generation and self.status.setText(tr("msg.online_error", error=m)))

    def _found(self, cands, gen):
        if gen != self.generation or self.closed:
            return
        self.cands = cands
        self.status.setText(tr("cover.found", n=len(cands)) if cands else tr("msg.nothing_found"))
        ph = cm_icons.placeholder_cover(170, "cover")
        for i, c in enumerate(cands):
            it = QListWidgetItem(QIcon(ph), f'{c["source"]}\n{c["label"]}')
            it.setData(Qt.UserRole, i)
            it.setToolTip(c["label"])
            self.grid.addItem(it)
            cm_online.run(cm_online.download, c["thumb"], done=lambda data, i=i: self._thumb(i, data, gen))
        if cands:
            self.grid.setCurrentRow(0)

    def _thumb(self, i, data, gen):
        if gen != self.generation or self.closed or i >= self.grid.count():
            return
        img = QImage.fromData(data or b"")
        if img.isNull():
            return
        it = self.grid.item(i)
        it.setIcon(QIcon(QPixmap.fromImage(img.scaled(340, 340, Qt.KeepAspectRatio, Qt.SmoothTransformation))))
        self.cands[i]["size"] = f"{img.width()}×{img.height()}"
        it.setText(f'{self.cands[i]["source"]} · {img.width()}×{img.height()}\n{self.cands[i]["label"]}')

    def accept_choice(self):
        it = self.grid.currentItem()
        if not it or self.busy:
            return
        i = it.data(Qt.UserRole)
        if not (0 <= i < len(self.cands)):
            return
        c = self.cands[i]
        self.busy = True
        self.ok.setEnabled(False)
        self.status.setText(tr("msg.downloading"))

        def got(data):
            if self.closed:
                return
            img = QImage.fromData(data or b"")
            if img.isNull():
                fail(tr("msg.not_image"))
                return
            self.result_data = data
            self.accept()

        def fail(msg):
            if self.closed:
                return
            self.busy = False
            self.ok.setEnabled(True)
            self.status.setText(tr("msg.online_error", error=msg))
        # full size missing on the server: fall back to the thumbnail
        cm_online.run(cm_online.download, c["url"], done=got,
                      failed=lambda m: not self.closed and cm_online.run(cm_online.download, c["thumb"], done=got,
                                                                         failed=fail))

    def done(self, r):
        self.closed = True
        super().done(r)


# ------------------------------------------------------------------ MusicBrainz picker
class MusicBrainzPicker(Dialog):
    def __init__(self, parent, artist, title, album="", duration=0):
        super().__init__(parent, tr("mb.title"), "star", "orange")
        self.resize(900, 500)
        self.result_row = None
        self.rows = []
        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        self.e_artist, self.e_title, self.e_album = QLineEdit(artist), QLineEdit(title), QLineEdit(album)
        for e, k in ((self.e_artist, "field.artist"), (self.e_title, "field.title"), (self.e_album, "field.album")):
            e.setPlaceholderText(tr(k))
            e.returnPressed.connect(self.search)
            row.addWidget(e, 1)
        b = QPushButton(tr("btn.search"))
        b.clicked.connect(self.search)
        row.addWidget(b)
        lay.addLayout(row)
        self.duration = duration
        self.status = muted()
        lay.addWidget(self.status)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels([tr("mb.score"), tr("field.title"), tr("field.artist"), tr("field.album"),
                                              tr("field.year"), tr("field.track"), tr("col.time")])
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        for i, w in enumerate([60, 220, 180, 220, 60, 70, 60]):
            self.table.setColumnWidth(i, w)
        self.table.itemDoubleClicked.connect(lambda _: self.choose())
        lay.addWidget(self.table, 1)
        ok = primary(tr("btn.apply"))
        ok.clicked.connect(self.choose)
        cancel = QPushButton(tr("btn.cancel"))
        cancel.clicked.connect(self.reject)
        self.footer(lay, cancel, ok, left=muted(tr("mb.note")))
        self.search()

    def search(self):
        self.table.setRowCount(0)
        self.status.setText(tr("msg.searching"))
        cm_online.run(cm_online.musicbrainz_lookup, self.e_artist.text(), self.e_title.text(), self.e_album.text(),
                      self.duration, done=self._found, failed=lambda m: self.status.setText(tr("msg.online_error", error=m)))

    def _found(self, rows):
        self.rows = rows
        self.status.setText(tr("mb.found", n=len(rows)) if rows else tr("msg.nothing_found"))
        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            vals = [f'{r["score"]}%', r["title"], r["artist"], r["album"] + (f' ({r["country"]})' if r["country"] else ""),
                    r["year"], r["track"], fmt_time(r["length"]) if r["length"] else ""]
            for j, v in enumerate(vals):
                self.table.setItem(i, j, QTableWidgetItem(str(v)))
        if rows:
            self.table.selectRow(0)

    def choose(self):
        r = self.table.currentRow()
        if 0 <= r < len(self.rows):
            self.result_row = self.rows[r]
            self.accept()


# ------------------------------------------------------------------ lyrics search / editor
class LyricsDialog(Dialog):
    """Search LRCLIB, preview, adjust timing and save (embedded and/or .lrc). With pick_only=True it just returns
    the chosen text in .result_text (used by the tag editor)."""
    def __init__(self, parent, path, info, current_text="", pick_only=False):
        super().__init__(parent, tr("lyr.title", title=info.get("title") or os.path.basename(path or "")), "lyrics", "purple")
        self.resize(980, 640)
        self.path, self.info, self.pick_only = path, info, pick_only
        self.result_text = None
        self.results = []
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.e_artist = QLineEdit(info.get("artist", ""))
        self.e_title = QLineEdit(info.get("title", ""))
        self.e_artist.setPlaceholderText(tr("field.artist"))
        self.e_title.setPlaceholderText(tr("field.title"))
        for e in (self.e_artist, self.e_title):
            e.returnPressed.connect(self.search)
            top.addWidget(e, 1)
        sb = QPushButton(tr("btn.search"))
        sb.clicked.connect(self.search)
        top.addWidget(sb)
        lay.addLayout(top)
        body = QHBoxLayout()
        left = QVBoxLayout()
        self.status = muted(tr("lyr.sources"))
        left.addWidget(self.status)
        self.list = QListWidget()
        self.list.setFixedWidth(320)
        self.list.currentRowChanged.connect(self._preview)
        left.addWidget(self.list, 1)
        self.chk_embed = QCheckBox(tr("lyr.embed"))
        self.chk_embed.setChecked(settings.get("embed_lyrics", True))
        self.chk_lrc = QCheckBox(tr("lyr.lrcfile"))
        self.chk_lrc.setChecked(settings.get("save_lrc_file", True))
        if pick_only:
            self.chk_embed.hide()
            self.chk_lrc.hide()
        elif path and not cm_tags.can_write(path):
            self.chk_embed.setChecked(False)
            self.chk_embed.setEnabled(False)
        left.addWidget(self.chk_embed)
        left.addWidget(self.chk_lrc)
        body.addLayout(left)
        right = QVBoxLayout()
        tools = QHBoxLayout()
        for label, delta in (("−0.5 s", -500), ("+0.5 s", 500)):
            b = QPushButton(label)
            b.setToolTip(tr("lyr.shift_tip"))
            b.clicked.connect(lambda _=False, d=delta: self.edit.setPlainText(shift_lrc(self.edit.toPlainText(), d)))
            tools.addWidget(b)
        self.kind = muted()
        tools.addWidget(self.kind, 1)
        clear = QPushButton(tr("btn.clear"))
        clear.clicked.connect(lambda: self.edit.setPlainText(""))
        tools.addWidget(clear)
        right.addLayout(tools)
        self.edit = QPlainTextEdit(current_text)
        self.edit.setStyleSheet("font-family: Consolas, 'DejaVu Sans Mono', monospace; font-size: 10pt;")
        self.edit.textChanged.connect(self._kind)
        right.addWidget(self.edit, 1)
        body.addLayout(right, 1)
        lay.addLayout(body, 1)
        ok = primary(tr("btn.use") if pick_only else tr("btn.save_lyrics"))
        ok.clicked.connect(self.save)
        cancel = QPushButton(tr("btn.cancel"))
        cancel.clicked.connect(self.reject)
        self.footer(lay, cancel, ok, left=muted(tr("lyr.privacy")))
        self._kind()
        if settings.get("online", True) and self.e_title.text():
            self.search()

    def _kind(self):
        lines, synced = parse_lrc(self.edit.toPlainText())
        self.kind.setText(tr("lyr.synced", n=len(lines)) if synced else (tr("lyr.plain", n=len(lines)) if lines else ""))

    def search(self):
        if not ask_online(self):
            return
        self.list.clear()
        self.status.setText(tr("msg.searching"))
        cm_online.run(cm_online.lyrics_search, self.e_artist.text(), self.e_title.text(), done=self._found,
                      failed=lambda m: self.status.setText(tr("msg.online_error", error=m)))

    def _found(self, rows):
        dur = self.info.get("duration") or 0
        if dur:
            rows.sort(key=lambda r: (not r["synced"], abs((r["duration"] or 0) - dur)))
        self.results = rows
        self.status.setText(tr("lyr.found", n=len(rows)) if rows else tr("msg.nothing_found"))
        for r in rows:
            kind = tr("lyr.kind_synced") if r["synced"] else tr("lyr.kind_plain")
            it = QListWidgetItem(f'{r["artist"]} — {r["title"]}\n{r["album"]} · {fmt_time(r["duration"])} · {kind}')
            self.list.addItem(it)
        if rows and not self.edit.toPlainText().strip():
            self.list.setCurrentRow(0)

    def _preview(self, row):
        if 0 <= row < len(self.results):
            r = self.results[row]
            self.edit.setPlainText(r["synced"] or r["plain"])

    def save(self):
        text = self.edit.toPlainText().strip()
        if self.pick_only:
            self.result_text = text
            self.accept()
            return
        if text and (self.info.get("artist") or self.info.get("title")) and not re.search(r"^\[ti:", text, re.M) \
                and parse_lrc(text)[1]:
            head = f'[ar:{self.info.get("artist", "")}]\n[ti:{self.info.get("title", "")}]\n'
            if self.info.get("album"):
                head += f'[al:{self.info["album"]}]\n'
            text = head + text
        settings["embed_lyrics"] = self.chk_embed.isChecked()
        settings["save_lrc_file"] = self.chk_lrc.isChecked()
        self.result_text = text
        self.accept()


# ------------------------------------------------------------------ tag editor
class TagEditor(Dialog):
    """Edits one file or several at once (then only the fields you change are written)."""
    saved = Signal(list)

    def __init__(self, parent, paths, release_file=None):
        super().__init__(parent, tr("tag.title"), "tag", "orange")
        self.paths = [p for p in paths if os.path.isfile(p)]
        self.release_file = release_file
        self.multi = len(self.paths) > 1
        self.resize(1000, 700)
        self.infos = [cm_tags.read(p) for p in self.paths]
        self.new_cover = None        # None = keep, b"" = remove, bytes = set
        self.new_lyrics = None
        self.changed = set()
        lay = QVBoxLayout(self)
        name = os.path.basename(self.paths[0]) if not self.multi else tr("tag.n_files", n=len(self.paths))
        head = QLabel(f"<b>{name}</b>")
        lay.addWidget(head)
        self.tabs = QTabWidget()
        lay.addWidget(self.tabs, 1)

        # --- details tab
        det = QWidget()
        dl = QHBoxLayout(det)
        dl.setContentsMargins(4, 14, 4, 4)
        dl.setSpacing(20)
        left = QVBoxLayout()
        self.cover = CoverLabel(250, 8)
        left.addWidget(self.cover)
        self.cover_info = muted()
        left.addWidget(self.cover_info)
        grid = QGridLayout()
        b_file = QPushButton(tr("btn.cover_file"))
        b_file.clicked.connect(self.cover_from_file)
        b_find = QPushButton(tr("btn.cover_online"))
        b_find.clicked.connect(self.cover_online)
        b_rem = QPushButton(tr("btn.remove"))
        b_rem.clicked.connect(self.cover_remove)
        b_exp = QPushButton(tr("btn.export"))
        b_exp.clicked.connect(self.cover_export)
        grid.addWidget(b_file, 0, 0)
        grid.addWidget(b_find, 0, 1)
        grid.addWidget(b_rem, 1, 0)
        grid.addWidget(b_exp, 1, 1)
        left.addLayout(grid)
        left.addStretch(1)
        dl.addLayout(left)
        form = QGridLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(4)
        self.edits = {}
        layout_spec = [("title", 0, 0, 2), ("artist", 2, 0, 1), ("albumartist", 2, 1, 1), ("album", 4, 0, 2),
                       ("year", 6, 0, 1), ("genre", 6, 1, 1), ("track", 8, 0, 1), ("disc", 8, 1, 1),
                       ("composer", 10, 0, 1), ("bpm", 10, 1, 1), ("comment", 12, 0, 2)]
        for key, r, c, span in layout_spec:
            form.addWidget(muted(tr("field." + key)), r, c, 1, span)
            if key == "genre":
                e = QComboBox()
                e.setEditable(True)
                e.addItems(["", "Alternative", "Blues", "Classical", "Country", "Dance", "Disco Polo", "Electronic", "Folk",
                            "Hip-Hop", "Indie", "Jazz", "Metal", "Pop", "Punk", "R&B", "Reggae", "Rock", "Soul",
                            "Soundtrack", "World"])
                line = e.lineEdit()
            else:
                e = QLineEdit()
                line = e
            vals = {i.get(key, "") for i in self.infos}
            value = vals.pop() if len(vals) == 1 else ""
            line.setText(value)
            if self.multi and len({i.get(key, "") for i in self.infos}) > 1:
                line.setPlaceholderText(tr("tag.keep"))
            line.textEdited.connect(lambda _t, k=key: self.changed.add(k))
            self.edits[key] = line
            form.addWidget(e, r + 1, c, 1, span)
        right = QVBoxLayout()
        right.addLayout(form)
        auto = QHBoxLayout()
        b_mb = QPushButton(cm_icons.glossy("star", "orange", 20), tr("act.mb_lookup"))
        b_mb.clicked.connect(self.musicbrainz)
        b_fn = QPushButton(cm_icons.glossy("list", "orange", 20), tr("act.tags_from_name"))
        b_fn.clicked.connect(self.from_filename)
        auto.addWidget(b_mb)
        auto.addWidget(b_fn)
        auto.addStretch(1)
        right.addSpacing(10)
        right.addLayout(auto)
        right.addStretch(1)
        dl.addLayout(right, 1)
        self.tabs.addTab(det, tr("tag.details"))

        # --- lyrics tab (single file)
        lyr = QWidget()
        ll = QVBoxLayout(lyr)
        bar = QHBoxLayout()
        b_l = QPushButton(cm_icons.glossy("lyrics", "purple", 20), tr("act.find_lyrics"))
        b_l.clicked.connect(self.lyrics_online)
        bar.addWidget(b_l)
        bar.addStretch(1)
        self.lyr_kind = muted()
        bar.addWidget(self.lyr_kind)
        ll.addLayout(bar)
        self.lyrics = QPlainTextEdit()
        self.lyrics.setStyleSheet("font-family: Consolas, 'DejaVu Sans Mono', monospace;")
        if not self.multi:
            self.lyrics.setPlainText(cm_tags.lyrics(self.paths[0]))
        self.lyrics.textChanged.connect(self._lyrics_changed)
        ll.addWidget(self.lyrics, 1)
        idx = self.tabs.addTab(lyr, tr("tag.lyrics"))
        self.tabs.setTabEnabled(idx, not self.multi)

        # --- file info tab
        info = QWidget()
        fl = QFormLayout(info)
        fl.setContentsMargins(10, 14, 10, 10)
        i0 = self.infos[0]
        if not self.multi:
            p = self.paths[0]
            rows = [(tr("info.file"), p), (tr("info.size"), f"{os.path.getsize(p) / 1048576:.1f} MB"),
                    (tr("info.format"), i0["codec"]), (tr("info.duration"), fmt_time(i0["duration"])),
                    (tr("info.bitrate"), f'{i0["bitrate"]} kbps' if i0["bitrate"] else "—"),
                    (tr("info.samplerate"), f'{i0["samplerate"]} Hz' if i0["samplerate"] else "—"),
                    (tr("info.bits"), str(i0["bits"] or "—")), (tr("info.channels"), str(i0["channels"] or "—")),
                    (tr("info.writable"), tr("yes") if i0["writable"] else tr("no"))]
        else:
            rows = [(tr("info.file"), "\n".join(os.path.basename(p) for p in self.paths[:30]))]
        for k, v in rows:
            lab = QLabel(v)
            lab.setTextInteractionFlags(Qt.TextSelectableByMouse)
            lab.setWordWrap(True)
            fl.addRow(muted(k), lab)
        self.tabs.addTab(info, tr("tag.fileinfo"))

        self.status = muted(tr("tag.saved_in_file") if all(i["writable"] for i in self.infos) else tr("tag.readonly"))
        save = primary(tr("btn.save"))
        save.clicked.connect(self.save)
        cancel = QPushButton(tr("btn.cancel"))
        cancel.clicked.connect(self.reject)
        self.footer(lay, cancel, save, left=self.status)
        save.setEnabled(any(i["writable"] for i in self.infos))
        self._show_cover(cm_tags.cover(self.paths[0]) if self.paths else None)
        self._lyrics_changed(initial=True)

    def _val(self, key):
        return self.edits[key].text().strip()

    def _show_cover(self, data):
        self.cover.set_cover(data, self._val("album") or "x")
        if data:
            img = QImage.fromData(data)
            self.cover_info.setText(f"{img.width()}×{img.height()} · {len(data) // 1024} KB" +
                                    (f" · {tr('tag.all_files')}" if self.multi else ""))
        else:
            self.cover_info.setText(tr("tag.no_cover"))

    def cover_from_file(self):
        fn, _ = QFileDialog.getOpenFileName(self, tr("btn.cover_file"), os.path.dirname(self.paths[0]),
                                            "Images (*.jpg *.jpeg *.png *.webp *.bmp)")
        if fn:
            self._set_cover(fn)

    def _set_cover(self, fn):
        img = QImage(fn)
        if img.isNull():
            return
        self.new_cover = _to_jpeg(img)
        self._show_cover(self.new_cover)

    def cover_online(self):
        if not ask_online(self):
            return
        guess = cover_search_fields(self.paths[0], dict(self.infos[0], artist=self._val("artist"),
                                                        albumartist=self._val("albumartist"),
                                                        album=self._val("album"), title=self._val("title")))
        dlg = CoverPicker(self, *guess)
        ok = dlg.exec()
        data = dlg.result_data
        dlg.deleteLater()
        if ok and data:
            img = QImage.fromData(data)
            self.new_cover = _to_jpeg(img) if not img.isNull() else data
            self._show_cover(self.new_cover)

    def cover_remove(self):
        self.new_cover = b""
        self._show_cover(None)

    def cover_export(self):
        data = self.new_cover if self.new_cover else cm_tags.cover(self.paths[0])
        if not data:
            return
        ext = ".png" if data[:4] == b"\x89PNG" else ".jpg"
        fn, _ = QFileDialog.getSaveFileName(self, tr("btn.export"), os.path.join(os.path.dirname(self.paths[0]), "cover" + ext))
        if fn:
            with open(fn, "wb") as fh:
                fh.write(data)

    def musicbrainz(self):
        if not ask_online(self):
            return
        i0 = self.infos[0]
        dlg = MusicBrainzPicker(self, self._val("artist") or i0["artist"], self._val("title") or i0["title"] or
                                title_from_filename(self.paths[0]).get("title", ""), self._val("album"), i0["duration"])
        if dlg.exec() and dlg.result_row:
            r = dlg.result_row
            keys = ["artist", "albumartist", "album", "year", "genre"] + ([] if self.multi else ["title", "track"])
            for k in keys:
                if r.get(k):
                    self.edits[k].setText(r[k])
                    self.changed.add(k)

    def from_filename(self):
        if self.multi:
            self._multi_names = True
            self.status.setText(tr("tag.names_applied"))
            return
        for k, v in title_from_filename(self.paths[0]).items():
            self.edits[k].setText(v)
            self.changed.add(k)

    def lyrics_online(self):
        if not ask_online(self):
            return
        info = dict(self.infos[0], artist=self._val("artist"), title=self._val("title"), album=self._val("album"))
        dlg = LyricsDialog(self, self.paths[0], info, self.lyrics.toPlainText(), pick_only=True)
        if dlg.exec() and dlg.result_text is not None:
            self.lyrics.setPlainText(dlg.result_text)

    def _lyrics_changed(self, initial=False):
        lines, synced = parse_lrc(self.lyrics.toPlainText())
        self.lyr_kind.setText(tr("lyr.synced", n=len(lines)) if synced else (tr("lyr.plain", n=len(lines)) if lines else ""))
        if not initial:
            self.new_lyrics = self.lyrics.toPlainText()

    def save(self):
        errors = []
        names = getattr(self, "_multi_names", False)
        for path, info in zip(self.paths, self.infos):
            if not info["writable"]:
                continue
            if self.multi:
                values = {k: self._val(k) for k in self.changed}
                if names:
                    values.update(title_from_filename(path))
            else:
                values = {k: self._val(k) for k in cm_tags.FIELDS if self._val(k) != (info.get(k) or "")}
            lyrics = None
            if self.new_lyrics is not None and not self.multi:
                lyrics = self.new_lyrics.strip()
            if not values and self.new_cover is None and lyrics is None:
                continue

            def do(path=path, values=values, lyrics=lyrics):
                cm_tags.write(path, values, cover=self.new_cover, lyrics=lyrics)
                if lyrics is not None and os.path.isfile(cm_tags.lrc_path(path)):
                    with open(cm_tags.lrc_path(path), "w", encoding="utf-8") as fh:
                        fh.write(lyrics)
            try:
                if self.release_file:
                    self.release_file(path, do)
                else:
                    do()
            except Exception as e:
                errors.append(f"{os.path.basename(path)}: {e}")
        if errors:
            QMessageBox.warning(self, APP_NAME, tr("msg.save_failed") + "\n\n" + "\n".join(errors[:12]))
        self.saved.emit(self.paths)
        self.accept()


def _to_jpeg(img, max_side=1400):
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    if max(img.width(), img.height()) > max_side:
        img = img.scaled(max_side, max_side, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    if img.hasAlphaChannel():
        img = img.convertToFormat(QImage.Format_RGB32)
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "JPG", 92)
    return bytes(ba)


# ------------------------------------------------------------------ rename files from tags
class RenameDialog(Dialog):
    PATTERNS = ["{track:02} - {title}", "{artist} - {title}", "{track:02} - {artist} - {title}", "{album} - {track:02} - {title}"]

    def __init__(self, parent, paths, release_file=None):
        super().__init__(parent, tr("ren.title"), "convert", "indigo")
        self.resize(860, 520)
        self.paths = paths
        self.release_file = release_file
        self.renamed = []
        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("ren.pattern")))
        self.pattern = QComboBox()
        self.pattern.setEditable(True)
        self.pattern.addItems(self.PATTERNS)
        self.pattern.currentTextChanged.connect(self.preview)
        row.addWidget(self.pattern, 1)
        lay.addLayout(row)
        lay.addWidget(muted(tr("ren.help")))
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels([tr("ren.old"), tr("ren.new")])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        lay.addWidget(self.table, 1)
        ok = primary(tr("ren.do"))
        ok.clicked.connect(self.apply)
        cancel = QPushButton(tr("btn.cancel"))
        cancel.clicked.connect(self.reject)
        self.footer(lay, cancel, ok)
        self.infos = {p: cm_tags.read(p) for p in paths}
        self.preview()

    def new_name(self, path):
        i = self.infos[path]
        try:
            n = int(str(i.get("track", "")).split("/")[0] or 0)
        except ValueError:
            n = 0
        vals = {k: (i.get(k) or "") for k in cm_tags.FIELDS}
        vals["track"] = n
        try:
            name = self.pattern.currentText().format(**vals)
        except (KeyError, ValueError, IndexError):
            return None
        name = re.sub(r'[\\/:*?"<>|]+', "_", name).strip(" .")
        if not name or not (i.get("title")):
            return None
        return os.path.join(os.path.dirname(path), name + os.path.splitext(path)[1])

    def preview(self):
        self.table.setRowCount(len(self.paths))
        for r, p in enumerate(self.paths):
            n = self.new_name(p)
            self.table.setItem(r, 0, QTableWidgetItem(os.path.basename(p)))
            it = QTableWidgetItem(os.path.basename(n) if n else tr("ren.skip"))
            if not n:
                it.setForeground(QColor("#c62828"))
            self.table.setItem(r, 1, it)

    def apply(self):
        errors = []
        for p in self.paths:
            n = self.new_name(p)
            if not n or n == p:
                continue
            if os.path.exists(n):
                errors.append(f"{os.path.basename(n)}: {tr('ren.exists')}")
                continue

            def do(p=p, n=n):
                os.rename(p, n)
                for side in (".lrc", ".srt"):
                    old_side = os.path.splitext(p)[0] + side
                    if os.path.exists(old_side):
                        os.rename(old_side, os.path.splitext(n)[0] + side)
            try:
                if self.release_file:
                    self.release_file(p, do, new_path=n)
                else:
                    do()
                self.renamed.append((p, n))
            except OSError as e:
                errors.append(f"{os.path.basename(p)}: {e}")
        if errors:
            QMessageBox.warning(self, APP_NAME, "\n".join(errors[:15]))
        self.accept()


# ------------------------------------------------------------------ settings
class SettingsDialog(Dialog):
    def __init__(self, parent, page=0):
        super().__init__(parent, tr("set.title"), "gear", "gray")
        self.resize(900, 620)
        outer = QVBoxLayout(self)
        body = QHBoxLayout()
        self.nav = QListWidget()
        self.nav.setObjectName("SideList")
        self.nav.setFixedWidth(200)
        self.stack = QStackedWidget()
        body.addWidget(self.nav)
        body.addWidget(self.stack, 1)
        outer.addLayout(body, 1)
        self.folders_changed = False

        # appearance
        p = QWidget()
        pl = QVBoxLayout(p)
        pl.addWidget(self._h(tr("set.appearance")))
        pl.addWidget(muted(tr("set.theme_help")))
        cards = QHBoxLayout()
        self.theme_group = QButtonGroup(self)
        for key, glyph, colour in (("system", "theme", "indigo"), ("light", "sun", "orange"), ("dark", "moon", "blue")):
            b = QPushButton(cm_icons.glossy(glyph, colour, 34), "  " + tr("theme." + key) + "\n  " + tr("theme." + key + "_desc"))
            b.setObjectName("Choice")
            b.setIconSize(QSize(34, 34))
            b.setCheckable(True)
            b.setMinimumHeight(64)
            b.setChecked(settings.get("theme") == key)
            b.mode = key
            self.theme_group.addButton(b)
            cards.addWidget(b)
        pl.addLayout(cards)
        pl.addSpacing(12)
        pl.addWidget(QLabel(f"<b>{tr('set.accent')}</b>"))
        acc = QHBoxLayout()
        self.accent_group = QButtonGroup(self)
        for colour in cm_theme.ACCENTS:
            b = QPushButton()
            b.setCheckable(True)
            b.setFixedSize(34, 34)
            b.setStyleSheet(f"QPushButton{{background:{colour};border-radius:17px;border:3px solid transparent;}}"
                            f"QPushButton:checked{{border:3px solid palette(text);}}")
            b.setChecked(settings.get("accent") == colour)
            b.colour = colour
            self.accent_group.addButton(b)
            acc.addWidget(b)
        acc.addStretch(1)
        pl.addLayout(acc)
        pl.addSpacing(12)
        pl.addWidget(self._h(tr("set.language")))
        pl.addWidget(muted(tr("set.language_help")))
        self.lang = QComboBox()
        for code, name in LANGUAGES:
            self.lang.addItem(name, code)
        self.lang.setCurrentIndex(max(0, self.lang.findData(settings.get("language") or "en")))
        self.lang.setMaximumWidth(260)
        pl.addWidget(self.lang)
        pl.addStretch(1)
        self._page(tr("set.appearance"), "theme", "indigo", p)

        # playback
        p = QWidget()
        pl = QVBoxLayout(p)
        pl.addWidget(self._h(tr("set.playback")))
        self.chk_queue = QCheckBox(tr("set.remember_queue"))
        self.chk_queue.setChecked(settings.get("remember_queue", True))
        pl.addWidget(self.chk_queue)
        self.chk_resume = QCheckBox(tr("set.resume"))
        self.chk_resume.setChecked(settings.get("resume", True))
        pl.addWidget(self.chk_resume)
        pl.addSpacing(10)
        pl.addWidget(QLabel(f"<b>{tr('set.snapshots')}</b>"))
        row = QHBoxLayout()
        self.snap = QLineEdit(settings.get("snapshot_dir") or default_snapshot_dir())
        b = QPushButton(tr("btn.browse"))
        b.clicked.connect(lambda: self._pick_dir(self.snap))
        row.addWidget(self.snap, 1)
        row.addWidget(b)
        pl.addLayout(row)
        pl.addStretch(1)
        self._page(tr("set.playback"), "play", "green", p)

        # library
        p = QWidget()
        pl = QVBoxLayout(p)
        pl.addWidget(self._h(tr("set.library")))
        pl.addWidget(muted(tr("set.library_help")))
        self.folders = QListWidget()
        for f in settings.get("library_folders", []):
            self.folders.addItem(f)
        pl.addWidget(self.folders, 1)
        row = QHBoxLayout()
        add = QPushButton(tr("btn.add_folder"))
        add.clicked.connect(self._add_folder)
        rem = QPushButton(tr("btn.remove"))
        rem.clicked.connect(self._remove_folder)
        row.addWidget(add)
        row.addWidget(rem)
        row.addStretch(1)
        pl.addLayout(row)
        self.chk_scan = QCheckBox(tr("set.scan_on_start"))
        self.chk_scan.setChecked(settings.get("scan_on_start", True))
        pl.addWidget(self.chk_scan)
        self.chk_watch = QCheckBox(tr("set.watch"))
        self.chk_watch.setChecked(settings.get("watch_folders", True))
        pl.addWidget(self.chk_watch)
        hid = QPushButton(cm_icons.glossy("undo", "orange", 18), tr("act.hidden_items") + "…")
        hid.clicked.connect(lambda: hasattr(self.parent(), "show_hidden") and self.parent().show_hidden())
        hrow = QHBoxLayout()
        hrow.addWidget(hid)
        hrow.addStretch(1)
        pl.addLayout(hrow)
        self._page(tr("set.library"), "library", "blue", p)

        # online
        p = QWidget()
        pl = QVBoxLayout(p)
        pl.addWidget(self._h(tr("set.online")))
        self.chk_online = QCheckBox(tr("set.online_enable"))
        self.chk_online.setChecked(settings.get("online", True))
        pl.addWidget(self.chk_online)
        self.chk_auto = QCheckBox(tr("set.auto_lyrics"))
        self.chk_auto.setChecked(settings.get("auto_lyrics", True))
        pl.addWidget(self.chk_auto)
        self.chk_embed = QCheckBox(tr("lyr.embed"))
        self.chk_embed.setChecked(settings.get("embed_lyrics", True))
        pl.addWidget(self.chk_embed)
        self.chk_lrc = QCheckBox(tr("lyr.lrcfile"))
        self.chk_lrc.setChecked(settings.get("save_lrc_file", True))
        pl.addWidget(self.chk_lrc)
        pl.addSpacing(10)
        note = muted(tr("set.online_note"))
        note.setWordWrap(True)
        pl.addWidget(note)
        pl.addStretch(1)
        self._page(tr("set.online"), "globe", "teal", p)

        # shortcuts
        p = QWidget()
        pl = QVBoxLayout(p)
        pl.addWidget(self._h(tr("set.shortcuts")))
        pl.addWidget(shortcuts_table(), 1)
        self._page(tr("set.shortcuts"), "keyboard", "gray", p)

        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(page)
        reset = QPushButton(tr("btn.reset"))
        reset.clicked.connect(self._reset)
        ok = primary(tr("btn.ok"))
        ok.clicked.connect(self.save)
        cancel = QPushButton(tr("btn.cancel"))
        cancel.clicked.connect(self.reject)
        bar = QHBoxLayout()
        bar.addWidget(reset)
        bar.addStretch(1)
        bar.addWidget(cancel)
        bar.addWidget(ok)
        outer.addLayout(bar)

    def _h(self, text):
        lab = QLabel(text)
        lab.setObjectName("H1")
        return lab

    def _page(self, title, glyph, colour, widget):
        it = QListWidgetItem(cm_icons.glossy(glyph, colour, 22), title)
        it.setSizeHint(QSize(10, 34))
        self.nav.addItem(it)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        widget.setContentsMargins(16, 6, 16, 6)
        scroll.setWidget(widget)
        self.stack.addWidget(scroll)

    def _pick_dir(self, edit):
        d = QFileDialog.getExistingDirectory(self, "", edit.text())
        if d:
            edit.setText(os.path.normpath(d))

    def _add_folder(self):
        d = QFileDialog.getExistingDirectory(self, tr("btn.add_folder"))
        if d:
            d = os.path.normpath(d)
            if not self.folders.findItems(d, Qt.MatchExactly):
                self.folders.addItem(d)
                self.folders_changed = True

    def _remove_folder(self):
        for it in self.folders.selectedItems():
            self.folders.takeItem(self.folders.row(it))
            self.folders_changed = True

    def _reset(self):
        if QMessageBox.question(self, APP_NAME, tr("set.reset_q")) == QMessageBox.Yes:
            for b in self.theme_group.buttons():
                b.setChecked(b.mode == "system")
            for b in self.accent_group.buttons():
                b.setChecked(b.colour == cm_theme.ACCENTS[0])
            for c in (self.chk_queue, self.chk_scan, self.chk_online, self.chk_auto, self.chk_embed, self.chk_lrc,
                      self.chk_resume, self.chk_watch):
                c.setChecked(True)
            self.snap.setText(default_snapshot_dir())

    def save(self):
        b = self.theme_group.checkedButton()
        if b:
            settings["theme"] = b.mode
        a = self.accent_group.checkedButton()
        if a:
            settings["accent"] = a.colour
        settings["language"] = self.lang.currentData()
        settings["remember_queue"] = self.chk_queue.isChecked()
        settings["snapshot_dir"] = self.snap.text().strip()
        old = settings.get("library_folders", [])
        settings["library_folders"] = [self.folders.item(i).text() for i in range(self.folders.count())]
        self.removed_folders = [f for f in old if f not in settings["library_folders"]]
        settings["scan_on_start"] = self.chk_scan.isChecked()
        settings["watch_folders"] = self.chk_watch.isChecked()
        settings["resume"] = self.chk_resume.isChecked()
        settings["online"] = self.chk_online.isChecked()
        settings["auto_lyrics"] = self.chk_auto.isChecked()
        settings["embed_lyrics"] = self.chk_embed.isChecked()
        settings["save_lrc_file"] = self.chk_lrc.isChecked()
        settings.save()
        self.accept()


def default_snapshot_dir():
    from PySide6.QtCore import QStandardPaths
    base = QStandardPaths.writableLocation(QStandardPaths.PicturesLocation) or os.path.expanduser("~")
    return os.path.join(base, APP_NAME)


SHORTCUTS = [("Space", "act.play"), ("Ctrl+O", "act.open_file"), ("Ctrl+Shift+O", "act.open_folder"),
             ("Ctrl+U", "act.open_url"), ("→ / ←", "sc.seek5"), ("Ctrl+→ / Ctrl+←", "sc.seek30"),
             ("↑ / ↓", "sc.volume"), ("M", "act.mute"), ("N / Ctrl+N", "act.next"), ("P / Ctrl+P", "act.prev"),
             ("S", "act.stop"), ("[ / ]", "sc.speed"), ("F11 / Enter", "act.fullscreen"), ("Esc", "sc.exit_full"),
             ("Ctrl+M", "act.mini"), ("Ctrl+T", "act.edit_tags"), ("Ctrl+L", "act.find_lyrics"),
             ("Ctrl+F", "sc.search"), ("Ctrl+S", "act.save_playlist"), ("F5", "act.rescan"), ("F12", "act.snapshot"),
             ("Ctrl+,", "act.settings"), ("Home", "sc.start_over"), ("Del", "act.remove_lib"),
             ("Shift+Del", "act.delete_files"), ("F2", "sc.rename"), ("Ctrl + wheel", "lib.tile_size")]


def shortcuts_table():
    t = QTableWidget(len(SHORTCUTS), 2)
    t.setHorizontalHeaderLabels([tr("sc.key"), tr("sc.action")])
    t.verticalHeader().hide()
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
    t.setColumnWidth(0, 180)
    for i, (key, act) in enumerate(SHORTCUTS):
        t.setItem(i, 0, QTableWidgetItem(key))
        t.setItem(i, 1, QTableWidgetItem(tr(act).replace("&", "")))
    return t


class HiddenDialog(Dialog):
    """Tools > Hidden items: tracks and videos taken out of the library (files untouched). Restore brings them
    back with their ratings, play counts and playlist places."""
    def __init__(self, parent):
        super().__init__(parent, tr("hid.title"), "undo", "orange")
        self.resize(940, 580)
        self.changed = False
        lay = QVBoxLayout(self)
        note = muted(tr("hid.note"))
        note.setWordWrap(True)
        lay.addWidget(note)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText(tr("search.placeholder"))
        self.filter.textChanged.connect(self._apply_filter)
        lay.addWidget(self.filter)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([tr("col.title"), tr("col.artist"), tr("col.album"), tr("hid.when"),
                                              tr("col.path")])
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSortingEnabled(True)
        h = self.table.horizontalHeader()
        for i, w in enumerate([220, 160, 170, 120]):
            self.table.setColumnWidth(i, w)
        h.setStretchLastSection(True)
        lay.addWidget(self.table, 1)
        self.count = muted()
        restore = primary(tr("hid.restore"))
        restore.clicked.connect(self._restore_selected)
        restore_all = QPushButton(tr("hid.restore_all"))
        restore_all.clicked.connect(self._restore_all)
        close = QPushButton(tr("btn.close"))
        close.clicked.connect(self.accept)
        self.footer(lay, restore_all, restore, close, left=self.count)
        self.load()

    def load(self):
        rows = cm_library.hidden_rows()
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            when = time.strftime("%Y-%m-%d", time.localtime(r["hidden_at"])) if r.get("hidden_at") else ""
            for j, v in enumerate([r.get("title") or os.path.basename(r["path"]), r.get("artist") or "",
                                   r.get("album") or "", when, r["path"]]):
                it = QTableWidgetItem(v)
                it.setData(Qt.UserRole, r["path"])
                self.table.setItem(i, j, it)
        self.table.setSortingEnabled(True)
        self.count.setText(tr("hid.count", n=len(rows)))
        self._apply_filter(self.filter.text())

    def _apply_filter(self, text):
        words = text.lower().split()
        for i in range(self.table.rowCount()):
            line = " ".join((self.table.item(i, j).text() if self.table.item(i, j) else "") for j in range(5)).lower()
            self.table.setRowHidden(i, not all(w in line for w in words))

    def _paths(self, rows):
        return [self.table.item(r, 0).data(Qt.UserRole) for r in rows if self.table.item(r, 0)]

    def _restore_selected(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        if rows:
            cm_library.unhide(self._paths(rows))
            self.changed = True
            self.load()

    def _restore_all(self):
        rows = [i for i in range(self.table.rowCount()) if not self.table.isRowHidden(i)]
        if rows and QMessageBox.question(self, APP_NAME, tr("hid.restore_all_q", n=len(rows))) == QMessageBox.Yes:
            cm_library.unhide(self._paths(rows))
            self.changed = True
            self.load()


class BarList(QWidget):
    """Horizontal bars, one hue, value written at the end of each bar (statistics)."""
    def __init__(self, items, fmt=str, parent=None):
        super().__init__(parent)
        self.items = list(items)
        self.fmt = fmt
        self.setMinimumHeight(max(1, len(self.items)) * 26 + 4)

    def paintEvent(self, _e):
        from PySide6.QtGui import QFontMetrics, QPainter
        c = cm_theme.colours()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        fm = QFontMetrics(self.font())
        if not self.items:
            p.setPen(QColor(c["muted"]))
            p.drawText(self.rect(), Qt.AlignLeft | Qt.AlignVCenter, tr("stats.nothing_yet"))
            return
        label_w = min(int(self.width() * 0.45), max(fm.horizontalAdvance(str(k)) for k, _v in self.items) + 12)
        top = max(v for _k, v in self.items) or 1
        val_w = max(fm.horizontalAdvance(self.fmt(v)) for _k, v in self.items) + 10
        bar_room = max(10, self.width() - label_w - val_w - 4)
        for i, (k, v) in enumerate(self.items):
            y = i * 26 + 2
            p.setPen(QColor(c["text"]))
            p.drawText(QRectF(0, y, label_w - 8, 22), Qt.AlignLeft | Qt.AlignVCenter,
                       fm.elidedText(str(k), Qt.ElideRight, label_w - 10))
            w = max(3, bar_room * v / top)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(c["accent"]))
            p.drawRoundedRect(QRectF(label_w, y + 6, w, 10), 4, 4)
            p.setPen(QColor(c["muted"]))
            p.drawText(QRectF(label_w + w + 6, y, val_w, 22), Qt.AlignLeft | Qt.AlignVCenter, self.fmt(v))


class MonthChart(QWidget):
    """Listening time per month: vertical bars, one hue, hover shows the exact time."""
    def __init__(self, months, parent=None):
        super().__init__(parent)
        self.months = months
        self.setMinimumHeight(190)
        self.setMouseTracking(True)
        self._bars = []

    def paintEvent(self, _e):
        from PySide6.QtCore import QLocale
        from PySide6.QtGui import QPainter, QPen
        c = cm_theme.colours()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        loc = QLocale(settings.get("language") or "en")
        top = max((s for _y, _m, s in self.months), default=0)
        base_y = self.height() - 24
        avail_h = base_y - 22
        n = max(1, len(self.months))
        slot = self.width() / n
        bw = min(34, slot * 0.6)
        p.setPen(QPen(QColor(c["border"]), 1))
        p.drawLine(0, base_y, self.width(), base_y)
        self._bars = []
        for i, (y, m, secs) in enumerate(self.months):
            x = i * slot + (slot - bw) / 2
            h = (avail_h * secs / top) if top else 0
            if secs and h < 3:
                h = 3
            rect = QRectF(x, base_y - h, bw, h)
            self._bars.append((rect.adjusted(-4, -avail_h, 4, 0), y, m, secs))
            if h:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(c["accent"]))
                p.drawRoundedRect(rect, 4, 4)
                p.fillRect(QRectF(x, base_y - min(h, 4), bw, min(h, 4)), QColor(c["accent"]))
            p.setPen(QColor(c["muted"]))
            p.drawText(QRectF(i * slot, base_y + 4, slot, 18), Qt.AlignCenter, loc.monthName(m, QLocale.ShortFormat))
        if top:
            i = max(range(len(self.months)), key=lambda k: self.months[k][2])
            r = self._bars[i][0]
            p.setPen(QColor(c["text"]))
            p.drawText(QRectF(r.left() - 30, base_y - avail_h * self.months[i][2] / top - 20, r.width() + 60, 18),
                       Qt.AlignCenter, _hours(self.months[i][2]))
        if not top:
            p.setPen(QColor(c["muted"]))
            p.drawText(QRectF(0, 0, self.width(), base_y), Qt.AlignCenter, tr("stats.nothing_yet"))

    def mouseMoveEvent(self, e):
        from PySide6.QtCore import QLocale
        from PySide6.QtWidgets import QToolTip
        loc = QLocale(settings.get("language") or "en")
        for rect, y, m, secs in self._bars:
            if rect.contains(e.position()):
                QToolTip.showText(e.globalPosition().toPoint(), f"{loc.monthName(m)} {y}: {_hours(secs)}", self)
                return
        QToolTip.hideText()


def _hours(secs):
    secs = int(secs or 0)
    h, m = secs // 3600, (secs % 3600) // 60
    return f"{h} h {m:02d} min" if h else f"{m} min"


class StatsDialog(Dialog):
    def __init__(self, parent):
        super().__init__(parent, tr("stats.title"), "eq", "green")
        self.resize(980, 720)
        s = cm_library.statistics()
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(14)
        tiles = QGridLayout()
        tiles.setSpacing(10)
        cards = [("stats.tracks", f'{s["music"]:,}'.replace(",", " ")), ("stats.albums", f'{s["albums"]:,}'.replace(",", " ")),
                 ("stats.artists", f'{s["artists"]:,}'.replace(",", " ")), ("stats.videos", f'{s["videos"]:,}'.replace(",", " ")),
                 ("stats.size", f'{s["size"] / 1073741824:.1f} GB'), ("stats.length", _hours(s["duration"])),
                 ("stats.plays", f'{s["plays"]:,}'.replace(",", " ")), ("stats.listened", _hours(s["listened"]))]
        for i, (key, val) in enumerate(cards):
            card = QFrame()
            card.setObjectName("Card")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(14, 10, 14, 10)
            v = QLabel(val)
            v.setStyleSheet("font-size: 17pt; font-weight: 700; background: transparent;")
            k = muted(tr(key))
            k.setStyleSheet("background: transparent;")
            cl.addWidget(v)
            cl.addWidget(k)
            tiles.addWidget(card, i // 4, i % 4)
        lay.addLayout(tiles)
        lay.addWidget(self._h(tr("stats.per_month")))
        lay.addWidget(MonthChart(s["months"]))
        since = s.get("history_since")
        lay.addWidget(muted(tr("stats.history_since", date=time.strftime("%Y-%m-%d", time.localtime(since)))
                            if since else tr("stats.history_note")))
        grid = QGridLayout()
        grid.setHorizontalSpacing(28)
        grid.setVerticalSpacing(6)
        plays = lambda v: tr("stats.n_plays", n=v)
        for i, (key, items) in enumerate((("stats.top_artists", s["top_artists"]), ("stats.top_tracks", s["top_tracks"]),
                                          ("stats.top_albums", s["top_albums"]), ("stats.top_genres", s["top_genres"]))):
            col = QVBoxLayout()
            col.addWidget(self._h(tr(key)))
            col.addWidget(BarList(items, plays))
            col.addStretch(1)
            grid.addLayout(col, i // 2, i % 2)
        lay.addLayout(grid)
        lay.addStretch(1)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)
        ok = primary(tr("btn.close"))
        ok.clicked.connect(self.accept)
        self.footer(outer, ok)

    def _h(self, text):
        lab = QLabel(text)
        lab.setObjectName("H1")
        return lab


class TextDialog(Dialog):
    def __init__(self, parent, title, text, glyph="list", colour="green"):
        super().__init__(parent, title, glyph, colour)
        self.resize(760, 560)
        lay = QVBoxLayout(self)
        ed = QPlainTextEdit(text)
        ed.setReadOnly(True)
        ed.setStyleSheet("font-family: Consolas, 'DejaVu Sans Mono', monospace; font-size: 9pt;")
        lay.addWidget(ed, 1)
        ok = primary(tr("btn.close"))
        ok.clicked.connect(self.accept)
        self.footer(lay, ok)


def read_doc(name):
    for enc in ("utf-8", "latin-1"):
        try:
            with open(os.path.join(resource_dir(), name), encoding=enc) as fh:
                return fh.read()
        except (OSError, UnicodeDecodeError):
            continue
    return ""


THIRD_PARTY = """Claudius Multimedia is built with these free components:

  Qt 6 / PySide6 (Qt for Python)   GNU LGPL v3      https://www.qt.io  https://doc.qt.io/qtforpython
  FFmpeg (inside Qt Multimedia)    GNU LGPL v2.1+   https://ffmpeg.org
  Mutagen (audio tags)             GNU GPL v2+      https://github.com/quodlibet/mutagen
  Python                           PSF licence      https://www.python.org

Online services used only when you ask for covers, lyrics or tags (or for the playing track's lyrics when
"Download lyrics automatically" is on in Settings > Online):
  LRCLIB (lyrics)                  https://lrclib.net
  MusicBrainz (tags)               https://musicbrainz.org   - data CC0
  Cover Art Archive (covers)       https://coverartarchive.org
  iTunes Search API (covers)       https://itunes.apple.com
  Deezer API (covers)              https://developers.deezer.com
Cover images and lyrics belong to their owners; they are downloaded for your personal use.
"""


class AboutPage(QWidget):
    def __init__(self, parent=None, open_doc=None):
        super().__init__(parent)
        self.setObjectName("AboutPage")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.open_doc = open_doc
        self.build()

    def build(self):
        old = self.layout()
        if old is not None:
            QWidget().setLayout(old)  # drop the old layout and its widgets
        outer = QVBoxLayout(self)
        outer.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)
        card = QFrame()
        card.setObjectName("Card")
        card.setFixedWidth(780)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        head = QFrame()
        head.setObjectName("CardHead")
        hl = QHBoxLayout(head)
        hl.setContentsMargins(30, 26, 30, 26)
        hl.setSpacing(22)
        logo = QLabel()
        logo.setPixmap(cm_icons.logo_pixmap(96))
        hl.addWidget(logo)
        txt = QVBoxLayout()
        name = QLabel(APP_NAME)
        name.setStyleSheet("font-size: 20pt; font-weight: 800; background: transparent;")
        ver = muted(tr("about.version", version=APP_VERSION))
        ver.setStyleSheet("background: transparent;")
        by = QLabel(tr("about.created_by", authors="<b>Michal Czapla</b> &amp; <b>Claude AI</b>"))
        by.setStyleSheet("font-size: 12pt; background: transparent;")
        txt.addStretch(1)
        txt.addWidget(name)
        txt.addWidget(ver)
        txt.addSpacing(8)
        txt.addWidget(by)
        txt.addStretch(1)
        hl.addLayout(txt, 1)
        cl.addWidget(head)
        mid = QHBoxLayout()
        mid.setContentsMargins(30, 20, 30, 20)
        mid.setSpacing(26)
        for glyph, colour, title_key, body_key in (("heartf", "green", "about.freeware", "about.freeware_text"),
                                                    ("list", "blue", "about.built_with", "about.built_with_text")):
            col = QVBoxLayout()
            h = QHBoxLayout()
            ic = QLabel()
            ic.setPixmap(cm_icons.glossy(glyph, colour, 26).pixmap(26, 26))
            h.addWidget(ic)
            t = QLabel(f"<b>{tr(title_key)}</b>")
            t.setStyleSheet("font-size: 11pt;")
            h.addWidget(t)
            h.addStretch(1)
            col.addLayout(h)
            body = muted(tr(body_key) + ("\n\n" + tr("about.license") if glyph == "heartf" else ""))
            body.setWordWrap(True)
            col.addWidget(body)
            col.addStretch(1)
            mid.addLayout(col, 1)
        cl.addLayout(mid)
        foot = QFrame()
        foot.setObjectName("CardFoot")
        fl = QHBoxLayout(foot)
        fl.setContentsMargins(30, 12, 30, 12)
        fl.addWidget(muted("© 2026 Michal Czapla"), 1)
        for key, doc in (("about.third_party", "third"), ("about.freeware_notice", "freeware"), ("about.website", "web")):
            b = QPushButton(tr(key))
            b.clicked.connect(lambda _=False, d=doc: self.open_doc and self.open_doc(d))
            if doc == "web":
                b.setObjectName("Primary")
            fl.addWidget(b)
        cl.addWidget(foot)
        row.addWidget(card)
        row.addStretch(1)
        outer.addLayout(row)
        outer.addStretch(1)


def open_url(url):
    QDesktopServices.openUrl(QUrl(url))


__all__ = ["CoverPicker", "MusicBrainzPicker", "LyricsDialog", "TagEditor", "RenameDialog", "SettingsDialog",
           "TextDialog", "AboutPage", "THIRD_PARTY", "read_doc", "open_url", "default_snapshot_dir", "ask_online",
           "APP_AUTHORS", "APP_URL"]
