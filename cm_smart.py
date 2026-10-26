"""Claudius Multimedia - smart playlists: an editor for rules such as "genre is Jazz and rating is at least 4".
The rules are turned into SQL by cm_library.smart_sql (fields and operators come from a fixed list there)."""
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
                               QScrollArea, QSpinBox, QVBoxLayout, QWidget)

import cm_icons
import cm_library
from cm_core import APP_NAME, tr
from cm_dialogs import Dialog, primary
from cm_widgets import muted

FIELD_ORDER = ["artist", "albumartist", "album", "title", "genre", "year", "rating", "plays", "favourite", "added",
               "last_played", "duration", "format", "bitrate", "has_cover", "has_lyrics", "kind", "path"]
ORDER_KEYS = ["artist", "title", "random", "most_played", "least_played", "recently_added", "recently_played", "rating"]


class RuleRow(QWidget):
    def __init__(self, rule, on_change, on_remove):
        super().__init__()
        self.on_change = on_change
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.field = QComboBox()
        for f in FIELD_ORDER:
            self.field.addItem(tr("smart.f." + f), f)
        self.field.setMinimumWidth(170)
        self.op = QComboBox()
        self.op.setMinimumWidth(170)
        self.value = QLineEdit()
        self.value.setMinimumWidth(160)
        self.unit = muted()
        rm = QPushButton("−")
        rm.setFixedWidth(34)
        rm.setToolTip(tr("smart.remove_rule"))
        rm.clicked.connect(lambda: on_remove(self))
        for w in (self.field, self.op):
            lay.addWidget(w)
        lay.addWidget(self.value, 1)
        lay.addWidget(self.unit)
        lay.addWidget(rm)
        self.field.currentIndexChanged.connect(self._field_changed)
        self.op.currentIndexChanged.connect(lambda _i: (self._update_unit(), on_change()))
        self.value.textChanged.connect(lambda _t: on_change())
        i = self.field.findData(rule.get("field", "artist"))
        self.field.setCurrentIndex(max(0, i))
        self._field_changed(keep_op=rule.get("op"))
        self.value.setText(str(rule.get("value", "")))

    def ftype(self):
        return cm_library.SMART_FIELDS[self.field.currentData()][0]

    def _field_changed(self, _i=None, keep_op=None):
        typ = self.ftype()
        self.op.blockSignals(True)
        self.op.clear()
        for op in cm_library.SMART_OPS[typ]:
            self.op.addItem(tr("smart.op." + op), op)
        if keep_op:
            self.op.setCurrentIndex(max(0, self.op.findData(keep_op)))
        self.op.blockSignals(False)
        self.value.setVisible(typ in ("text", "number", "date"))
        self.value.setPlaceholderText({"number": "0", "date": "30"}.get(typ, ""))
        self._update_unit()
        self.on_change()

    def _update_unit(self):
        f = self.field.currentData()
        typ = self.ftype()
        unit = ""
        if typ == "date":
            unit = tr("smart.days")
        elif f == "duration":
            unit = tr("smart.minutes")
        elif f == "rating":
            unit = "★ 0–5"
        elif f == "bitrate":
            unit = "kbps"
        self.unit.setText(unit)
        self.unit.setVisible(bool(unit))

    def rule(self):
        return {"field": self.field.currentData(), "op": self.op.currentData(), "value": self.value.text().strip()}


