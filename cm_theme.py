"""Claudius Multimedia - System / Light / Dark themes (live switching, follows Windows in System mode)."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

from cm_core import settings

LIGHT = dict(bg="#eef1f5", title="#e9ecf1", head="#f6f7f9", ribbon="#fbfcfd", panel="#ffffff", panel2="#f5f7fa",
             border="#dde2e8", text="#1d2430", muted="#6b7584", sel="#dbe7fd", row="#f8fafc", hover="#eaf0f9",
             video="#000000", input="#ffffff")
DARK = dict(bg="#121419", title="#181b21", head="#1c1f26", ribbon="#20242c", panel="#191c22", panel2="#1f232b",
            border="#2d323c", text="#e6e9ee", muted="#939cab", sel="#23365a", row="#1c2027", hover="#262b35",
            video="#000000", input="#15181d")

ACCENTS = ["#2563eb", "#16a34a", "#ea580c", "#9333ea", "#db2777", "#0891b2"]


def system_is_dark():
    try:
        return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except Exception:
        return False


def is_dark():
    mode = settings.get("theme", "system")
    return system_is_dark() if mode == "system" else mode == "dark"


def colours():
    c = dict(DARK if is_dark() else LIGHT)
    accent = QColor(settings.get("accent") or ACCENTS[0])
    if is_dark():
        accent = accent.lighter(125)
    c["accent"] = accent.name()
    soft = QColor(accent)
    base = QColor(c["panel"])
    mix = 0.22 if is_dark() else 0.13
    c["accentSoft"] = QColor(int(base.red() + (soft.red() - base.red()) * mix),
                             int(base.green() + (soft.green() - base.green()) * mix),
                             int(base.blue() + (soft.blue() - base.blue()) * mix)).name()
    return c


QSS = """
* {{ font-family: "Segoe UI Variable Text", "Segoe UI", "Inter", sans-serif; font-size: 9.5pt; }}
QWidget {{ color: {text}; }}
QMainWindow, #Root, QDialog {{ background: {bg}; }}
QToolTip {{ background: {panel}; color: {text}; border: 1px solid {border}; padding: 4px 6px; }}
#Header {{ background: {head}; border-bottom: 1px solid {border}; }}
#Brand {{ font-weight: 800; font-size: 12.5pt; letter-spacing: 0.5px; }}
#BrandSmall {{ color: {muted}; font-size: 8pt; font-weight: 600; letter-spacing: 1px; }}
#QuickSep, #VSep {{ background: {border}; }}
QPushButton#TabBtn {{ border: none; background: transparent; padding: 6px 11px; border-radius: 6px; font-size: 10pt; }}
QPushButton#TabBtn:hover {{ background: {hover}; }}
QPushButton#TabBtn:checked {{ background: {accentSoft}; color: {accent}; font-weight: 700; }}
QPushButton#Round {{ border: none; background: transparent; padding: 0; }}
QPushButton#Round:hover {{ background: {hover}; border-radius: 15px; }}
QLineEdit#Search {{ border: 1px solid {border}; border-radius: 15px; padding: 5px 12px; background: {panel}; min-width: 150px; max-width: 260px; }}
#Ribbon {{ background: {ribbon}; border-bottom: 1px solid {border}; }}
#RibbonGroupLabel {{ color: {muted}; font-size: 8pt; }}
QToolButton#RibbonBtn {{ border: none; border-radius: 7px; padding: 3px 2px 2px 2px; min-width: 60px; font-size: 8.5pt; background: transparent; }}
QToolButton#RibbonBtn:hover {{ background: {hover}; }}
QToolButton#RibbonBtn:checked {{ background: {accentSoft}; color: {accent}; }}
QToolButton#RibbonBtn:pressed {{ background: {sel}; }}
QToolButton#RibbonBtn:disabled {{ color: {muted}; }}
QToolButton#RibbonBtn::menu-indicator {{ image: none; width: 0; }}
#Side {{ background: {panel2}; border-right: 1px solid {border}; }}
#RightPanel {{ background: {panel2}; border-left: 1px solid {border}; }}
#SideHeading {{ color: {muted}; font-size: 7.5pt; font-weight: 700; letter-spacing: 1px; padding: 10px 10px 4px 10px; }}
QListWidget#SideList {{ background: transparent; border: none; outline: none; }}
QListWidget#SideList::item {{ padding: 5px 8px; border-radius: 6px; margin: 1px 4px; }}
QListWidget#SideList::item:hover {{ background: {hover}; }}
QListWidget#SideList::item:selected {{ background: {sel}; color: {text}; font-weight: 600; }}
#Main, #LibraryPage, #AboutPage {{ background: {panel}; }}
#AboutPage {{ background: {bg}; }}
#Card {{ background: {panel}; border: 1px solid {border}; border-radius: 14px; }}
#CardHead {{ background: {accentSoft}; border-top-left-radius: 14px; border-top-right-radius: 14px; }}
#CardFoot {{ background: {panel2}; border-top: 1px solid {border}; border-bottom-left-radius: 14px; border-bottom-right-radius: 14px; }}
#VideoPage {{ background: {video}; }}
QGraphicsView {{ background: #000; border: none; }}
#Muted {{ color: {muted}; }}
#BigTitle {{ font-size: 15pt; font-weight: 700; }}
#NowTitle {{ font-size: 12pt; font-weight: 700; }}
#H1 {{ font-size: 13pt; font-weight: 700; }}
QTableView {{ background: {panel}; alternate-background-color: {row}; border: none; gridline-color: transparent;
             selection-background-color: {sel}; selection-color: {text}; outline: none; }}
QTableView::item {{ padding: 3px 6px; border-bottom: 1px solid {border}; }}
QHeaderView::section {{ background: {panel}; color: {muted}; border: none; border-bottom: 1px solid {border};
                       padding: 6px 6px; font-weight: 600; font-size: 8.5pt; }}
QListView#AlbumStrip {{ background: {panel}; border: none; border-bottom: 1px solid {border}; outline: none; }}
QListView#AlbumStrip::item {{ border-radius: 8px; padding: 4px; color: {text}; }}
QListView#AlbumStrip::item:selected {{ background: {sel}; color: {text}; }}
QListView#AlbumStrip::item:hover {{ background: {hover}; }}
#LibBar {{ background: {panel}; border-bottom: 1px solid {border}; }}
#BarTitle {{ font-weight: 700; font-size: 10.5pt; }}
QTreeWidget#FolderTree {{ background: {panel2}; border: none; border-right: 1px solid {border}; outline: none; }}
QTreeWidget#FolderTree::item {{ padding: 4px 2px; }}
QTreeWidget#FolderTree::item:selected {{ background: {sel}; color: {text}; }}
QTreeWidget, QTableWidget {{ background: {panel}; border: 1px solid {border}; border-radius: 6px; outline: none;
                             selection-background-color: {sel}; selection-color: {text}; }}
QListWidget {{ background: {panel}; border: 1px solid {border}; border-radius: 6px; outline: none; }}
QListWidget::item {{ padding: 4px 6px; }}
QListWidget::item:selected {{ background: {sel}; color: {text}; }}
QListWidget#Queue, QListWidget#Lyrics {{ background: transparent; border: none; }}
QListWidget#Lyrics::item {{ padding: 5px 4px; color: {muted}; }}
QListWidget#Lyrics::item:selected {{ background: transparent; color: {accent}; }}
#Transport {{ background: {head}; border-top: 1px solid {border}; }}
#StatusBar {{ background: {title}; border-top: 1px solid {border}; }}
#StatusBar QLabel {{ color: {muted}; font-size: 8.5pt; }}
QToolButton#Flat {{ border: none; background: transparent; border-radius: 6px; padding: 4px; }}
QToolButton#Flat:hover {{ background: {hover}; }}
QToolButton#Flat:checked {{ background: {accentSoft}; }}
QToolButton#PlayBtn {{ border: none; background: transparent; padding: 0; }}
QSlider::groove:horizontal {{ height: 5px; border-radius: 2px; background: {border}; }}
QSlider::sub-page:horizontal {{ height: 5px; border-radius: 2px; background: {accent}; }}
QSlider::handle:horizontal {{ width: 13px; height: 13px; margin: -5px 0; border-radius: 7px; background: #ffffff; border: 1px solid #9aa4b2; }}
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{ background: {input}; border: 1px solid {border};
     border-radius: 6px; padding: 5px 8px; selection-background-color: {accent}; selection-color: #fff; }}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{ border: 1px solid {accent}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox::down-arrow {{ image: url("{arrow_down}"); width: 10px; height: 10px; margin-right: 6px; }}
QSpinBox, QDoubleSpinBox {{ padding-right: 20px; }}
QSpinBox::up-button, QDoubleSpinBox::up-button {{ subcontrol-origin: border; subcontrol-position: top right; width: 20px; border: none; }}
QSpinBox::down-button, QDoubleSpinBox::down-button {{ subcontrol-origin: border; subcontrol-position: bottom right; width: 20px; border: none; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: url("{arrow_up}"); width: 9px; height: 9px; }}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: url("{arrow_down}"); width: 9px; height: 9px; }}
QComboBox QAbstractItemView {{ background: {panel}; border: 1px solid {border}; selection-background-color: {sel}; selection-color: {text}; }}
QPushButton {{ background: {panel2}; border: 1px solid {border}; border-radius: 6px; padding: 6px 14px; }}
QPushButton:hover {{ background: {hover}; }}
QPushButton:disabled {{ color: {muted}; }}
QPushButton#Primary {{ background: {accent}; border: 1px solid {accent}; color: #ffffff; font-weight: 600; }}
QPushButton#Danger {{ background: #c62828; border: 1px solid #c62828; color: #ffffff; font-weight: 600; }}
QPushButton#Choice {{ text-align: left; padding: 8px 12px; }}
QPushButton#Choice:checked {{ border: 2px solid {accent}; background: {accentSoft}; }}
QTabWidget::pane {{ border: none; border-top: 1px solid {border}; }}
QTabBar::tab {{ background: transparent; color: {muted}; padding: 7px 14px; border: none; }}
QTabBar::tab:selected {{ color: {accent}; font-weight: 600; border-bottom: 2px solid {accent}; }}
QMenu {{ background: {panel}; border: 1px solid {border}; padding: 4px; }}
QMenu::item {{ padding: 6px 22px 6px 12px; border-radius: 4px; }}
QMenu::item:selected {{ background: {sel}; color: {text}; }}
QMenu::separator {{ height: 1px; background: {border}; margin: 4px 8px; }}
QScrollBar:vertical {{ background: transparent; width: 11px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {border}; border-radius: 4px; min-height: 30px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 11px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: {border}; border-radius: 4px; min-width: 30px; margin: 2px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QSplitter::handle {{ background: {border}; }}
QCheckBox, QRadioButton {{ spacing: 7px; }}
QGroupBox {{ border: 1px solid {border}; border-radius: 8px; margin-top: 12px; padding-top: 8px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {muted}; }}
QProgressBar {{ border: none; background: {border}; border-radius: 3px; height: 6px; text-align: center; color: transparent; }}
QProgressBar::chunk {{ background: {accent}; border-radius: 3px; }}
"""


def _arrow_files(colour):
    """Small arrow images for combo / spin boxes (style sheets can only draw arrows from files)."""
    import os
    from cm_core import data_dir
    folder = os.path.join(data_dir(), "theme")
    os.makedirs(folder, exist_ok=True)
    out = {}
    for name, path in (("down", "M2 4l4 4 4-4"), ("up", "M2 8l4-4 4 4")):
        fn = os.path.join(folder, f"arrow-{name}-{colour.lstrip('#')}.svg")
        if not os.path.isfile(fn):
            with open(fn, "w", encoding="utf-8") as fh:
                fh.write(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 12 12"><path d="{path}" fill="none" '
                         f'stroke="{colour}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>')
        out["arrow_" + name] = fn.replace("\\", "/")
    return out


def apply(app=None):
    app = app or QApplication.instance()
    c = colours()
    c.update(_arrow_files(c["muted"]))
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(c["bg"]))
    pal.setColor(QPalette.WindowText, QColor(c["text"]))
    pal.setColor(QPalette.Base, QColor(c["panel"]))
    pal.setColor(QPalette.AlternateBase, QColor(c["row"]))
    pal.setColor(QPalette.Text, QColor(c["text"]))
    pal.setColor(QPalette.Button, QColor(c["panel2"]))
    pal.setColor(QPalette.ButtonText, QColor(c["text"]))
    pal.setColor(QPalette.Highlight, QColor(c["accent"]))
    pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    pal.setColor(QPalette.PlaceholderText, QColor(c["muted"]))
    pal.setColor(QPalette.ToolTipBase, QColor(c["panel"]))
    pal.setColor(QPalette.ToolTipText, QColor(c["text"]))
    pal.setColor(QPalette.Link, QColor(c["accent"]))
    app.setPalette(pal)
    app.setStyleSheet(QSS.format(**c))
    return c


def set_windows_dark_titlebar(widget):
    """Make the Windows 11 title bar follow the theme (does nothing on other systems)."""
    import sys
    if sys.platform != "win32":
        return
    try:
        import ctypes
        value = ctypes.c_int(1 if is_dark() else 0)
        hwnd = int(widget.winId())
        for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (new / old builds)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(value), ctypes.sizeof(value)) == 0:
                break
    except Exception:
        pass
