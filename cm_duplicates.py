"""Claudius Multimedia - duplicate finder: the same song more than once in the library (same artist and title,
similar length). The best copy is kept by default (lossless > higher resolution > higher bit rate, files that
exist before missing ones); the other copies can be removed from the library or moved to the Recycle Bin.
Play counts, ratings and favourites of removed copies are added to the copy that stays."""
import os
import re
import unicodedata

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QHBoxLayout, QHeaderView, QMessageBox, QPushButton,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout)

import cm_library
import cm_theme
from cm_core import APP_NAME, fmt_time, tr
from cm_dialogs import Dialog, primary
from cm_widgets import LOSSLESS, muted

_NOISE = re.compile(r"[\(\[][^\)\]]*(remaster|version|explicit|album|single edit|mono|stereo)[^\)\]]*[\)\]]"
                    r"|\s-\s.*remaster.*$", re.I)


def norm(text):
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    text = _NOISE.sub("", text)
    text = re.sub(r"^the\s+", "", text.strip())
    text = re.sub(r"[^\w]+", " ", text)
    return " ".join(text.split())


def quality(r):
    lossless = (r.get("codec") or "").upper() in LOSSLESS
    return (not r.get("missing"), lossless, r.get("bits") or 0, r.get("samplerate") or 0, r.get("bitrate") or 0,
            r.get("rating") or 0, r.get("play_count") or 0, -len(r["path"]))


def find_groups(compare_length=True, compare_album=False):
    con = cm_library.connect()
    try:
        rows = [dict(r) for r in con.execute("SELECT * FROM tracks WHERE hidden=0 AND kind='audio' AND title<>''")]
    finally:
        con.close()
    buckets = {}
    for r in rows:
        key = (norm(r.get("artist") or r.get("albumartist")), norm(r.get("title")))
        if not key[1]:
            continue
        if compare_album:
            key += (norm(r.get("album")),)
        buckets.setdefault(key, []).append(r)
    groups = []
    for items in buckets.values():
        if len(items) < 2:
            continue
        if not compare_length:
            groups.append(items)
            continue
        known = sorted((r for r in items if r.get("duration")), key=lambda r: r["duration"])
        unknown = [r for r in items if not r.get("duration")]
        clusters, cur = [], []
        for r in known:
            if cur and r["duration"] - cur[-1]["duration"] > 3.0:
                clusters.append(cur)
                cur = []
            cur.append(r)
        if cur:
            clusters.append(cur)
        if unknown:
            if clusters:
                clusters[0].extend(unknown)
            else:
                clusters.append(unknown)
        groups.extend(c for c in clusters if len(c) > 1)
    for g in groups:
        g.sort(key=quality, reverse=True)
    groups.sort(key=lambda g: (norm(g[0].get("artist")), norm(g[0].get("title"))))
    return groups


def _fmt(r):
    parts = [r.get("codec") or ""]
    if r.get("bits") and r.get("samplerate"):
        parts.append(f'{r["bits"]}/{r["samplerate"] // 1000}')
    elif r.get("bitrate"):
        parts.append(f'{r["bitrate"]} kbps')
    return " ".join(p for p in parts if p)