class SmartDialog(Dialog):
    """Create / edit a smart playlist. result_value = (name, spec) after exec() returns True."""
    def __init__(self, parent, name="", spec=None):
        super().__init__(parent, tr("smart.title"), "star", "teal")
        self.resize(820, 560)
        spec = spec or {"match": "all", "rules": [{"field": "rating", "op": "ge", "value": "4"}], "order": "random",
                        "limit": 0}
        self.result_value = None
        self.rows = []
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel(tr("smart.name")))
        self.name = QLineEdit(name)
        self.name.setPlaceholderText(tr("smart.name_ph"))
        top.addWidget(self.name, 1)
        lay.addLayout(top)
        m = QHBoxLayout()
        m.addWidget(QLabel(tr("smart.match_a")))
        self.match = QComboBox()
        self.match.addItem(tr("smart.match_all"), "all")
        self.match.addItem(tr("smart.match_any"), "any")
        self.match.setCurrentIndex(1 if spec.get("match") == "any" else 0)
        self.match.currentIndexChanged.connect(lambda _i: self._changed())
        m.addWidget(self.match)
        m.addWidget(QLabel(tr("smart.match_b")))
        m.addStretch(1)
        lay.addLayout(m)
        self.rule_box = QWidget()
        self.rule_lay = QVBoxLayout(self.rule_box)
        self.rule_lay.setContentsMargins(0, 0, 0, 0)
        self.rule_lay.setSpacing(6)
        self.rule_lay.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(self.rule_box)
        lay.addWidget(scroll, 1)
        add = QPushButton(cm_icons.glossy("add", "teal", 18), tr("smart.add_rule"))
        add.clicked.connect(lambda: self._add_rule({"field": "genre", "op": "contains", "value": ""}))
        ar = QHBoxLayout()
        ar.addWidget(add)
        ar.addStretch(1)
        lay.addLayout(ar)
        opts = QHBoxLayout()
        self.chk_limit = QCheckBox(tr("smart.limit"))
        self.limit = QSpinBox()
        self.limit.setRange(1, 100000)
        self.limit.setValue(int(spec.get("limit") or 50))
        self.chk_limit.setChecked(bool(spec.get("limit")))
        self.limit.setEnabled(self.chk_limit.isChecked())
        self.chk_limit.toggled.connect(lambda on: (self.limit.setEnabled(on), self._changed()))
        self.limit.valueChanged.connect(lambda _v: self._changed())
        opts.addWidget(self.chk_limit)
        opts.addWidget(self.limit)
        opts.addWidget(QLabel(tr("smart.tracks")))
        opts.addSpacing(24)
        opts.addWidget(QLabel(tr("smart.order")))
        self.order = QComboBox()
        for k in ORDER_KEYS:
            self.order.addItem(tr("smart.o." + k), k)
        self.order.setCurrentIndex(max(0, self.order.findData(spec.get("order", "artist"))))
        opts.addWidget(self.order)
        opts.addStretch(1)
        lay.addLayout(opts)
        self.count = muted()
        ok = primary(tr("btn.save"))
        ok.clicked.connect(self._save)
        cancel = QPushButton(tr("btn.cancel"))
        cancel.clicked.connect(self.reject)
        self.footer(lay, cancel, ok, left=self.count)
        self.count_timer = QTimer(self, singleShot=True, interval=300, timeout=self._update_count)
        for rule in spec.get("rules") or []:
            self._add_rule(rule)
        if not self.rows:
            self._add_rule({"field": "artist", "op": "contains", "value": ""})
        self._update_count()

    def _add_rule(self, rule):
        row = RuleRow(rule, self._changed, self._remove_rule)
        self.rule_lay.insertWidget(self.rule_lay.count() - 1, row)
        self.rows.append(row)
        self._changed()

    def _remove_rule(self, row):
        if row in self.rows:
            self.rows.remove(row)
            row.setParent(None)
            row.deleteLater()
            self._changed()

    def _changed(self):
        if hasattr(self, "count_timer"):
            self.count_timer.start()

    def spec(self):
        return {"match": self.match.currentData(), "rules": [r.rule() for r in self.rows],
                "order": self.order.currentData(), "limit": self.limit.value() if self.chk_limit.isChecked() else 0}

    def _update_count(self):
        try:
            n = cm_library.smart_count(self.spec())
        except Exception:
            n = 0
        self.count.setText(tr("smart.count", n=n))

    def _save(self):
        name = self.name.text().strip()
        if not name:
            QMessageBox.information(self, APP_NAME, tr("smart.need_name"))
            self.name.setFocus()
            return
        self.result_value = (name, self.spec())
        self.accept()