class DuplicatesDialog(Dialog):
    def __init__(self, main):
        super().__init__(main, tr("dup.title"), "grid", "orange")
        self.main = main
        self.changed = False
        self.groups = []
        self.resize(1080, 660)
        lay = QVBoxLayout(self)
        note = muted(tr("dup.note"))
        note.setWordWrap(True)
        lay.addWidget(note)
        opts = QHBoxLayout()
        self.chk_len = QCheckBox(tr("dup.compare_length"))
        self.chk_len.setChecked(True)
        self.chk_album = QCheckBox(tr("dup.compare_album"))
        for c in (self.chk_len, self.chk_album):
            c.toggled.connect(lambda _on: self.search())
            opts.addWidget(c)
        opts.addStretch(1)
        best = QPushButton(tr("dup.select_best"))
        best.clicked.connect(self._check_best)
        none = QPushButton(tr("dup.select_none"))
        none.clicked.connect(lambda: self._check_all(False))
        opts.addWidget(best)
        opts.addWidget(none)
        lay.addLayout(opts)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(7)
        self.tree.setHeaderLabels([tr("dup.copy"), tr("col.format"), tr("col.time"), tr("dup.size"), tr("col.plays"),
                                   tr("col.rating"), tr("col.path")])
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.setUniformRowHeights(True)
        h = self.tree.header()
        h.setStretchLastSection(True)
        for i, w in enumerate([300, 110, 60, 80, 56, 80]):
            self.tree.setColumnWidth(i, w)
        h.setSectionResizeMode(QHeaderView.Interactive)
        self.tree.itemChanged.connect(lambda *_: self._update_summary())
        self.tree.itemDoubleClicked.connect(self._play_item)
        lay.addWidget(self.tree, 1)
        self.summary = muted()
        self.b_hide = QPushButton(tr("dup.remove_checked"))
        self.b_hide.clicked.connect(lambda: self._apply(trash=False))
        self.b_trash = primary(tr("dup.trash_checked"))
        self.b_trash.setObjectName("Danger")
        self.b_trash.clicked.connect(lambda: self._apply(trash=True))
        close = QPushButton(tr("btn.close"))
        close.clicked.connect(self.accept)
        self.footer(lay, self.b_hide, self.b_trash, close, left=self.summary)
        self.search()

    def search(self):
        self.groups = find_groups(self.chk_len.isChecked(), self.chk_album.isChecked())
        self.tree.blockSignals(True)
        self.tree.clear()
        c = cm_theme.colours()
        bold = QFont()
        bold.setBold(True)
        for g in self.groups:
            head = QTreeWidgetItem(self.tree, [f'{g[0].get("artist") or ""} – {g[0].get("title") or ""}   '
                                               f'({tr("dup.n_copies", n=len(g))})'])
            head.setFirstColumnSpanned(True)
            head.setFont(0, bold)
            head.setFlags(Qt.ItemIsEnabled)
            for i, r in enumerate(g):
                label = (r.get("album") or os.path.basename(os.path.dirname(r["path"]))) + \
                        (f'  ·  {tr("dup.missing")}' if r.get("missing") else "")
                it = QTreeWidgetItem(head, [label, _fmt(r), fmt_time(r["duration"]) if r.get("duration") else "",
                                            f'{(r.get("size") or 0) / 1048576:.1f} MB', str(r.get("play_count") or 0),
                                            "★" * int(r.get("rating") or 0), r["path"]])
                it.setData(0, Qt.UserRole, r)
                it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable)
                it.setCheckState(0, Qt.Unchecked if i == 0 else Qt.Checked)
                it.setToolTip(0, tr("dup.keep_tip") if i == 0 else tr("dup.remove_tip"))
                if i == 0:
                    it.setForeground(0, QColor("#16a34a"))
                if r.get("missing"):
                    for col in range(7):
                        it.setForeground(col, QColor(c["muted"]))
            head.setExpanded(True)
        self.tree.blockSignals(False)
        self._update_summary()

    def _children(self):
        for i in range(self.tree.topLevelItemCount()):
            head = self.tree.topLevelItem(i)
            yield head, [head.child(j) for j in range(head.childCount())]

    def _check_best(self):
        self.tree.blockSignals(True)
        for _head, kids in self._children():
            for j, it in enumerate(kids):
                it.setCheckState(0, Qt.Unchecked if j == 0 else Qt.Checked)
        self.tree.blockSignals(False)
        self._update_summary()

    def _check_all(self, on):
        self.tree.blockSignals(True)
        for _head, kids in self._children():
            for it in kids:
                it.setCheckState(0, Qt.Checked if on else Qt.Unchecked)
        self.tree.blockSignals(False)
        self._update_summary()

    def _plan(self):
        """[(keep row, [rows to remove])] - a group where every copy is checked keeps its best copy anyway."""
        plan = []
        for _head, kids in self._children():
            rows = [(it.data(0, Qt.UserRole), it.checkState(0) == Qt.Checked) for it in kids]
            drop = [r for r, on in rows if on]
            keep = [r for r, on in rows if not on]
            if not drop:
                continue
            if not keep:
                keep = [drop.pop(0)]
            plan.append((keep[0], drop))
        return plan

    def _update_summary(self):
        plan = self._plan()
        n = sum(len(d) for _k, d in plan)
        size = sum((r.get("size") or 0) for _k, d in plan for r in d)
        self.summary.setText(tr("dup.summary", groups=len(self.groups), n=n, size=f"{size / 1048576:.0f} MB")
                             if self.groups else tr("dup.none"))
        self.b_hide.setEnabled(n > 0)
        self.b_trash.setEnabled(n > 0)

    def _apply(self, trash):
        plan = self._plan()
        drop = [r["path"] for _k, d in plan for r in d]
        if not drop:
            return
        q = tr("dup.trash_q", n=len(drop)) if trash else tr("dup.remove_q", n=len(drop))
        if QMessageBox.question(self, APP_NAME, q) != QMessageBox.Yes:
            return
        for keep, d in plan:
            merge_stats(keep["path"], [r["path"] for r in d])
        ok = self.main.delete_files(drop, confirm=False) if trash else self.main.remove_from_library(drop, confirm=False)
        if ok:
            self.changed = True
        self.search()

    def _play_item(self, it, _col):
        r = it.data(0, Qt.UserRole)
        if r and not r.get("missing"):
            self.main._play_list([r])


def merge_stats(keep, drops):
    """Add play counts, the best rating and favourite of the removed copies to the copy that stays."""
    con = cm_library.connect()
    try:
        for p in drops:
            r = con.execute("SELECT rating, favourite, play_count, last_played FROM tracks WHERE path=?", (p,)).fetchone()
            if r is None:
                continue
            con.execute("UPDATE tracks SET rating=MAX(rating,?), favourite=MAX(favourite,?), play_count=play_count+?, "
                        "last_played=MAX(last_played,?) WHERE path=?",
                        (r["rating"] or 0, r["favourite"] or 0, r["play_count"] or 0, r["last_played"] or 0, keep))
            con.execute("UPDATE tracks SET play_count=0 WHERE path=?", (p,))
            con.execute("UPDATE playlist_items SET path=? WHERE path=?", (keep, p))
        con.commit()
    finally:
        con.close()
