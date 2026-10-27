"""Claudius Multimedia - main window."""
import os
import random
import re
import sqlite3
import sys
import time

from PySide6.QtCore import QByteArray, QFileSystemWatcher, QRectF, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import (QActionGroup, QColor, QDesktopServices, QIcon, QImage, QKeySequence, QLinearGradient,
                           QPainter, QPixmap, QShortcut, QStandardItem)
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QButtonGroup, QComboBox, QFileDialog, QHBoxLayout,
                               QInputDialog, QLabel, QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox,
                               QProgressBar, QPushButton, QSlider, QSplitter, QStackedWidget, QTabWidget, QToolButton,
                               QVBoxLayout, QWidget)

import cm_dialogs
import cm_icons
import cm_library
import cm_online
import cm_tags
import cm_theme
import cm_widgets
from cm_core import (APP_NAME, APP_URL, LANGUAGES, MEDIA_EXT, PLAYLIST_EXT, SUBTITLE_EXT, fmt_time,
                     is_media, is_url, is_video, set_language, settings, tr)
from cm_parse import parse_subtitles, read_playlist, read_text, subtitle_at, write_m3u
from cm_player import Player, ThumbnailMaker
from cm_widgets import bind, muted

TABS = ["file", "home", "playback", "library", "tags", "lyrics", "playlist", "tools", "view", "about"]
RESUME_MIN_MS = 20 * 60 * 1000      # audio longer than this (audiobooks, podcasts, mixes) also continues where it stopped

RIBBONS = {
    "file": [("open", ["open_file", "open_folder", "open_url"]),
             ("queue", ["load_playlist", "save_playlist", "clear_queue"]),
             ("program", ["settings", "exit"])],
    "home": [("open", ["open_file", "open_folder", "open_url"]),
             ("playback", ["play", "stop", "prev", "next"]),
             ("audio", ["audio_track", "speed"]),
             ("video", ["subtitles", "snapshot", "aspect"]),
             ("online", ["find_cover", "find_lyrics"]),
             ("view", ["fullscreen", "mini", "toggle_right"])],
    "playback": [("control", ["play", "stop", "prev", "next"]),
                 ("mode", ["shuffle", "repeat"]),
                 ("jump", ["back10", "fwd10"]),
                 ("speed", ["slower", "speed", "faster"]),
                 ("sound", ["mute", "voldown", "volup"])],
    "library": [("library", ["add_folder", "rescan", "folders"]),
                ("browse", ["browse_artists", "browse_albums", "browse_genres", "browse_folders", "browse_tracks"]),
                ("layout", ["album_grid"]),
                ("selection", ["edit_tags", "find_cover", "remove_lib", "delete_files"]),
                ("playlists", ["new_playlist", "new_smart", "add_to_playlist"])],
    "tags": [("edit", ["edit_tags", "mb_lookup", "tags_from_name"]),
             ("artwork", ["find_cover", "cover_from_file", "remove_cover", "export_cover"]),
             ("batch", ["batch_covers", "rename_files"])],
    "lyrics": [("lyrics", ["find_lyrics", "edit_lyrics", "load_lrc", "batch_lyrics"]),
               ("display", ["lyrics_smaller", "lyrics_bigger", "lyrics_earlier", "lyrics_later"])],
    "playlist": [("queue", ["queue_add_files", "queue_add_folder", "queue_remove", "clear_queue"]),
                 ("order", ["queue_shuffle", "queue_sort"]),
                 ("file", ["load_playlist", "save_playlist"]),
                 ("playlists", ["new_playlist", "new_smart", "add_to_playlist"])],
    "tools": [("cleanup", ["duplicates", "missing_files", "hidden_items"]),
              ("batch", ["batch_covers", "batch_lyrics", "rename_files"]),
              ("library", ["statistics", "watch_folders", "backup", "restore"])],
    "view": [("theme", ["theme_system", "theme_light", "theme_dark"]),
             ("language", ["language"]),
             ("show", ["show_library", "show_nowplaying", "toggle_sidebar", "toggle_right"]),
             ("window", ["fullscreen", "mini", "always_on_top"]),
             ("options", ["settings", "shortcuts"])],
    "about": [("help", ["about", "website", "shortcuts"]),
              ("licence", ["freeware", "third_party"])],
}


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(cm_icons.logo_icon())
        self.setAcceptDrops(True)
        self.player = Player(self)
        self.subs = []                    # external subtitle cues
        self.embedded_sub = ""
        self.current_info = {}
        self.current_lyrics_source = ""
        self.view = ("music", None)       # sidebar selection
        self.browse = settings.get("browse", "albums")
        if self.browse not in ("artists", "albums", "genres", "folders", "tracks"):
            self.browse = "albums"
        self.browse_value = None
        self.watch_task = None
        self._pending_dirs = set()
        self._listen_acc = 0
        self._listen_last = None
        self.thumbnailer = ThumbnailMaker(self)
        self.thumbnailer.ready.connect(self._video_thumb_ready)
        self.watcher = QFileSystemWatcher(self)
        self.watcher.directoryChanged.connect(self._dir_changed)
        self.watch_timer = QTimer(self, singleShot=True, interval=4000, timeout=self._watch_scan)
        self.periodic_timer = QTimer(self, interval=10 * 60 * 1000, timeout=self._periodic_scan)
        self._last_quiet_scan = time.monotonic()
        self.batch_task = None
        self._prev_page = 0
        self._mini_geometry = None
        self._normal_state = None
        self._lyrics_req = None
        self._lyrics_text = ""

        self._build_actions()
        self._build_ui()
        self._connect_player()
        self._shortcuts()
        cm_theme.apply()
        self._refresh_icons()
        self.header.select("home")
        self.ribbon.show_page("home")
        try:
            QApplication.styleHints().colorSchemeChanged.connect(self._system_theme_changed)
        except Exception:
            pass
        if settings.get("geometry"):
            self.restoreGeometry(QByteArray.fromBase64(settings["geometry"].encode()))
        else:
            self.resize(1440, 900)
        if settings.get("always_on_top"):
            self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.reload_sidebar()
        self.reload_library()
        self._update_stats()
        self._restore_queue()
        self._update_modes()
        self._show_track(-1)
        self.save_timer = QTimer(self, interval=60000, timeout=self._save_state)
        self.save_timer.start()
        QTimer.singleShot(3000, self.setup_watch)

    # ================================================================ actions
    def _build_actions(self):
        A = {}
        mk = lambda aid, glyph, colour, slot, key=None, check=False: A.__setitem__(aid, cm_widgets.make_action(
            self, "act." + aid, glyph, colour, slot, key, check))
        mk("open_file", "open", "blue", self.open_files, QKeySequence.Open)
        mk("open_folder", "folderplus", "blue", self.open_folder, "Ctrl+Shift+O")
        mk("open_url", "url", "teal", self.open_url, "Ctrl+U")
        mk("load_playlist", "playlist", "teal", self.load_playlist_file)
        mk("save_playlist", "save", "green", self.save_playlist_file, QKeySequence.Save)
        mk("clear_queue", "trash", "red", self.player.clear)
        mk("settings", "gear", "gray", lambda: self.open_settings(0), "Ctrl+,")
        mk("exit", "exit", "red", self.close)
        mk("play", "play", "green", self.player.toggle)
        mk("stop", "stop", "red", self.player.stop, "S")
        mk("prev", "prev", "green", self.player.previous, "Ctrl+P")
        mk("next", "next", "green", lambda: self.player.next(), "Ctrl+N")
        mk("shuffle", "shuffle", "purple", lambda on: self.player.set_shuffle(on), None, True)
        mk("repeat", "repeat", "purple", self.player.cycle_repeat)
        mk("back10", "back10", "teal", lambda: self.player.jump(-10000))
        mk("fwd10", "fwd10", "teal", lambda: self.player.jump(10000))
        mk("slower", "slower", "orange", lambda: self.change_rate(-0.1), "[")
        mk("speed", "speed", "orange", None)
        mk("faster", "speed", "orange", lambda: self.change_rate(+0.1), "]")
        mk("mute", "mute", "gray", self.toggle_mute, "M", True)
        mk("voldown", "voldown", "gray", lambda: self.change_volume(-5))
        mk("volup", "volup", "gray", lambda: self.change_volume(+5))
        mk("audio_track", "lyrics", "orange", None)
        mk("subtitles", "sub", "purple", None)
        mk("snapshot", "camera", "purple", self.snapshot, "F12")
        mk("aspect", "aspect", "purple", None)
        mk("find_cover", "image", "pink", self.find_cover)
        mk("find_lyrics", "lyrics", "pink", self.find_lyrics, "Ctrl+L")
        mk("fullscreen", "full", "indigo", self.toggle_fullscreen, "F11")
        mk("mini", "mini", "indigo", self.toggle_mini, "Ctrl+M")
        mk("toggle_right", "panel", "indigo", self.toggle_right, None, True)
        mk("add_folder", "folderplus", "blue", self.add_library_folder)
        mk("rescan", "scan", "blue", self.rescan, "F5")
        mk("folders", "library", "blue", lambda: self.open_settings(2))
        for aid, glyph in (("browse_artists", "user"), ("browse_albums", "album"), ("browse_genres", "grid"),
                           ("browse_folders", "open"), ("browse_tracks", "list")):
            mk(aid, glyph, "green", lambda _=False, m=aid.split("_")[1]: self.set_browse(m), None, True)
        mk("album_grid", "grid", "teal", lambda on: self.set_album_view("grid" if on else "strip"), None, True)
        mk("remove_lib", "remove", "gray", lambda: self.remove_from_library(self.target_paths(library_only=True)))
        mk("delete_files", "trash", "red", lambda: self.delete_files(self.target_paths(library_only=True)))
        mk("new_smart", "star", "teal", lambda: self.edit_smart(None))
        mk("duplicates", "grid", "orange", self.show_duplicates)
        mk("missing_files", "search", "orange", self.show_missing)
        mk("hidden_items", "undo", "orange", self.show_hidden)
        mk("statistics", "eq", "green", self.show_statistics)
        mk("watch_folders", "scan", "green", self.toggle_watch, None, True)
        mk("backup", "save", "blue", self.backup_library)
        mk("restore", "export", "blue", self.restore_library)
        mk("edit_tags", "tag", "orange", self.edit_tags, "Ctrl+T")
        mk("mb_lookup", "star", "orange", self.mb_lookup)
        mk("tags_from_name", "list", "orange", self.tags_from_name)
        mk("cover_from_file", "image", "pink", self.cover_from_file)
        mk("remove_cover", "trash", "pink", self.remove_cover)
        mk("export_cover", "export", "pink", self.export_cover)
        mk("batch_covers", "cloud", "pink", self.batch_covers)
        mk("batch_lyrics", "cloud", "purple", self.batch_lyrics)
        mk("rename_files", "convert", "indigo", self.rename_files)
        mk("new_playlist", "add", "teal", self.new_playlist)
        mk("add_to_playlist", "playlist", "teal", None)
        mk("edit_lyrics", "edit", "purple", self.find_lyrics)
        mk("load_lrc", "file", "purple", self.load_lrc)
        mk("lyrics_smaller", "fontdown", "indigo", lambda: self.lyrics_font(-1))
        mk("lyrics_bigger", "fontup", "indigo", lambda: self.lyrics_font(+1))
        mk("lyrics_earlier", "back10", "indigo", lambda: self.lyrics_offset(-500))
        mk("lyrics_later", "fwd10", "indigo", lambda: self.lyrics_offset(+500))
        mk("queue_add_files", "add", "blue", lambda: self.open_files(add=True))
        mk("queue_add_folder", "folderplus", "blue", lambda: self.open_folder(add=True))
        mk("queue_remove", "remove", "red", self.queue_remove)
        mk("queue_shuffle", "shuffle", "purple", self.player.shuffle_queue)
        mk("queue_sort", "sort", "purple", None)
        mk("theme_system", "theme", "indigo", lambda: self.set_theme("system"), None, True)
        mk("theme_light", "sun", "orange", lambda: self.set_theme("light"), None, True)
        mk("theme_dark", "moon", "blue", lambda: self.set_theme("dark"), None, True)
        mk("language", "lang", "teal", None)
        mk("show_library", "library", "green", lambda: self.show_page(0))
        mk("show_nowplaying", "video", "green", lambda: self.show_page(1))
        mk("toggle_sidebar", "sidebar", "green", self.toggle_sidebar, None, True)
        mk("always_on_top", "pin", "purple", self.toggle_on_top, None, True)
        mk("shortcuts", "keyboard", "teal", self.show_shortcuts)
        mk("about", "info", "blue", lambda: self.select_tab("about"))
        mk("website", "globe", "blue", lambda: QDesktopServices.openUrl(QUrl(APP_URL)))
        mk("freeware", "heartf", "green", lambda: self.open_doc("freeware"))
        mk("third_party", "list", "green", lambda: self.open_doc("third"))
        mk("favourite", "heart", "pink", self.toggle_favourite, None, True)
        self.acts = A
        g = QActionGroup(self)
        for k in ("theme_system", "theme_light", "theme_dark"):
            g.addAction(A[k])
        A["theme_" + settings.get("theme", "system")].setChecked(True)
        g2 = QActionGroup(self)
        for k in ("browse_artists", "browse_albums", "browse_genres", "browse_folders", "browse_tracks"):
            g2.addAction(A[k])
        A["browse_" + self.browse].setChecked(True)
        A["album_grid"].setChecked(settings.get("album_view") == "grid")
        A["watch_folders"].setChecked(bool(settings.get("watch_folders", True)))
        A["shuffle"].setChecked(self.player.shuffle)
        A["mute"].setChecked(bool(settings.get("muted")))
        A["toggle_sidebar"].setChecked(settings.get("show_sidebar", True))
        A["toggle_right"].setChecked(settings.get("show_right", True))
        A["always_on_top"].setChecked(bool(settings.get("always_on_top")))

        # menus for drop-down ribbon buttons
        self.menus = {}
        self.menus["audio_track"] = QMenu(self)
        self.menus["audio_track"].aboutToShow.connect(self._fill_audio_menu)
        self.menus["subtitles"] = QMenu(self)
        self.menus["subtitles"].aboutToShow.connect(self._fill_sub_menu)
        self.menus["aspect"] = QMenu(self)
        self.menus["aspect"].aboutToShow.connect(self._fill_aspect_menu)
        self.menus["speed"] = QMenu(self)
        self.menus["speed"].aboutToShow.connect(self._fill_speed_menu)
        self.menus["language"] = QMenu(self)
        self.menus["language"].aboutToShow.connect(self._fill_lang_menu)
        self.menus["add_to_playlist"] = QMenu(self)
        self.menus["add_to_playlist"].aboutToShow.connect(
            lambda: self._fill_playlist_menu(self.menus["add_to_playlist"], self.target_paths()))
        self.menus["queue_sort"] = QMenu(self)
        self.menus["queue_sort"].aboutToShow.connect(self._fill_sort_menu)

    def _shortcuts(self):
        def sc(key, fn):
            s = QShortcut(QKeySequence(key), self)
            s.setContext(Qt.WindowShortcut)
            s.activated.connect(fn)
        sc("Space", self._space)
        sc("Right", lambda: self.player.jump(5000))
        sc("Left", lambda: self.player.jump(-5000))
        sc("Ctrl+Right", lambda: self.player.jump(30000))
        sc("Ctrl+Left", lambda: self.player.jump(-30000))
        sc("Up", lambda: self.change_volume(+5))
        sc("Down", lambda: self.change_volume(-5))
        sc("N", lambda: self.player.next())
        sc("P", self.player.previous)
        sc("Return", self._enter)
        sc("Escape", self._escape)
        sc("Ctrl+F", lambda: (self.header.search.setFocus(), self.header.search.selectAll()))
        sc("Home", self._start_over)
        sc("Media Play", self.player.toggle)
        sc("Media Next", lambda: self.player.next())
        sc("Media Previous", self.player.previous)
        sc("Media Stop", self.player.stop)

    def _space(self):
        w = QApplication.focusWidget()
        if isinstance(w, (cm_widgets.QLineEdit,)):
            return
        self.player.toggle()

    def _enter(self):
        if self.center.currentIndex() == 1 or self.isFullScreen():
            self.toggle_fullscreen()

    def _escape(self):
        if self.isFullScreen():
            self.toggle_fullscreen()
        elif self._mini_geometry is not None:
            self.toggle_mini()

    # ================================================================ layout
    def _build_ui(self):
        root = QWidget()
        root.setObjectName("Root")
        v = QVBoxLayout(root)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        A = self.acts
        self.header = cm_widgets.Header(TABS, [(A["open_file"], "open", "blue"), (A["save_playlist"], "save", "green"),
                                               (A["toggle_right"], "playlist", "orange"), (A["settings"], "gear", "purple")])
        self.header.tabChanged.connect(self.select_tab)
        self.header.search.textChanged.connect(lambda _t: self.search_timer.start())
        self.search_timer = QTimer(self, singleShot=True, interval=250, timeout=self.reload_library)
        v.addWidget(self.header)
        self.ribbon = cm_widgets.Ribbon()
        for key in TABS:
            self.ribbon.add_page(key, RIBBONS[key], A, self.menus)
        v.addWidget(self.ribbon)

        self.body = QSplitter(Qt.Horizontal)
        self.body.setHandleWidth(1)
        self.body.setChildrenCollapsible(False)
        # sidebar
        self.side = QWidget()
        self.side.setObjectName("Side")
        self.side.setAttribute(Qt.WA_StyledBackground, True)
        sl = QVBoxLayout(self.side)
        sl.setContentsMargins(4, 8, 4, 8)
        self.sidelist = cm_widgets.SideList()
        self.sidelist.itemClicked.connect(self._side_clicked)
        self.sidelist.customContextMenuRequested.connect(self._side_menu)
        self.sidelist.tracksDropped.connect(self._side_drop)
        sl.addWidget(self.sidelist)
        self.side.setMinimumWidth(190)
        self.body.addWidget(self.side)

        # centre: library / now playing / about
        self.center = QStackedWidget()
        self.center.addWidget(self._build_library_page())
        self.video = cm_widgets.VideoView()
        self.video.doubleClicked.connect(self.toggle_fullscreen)
        self.video.filesDropped.connect(lambda files: self.open_paths(files))
        self.video.setContextMenuPolicy(Qt.CustomContextMenu)
        self.video.customContextMenuRequested.connect(self._video_menu)
        self.center.addWidget(self.video)
        self.about = cm_dialogs.AboutPage(open_doc=self.open_doc)
        self.center.addWidget(self.about)
        self.body.addWidget(self.center)

        # right panel: cover, lyrics, info, up next
        self.right = QWidget()
        self.right.setObjectName("RightPanel")
        self.right.setAttribute(Qt.WA_StyledBackground, True)
        rl = QVBoxLayout(self.right)
        rl.setContentsMargins(16, 16, 16, 8)
        rl.setSpacing(6)
        self.big_cover = cm_widgets.CoverLabel(268, 10)
        rl.addWidget(self.big_cover, 0, Qt.AlignHCenter)
        self.np_title = QLabel()
        self.np_title.setObjectName("NowTitle")
        self.np_title.setWordWrap(True)
        self.np_sub = muted()
        self.np_sub.setWordWrap(True)
        rl.addWidget(self.np_title)
        rl.addWidget(self.np_sub)
        self.rtabs = QTabWidget()
        self.lyrics = cm_widgets.LyricsView()
        self.lyrics.set_font_size(settings.get("lyrics_font", 13))
        self.lyrics.seekRequested.connect(self.player.seek)
        lw = QWidget()
        ll = QVBoxLayout(lw)
        ll.setContentsMargins(0, 6, 0, 0)
        ll.addWidget(self.lyrics, 1)
        self.lyr_status = muted()
        self.lyr_status.setWordWrap(True)
        ll.addWidget(self.lyr_status)
        self.rtabs.addTab(lw, "")
        self.info_lab = QLabel()
        self.info_lab.setWordWrap(True)
        self.info_lab.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.info_lab.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.info_lab.setContentsMargins(4, 10, 4, 4)
        self.rtabs.addTab(self.info_lab, "")
        self.queue = cm_widgets.QueueList()
        self.queue.tracksDropped.connect(self._queue_drop)
        self.queue.itemDoubleClicked.connect(lambda it: self.player.play_index(self.queue.row(it)))
        self.queue.model().rowsMoved.connect(self._queue_moved)
        self.queue.setContextMenuPolicy(Qt.CustomContextMenu)
        self.queue.customContextMenuRequested.connect(self._queue_menu)
        self.rtabs.addTab(self.queue, "")
        rl.addWidget(self.rtabs, 1)
        self.right.setMinimumWidth(300)
        self.right.setMaximumWidth(420)
        self.body.addWidget(self.right)
        self.body.setStretchFactor(1, 1)
        self.body.setSizes([220, 900, 320])
        v.addWidget(self.body, 1)

        self.transport = cm_widgets.Transport(self.player, A)
        self.transport.speed.setMenu(self.menus["speed"])
        v.addWidget(self.transport)

        sb = QWidget()
        sb.setObjectName("StatusBar")
        sb.setAttribute(Qt.WA_StyledBackground, True)
        sb.setFixedHeight(26)
        sl = QHBoxLayout(sb)
        sl.setContentsMargins(12, 0, 12, 0)
        sl.setSpacing(18)
        self.st_state = QLabel()
        self.st_tech = QLabel()
        self.st_msg = QLabel()
        self.st_progress = QProgressBar()
        self.st_progress.setFixedWidth(160)
        self.st_progress.hide()
        self.st_cancel = QPushButton()
        bind(self.st_cancel, "btn.cancel")
        self.st_cancel.setFixedHeight(20)
        self.st_cancel.setStyleSheet("padding: 0 10px; font-size: 8pt;")
        self.st_cancel.hide()
        self.st_cancel.clicked.connect(self._cancel_batch)
        self.st_stats = QLabel()
        for w in (self.st_state, self.st_tech):
            sl.addWidget(w)
        sl.addStretch(1)
        sl.addWidget(self.st_msg)
        sl.addWidget(self.st_progress)
        sl.addWidget(self.st_cancel)
        sl.addWidget(self.st_stats)
        self.statusw = sb
        v.addWidget(sb)
        self.setCentralWidget(root)
        self.side.setVisible(settings.get("show_sidebar", True))
        self.right.setVisible(settings.get("show_right", True))
        self._retranslate_local()

    def _build_library_page(self):
        page = QWidget()
        page.setObjectName("LibraryPage")
        page.setAttribute(Qt.WA_StyledBackground, True)
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.lib_layout = v
        # bar above albums / videos: back to the grid, title, sort, tile size, strip / grid
        self.lib_bar = QWidget()
        self.lib_bar.setObjectName("LibBar")
        self.lib_bar.setAttribute(Qt.WA_StyledBackground, True)
        self.lib_bar.setFixedHeight(42)
        bl = QHBoxLayout(self.lib_bar)
        bl.setContentsMargins(10, 4, 12, 4)
        bl.setSpacing(8)
        self.b_back = QToolButton()
        self.b_back.setObjectName("Flat")
        self.b_back.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        bind(self.b_back, "lib.all_albums")
        self.b_back.clicked.connect(self._back_to_grid)
        bl.addWidget(self.b_back)
        self.bar_title = QLabel()
        self.bar_title.setObjectName("BarTitle")
        bl.addWidget(self.bar_title)
        bl.addStretch(1)
        self.sort_label = muted()
        bind(self.sort_label, "lib.sort")
        bl.addWidget(self.sort_label)
        self.sort_combo = QComboBox()
        self.sort_combo.setMinimumWidth(150)
        self._fill_sort_combo()
        self.sort_combo.currentIndexChanged.connect(self._album_sort_changed)
        bl.addWidget(self.sort_combo)
        bl.addSpacing(10)
        self.size_icon = QLabel()
        bl.addWidget(self.size_icon)
        self.size_slider = QSlider(Qt.Horizontal)
        self.size_slider.setRange(72, 260)
        self.size_slider.setFixedWidth(110)
        self.size_slider.setValue(int(settings.get("tile_size", 124)))
        self.size_slider.valueChanged.connect(self._tile_size_changed)
        bind(self.size_slider, "lib.tile_size", "setToolTip")
        bl.addWidget(self.size_slider)
        bl.addSpacing(6)
        self.b_strip = QToolButton()
        self.b_grid = QToolButton()
        grp = QButtonGroup(self)
        for b, mode, key in ((self.b_strip, "strip", "lib.view_strip"), (self.b_grid, "grid", "lib.view_grid")):
            b.setObjectName("Flat")
            b.setCheckable(True)
            b.setIconSize(QSize(18, 18))
            b.setChecked(settings.get("album_view", "strip") == mode)
            bind(b, key, "setToolTip")
            b.clicked.connect(lambda _=False, m=mode: self.set_album_view(m))
            grp.addButton(b)
            bl.addWidget(b)
        v.addWidget(self.lib_bar)

        self.tile_model = cm_widgets.TileModel(self)
        self.tile_model.resolver = self._tile_paths
        self.tiles = cm_widgets.TileView()
        self.tiles.setModel(self.tile_model)
        self.tiles.configure(mode=settings.get("album_view", "strip"), tile=settings.get("tile_size", 124))
        self.tiles.clicked.connect(self._tile_clicked)
        self.tiles.doubleClicked.connect(self._tile_activated)
        self.tiles.customContextMenuRequested.connect(self._tile_menu)
        self.tiles.removeRequested.connect(lambda: self.remove_from_library(self._tile_selected_paths()))
        self.tiles.trashRequested.connect(lambda: self.delete_files(self._tile_selected_paths()))
        self.tiles.tileSizeChanged.connect(lambda v: self.size_slider.setValue(v))
        self.tiles.setItemDelegate(cm_widgets.TileDelegate(self.tiles))
        v.addWidget(self.tiles)

        self.lower = QWidget()
        h = QHBoxLayout(self.lower)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        self.group_list = QListWidget()
        self.group_list.setObjectName("SideList")
        self.group_list.setFixedWidth(230)
        self.group_list.itemClicked.connect(self._group_clicked)
        self.group_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.group_list.customContextMenuRequested.connect(self._group_menu)
        self.group_list.hide()
        h.addWidget(self.group_list)
        self.folder_tree = cm_widgets.FolderTree()
        self.folder_tree.itemClicked.connect(self._folder_clicked)
        self.folder_tree.customContextMenuRequested.connect(self._folder_menu)
        self.folder_tree.hide()
        h.addWidget(self.folder_tree)
        inner = QVBoxLayout()
        inner.setContentsMargins(0, 0, 0, 0)
        inner.setSpacing(0)
        self.album_head = QWidget()
        ah = QHBoxLayout(self.album_head)
        ah.setContentsMargins(16, 12, 16, 10)
        ah.setSpacing(14)
        self.head_cover = cm_widgets.CoverLabel(56, 6)
        ah.addWidget(self.head_cover)
        t = QVBoxLayout()
        t.setSpacing(2)
        self.head_title = QLabel()
        self.head_title.setObjectName("BigTitle")
        self.head_sub = muted()
        t.addStretch(1)
        t.addWidget(self.head_title)
        t.addWidget(self.head_sub)
        t.addStretch(1)
        ah.addLayout(t, 1)
        self.b_play_all = QPushButton()
        self.b_play_all.setObjectName("Primary")
        bind(self.b_play_all, "btn.play_all")
        self.b_play_all.clicked.connect(lambda: self.play_rows(0))
        self.b_shuffle_all = QPushButton()
        bind(self.b_shuffle_all, "btn.shuffle_all")
        self.b_shuffle_all.clicked.connect(lambda: self.play_rows(0, shuffle=True))
        self.b_extra = QPushButton()
        self.b_extra.clicked.connect(self._head_extra)
        self.b_tags_all = QPushButton()
        bind(self.b_tags_all, "act.edit_tags")
        self.b_tags_all.clicked.connect(lambda: self.edit_tags(all_rows=True))
        self.b_more = QPushButton("⋯")
        self.b_more.setFixedWidth(42)
        bind(self.b_more, "lib.more", "setToolTip")
        self.b_more.clicked.connect(lambda: self._track_menu(
            self.table.model_.rows, self.b_more.mapToGlobal(self.b_more.rect().bottomLeft()), source="head"))
        for b in (self.b_play_all, self.b_shuffle_all, self.b_extra, self.b_tags_all, self.b_more):
            ah.addWidget(b)
        inner.addWidget(self.album_head)
        self.table = cm_widgets.TrackTable()
        if settings.get("table_header"):
            self.table.restore_layout(settings["table_header"])
        self.table.layoutSaved.connect(lambda s: settings.__setitem__("table_header", s))
        self.table.model_.edit_hook = self._edit_cell
        self.table.doubleClicked.connect(self._table_activated)
        self.table.customContextMenuRequested.connect(self._table_menu)
        self.table.ratingClicked.connect(self._rate_row)
        self.table.favClicked.connect(lambda row: self._set_fav([row["path"]], not row.get("favourite")))
        self.table.removeRequested.connect(lambda: self.remove_from_library(self.table.selected_paths()))
        self.table.trashRequested.connect(lambda: self.delete_files(self.table.selected_paths()))
        inner.addWidget(self.table, 1)
        self.empty = QLabel()
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setObjectName("Muted")
        self.empty.setWordWrap(True)
        self.empty.hide()
        inner.addWidget(self.empty, 1)
        h.addLayout(inner, 1)
        v.addWidget(self.lower, 1)
        return page

    def _fill_sort_combo(self):
        self.sort_combo.blockSignals(True)
        self.sort_combo.clear()
        for key in cm_library.ALBUM_SORTS:
            self.sort_combo.addItem(tr("sort." + key), key)
        self.sort_combo.setCurrentIndex(max(0, self.sort_combo.findData(settings.get("album_sort", "artist"))))
        self.sort_combo.blockSignals(False)

    def _retranslate_local(self):
        for i, key in enumerate(("panel.lyrics", "panel.info", "panel.queue")):
            self.rtabs.setTabText(i, tr(key))
        self.table.model_.headerDataChanged.emit(Qt.Horizontal, 0, len(cm_widgets.COLUMNS) - 1)
        self.empty.setText(tr("lib.empty"))
        if hasattr(self, "sort_combo"):
            self._fill_sort_combo()

    # ================================================================ theme / language
    def set_theme(self, mode):
        settings["theme"] = mode
        self.acts["theme_" + mode].setChecked(True)
        self.apply_theme()

    def _system_theme_changed(self, *_):
        if settings.get("theme") == "system":
            self.apply_theme()

    def apply_theme(self):
        cm_theme.apply()
        cm_theme.set_windows_dark_titlebar(self)
        self._refresh_icons()
        self.lyrics._restyle()
        self.reload_sidebar()
        self.reload_library(keep=True)

    def _refresh_icons(self):
        self.transport.refresh_icons()

    def set_lang(self, code):
        settings["language"] = code
        set_language(code)
        cm_widgets.retranslate_all()
        self._retranslate_local()
        self.about.build()
        self.reload_sidebar()
        self.reload_library(keep=True)
        self._update_stats()
        self._update_modes()
        self._show_info()
        if not self.lyrics.lines:
            self._set_lyrics_text(self._lyrics_text, self.current_lyrics_source)

    # ================================================================ tabs and pages
    def select_tab(self, key):
        self.header.select(key)
        self.ribbon.show_page(key)
        if key == "about":
            if self.center.currentIndex() != 2:
                self._prev_page = self.center.currentIndex()
            self.center.setCurrentIndex(2)
        elif self.center.currentIndex() == 2:
            self.center.setCurrentIndex(self._prev_page)

    def show_page(self, i):
        if self.header.buttons["about"].isChecked():
            self.select_tab("home")
        self.center.setCurrentIndex(i)

    def toggle_sidebar(self):
        on = not self.side.isVisible()
        self.side.setVisible(on)
        settings["show_sidebar"] = on
        self.acts["toggle_sidebar"].setChecked(on)

    def toggle_right(self):
        on = not self.right.isVisible()
        self.right.setVisible(on)
        settings["show_right"] = on
        self.acts["toggle_right"].setChecked(on)
        if on:
            self.rtabs.setCurrentIndex(2 if self.player.has_video() else self.rtabs.currentIndex())

    def toggle_on_top(self):
        on = not bool(self.windowFlags() & Qt.WindowStaysOnTopHint)
        settings["always_on_top"] = on
        self.setWindowFlag(Qt.WindowStaysOnTopHint, on)
        self.acts["always_on_top"].setChecked(on)
        self.show()

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal() if not self._normal_state else (self.showMaximized() if self._normal_state == "max" else self.showNormal())
            for w, vis in self._full_hidden:
                w.setVisible(vis)
            self.setCursor(Qt.ArrowCursor)
        else:
            if self._mini_geometry is not None:
                self.toggle_mini()
            self._normal_state = "max" if self.isMaximized() else "normal"
            self.center.setCurrentIndex(1)
            self._full_hidden = [(w, w.isVisible()) for w in (self.header, self.ribbon, self.side, self.right, self.statusw)]
            for w, _ in self._full_hidden:
                w.hide()
            self.showFullScreen()

    def toggle_mini(self):
        if self._mini_geometry is None:
            if self.isFullScreen():
                self.toggle_fullscreen()
            self._mini_geometry = (self.saveGeometry(), self.isMaximized())
            self._mini_hidden = [(w, w.isVisible()) for w in (self.header, self.ribbon, self.body, self.statusw)]
            for w, _ in self._mini_hidden:
                w.hide()
            self.transport.set_mini(True)
            self.showNormal()
            self.setMinimumSize(0, 0)
            self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
            self.show()
            self.resize(560, self.transport.height())
            self.acts["mini"].setChecked(True)
        else:
            geo, was_max = self._mini_geometry
            self._mini_geometry = None
            for w, vis in self._mini_hidden:
                w.setVisible(vis)
            self.transport.set_mini(False)
            self.setWindowFlag(Qt.WindowStaysOnTopHint, bool(settings.get("always_on_top")))
            self.restoreGeometry(geo)
            self.showMaximized() if was_max else self.show()

    # ================================================================ opening media
    def _media_filter(self):
        exts = " ".join("*" + e for e in sorted(MEDIA_EXT | PLAYLIST_EXT))
        return f"{tr('dlg.media_files')} ({exts});;{tr('dlg.all_files')} (*.*)"

    def open_files(self, add=False):
        files, _ = QFileDialog.getOpenFileNames(self, tr("act.open_file"), settings.get("last_dir", ""), self._media_filter())
        if files:
            settings["last_dir"] = os.path.dirname(files[0])
            self.open_paths(files, add=add)

    def open_folder(self, add=False):
        d = QFileDialog.getExistingDirectory(self, tr("act.open_folder"), settings.get("last_dir", ""))
        if d:
            settings["last_dir"] = d
            self.open_paths([d], add=add)

    def open_url(self):
        url, ok = QInputDialog.getText(self, tr("act.open_url"), tr("dlg.url_prompt"), text="https://")
        if ok and is_url(url.strip()):
            self.open_paths([url.strip()])

    def expand_paths(self, paths):
        out = []
        for p in paths:
            if not p:
                continue
            if is_url(p):
                out.append(p)
            elif os.path.isdir(p):
                for root, dirs, files in os.walk(p):
                    dirs.sort(key=str.lower)
                    for f in sorted(files, key=str.lower):
                        if is_media(f):
                            out.append(os.path.join(root, f))
            elif os.path.splitext(p)[1].lower() in PLAYLIST_EXT:
                out.extend(x for x in read_playlist(p) if is_url(x) or os.path.isfile(x))
            elif os.path.splitext(p)[1].lower() in SUBTITLE_EXT:
                self.load_subtitles(p)
            elif os.path.isfile(p):
                out.append(os.path.abspath(p))
        return out

    def open_paths(self, paths, add=False):
        files = self.expand_paths(paths)
        if not files:
            return
        if add:
            self.player.add(files)
        else:
            self.player.set_queue(files, 0, True)
        cm_online.run(cm_library.ensure, [f for f in files if not is_url(f)][:2000])

    def load_playlist_file(self):
        fn, _ = QFileDialog.getOpenFileName(self, tr("act.load_playlist"), settings.get("last_dir", ""),
                                            "Playlists (*.m3u *.m3u8 *.pls)")
        if fn:
            self.open_paths([fn])

    def save_playlist_file(self):
        if not self.player.queue:
            return
        fn, _ = QFileDialog.getSaveFileName(self, tr("act.save_playlist"), os.path.join(settings.get("last_dir", ""),
                                            "playlist.m3u8"), "M3U8 (*.m3u8);;M3U (*.m3u)")
        if fn:
            entries = []
            for p in self.player.queue:
                r = cm_library.get(p) or {}
                title = " - ".join(x for x in (r.get("artist"), r.get("title")) if x) or os.path.basename(p)
                entries.append((p, title, r.get("duration") or -1))
            write_m3u(fn, entries)
            self.message(tr("msg.saved", name=os.path.basename(fn)))

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        files = [u.toLocalFile() or u.toString() for u in e.mimeData().urls()]
        self.open_paths(files, add=bool(e.modifiers() & Qt.ControlModifier))

    # ================================================================ player events
    def _connect_player(self):
        p = self.player
        p.trackChanged.connect(self._show_track)
        p.queueChanged.connect(self._fill_queue)
        p.stateChanged.connect(self._state)
        p.positionChanged.connect(self._position)
        p.modeChanged.connect(self._update_modes)
        p.error.connect(self._play_error)
        p.finished.connect(lambda path, dur: cm_library.played(path, dur / 1000))
        p.tracksChanged.connect(self._tracks_changed)
        p.leaving.connect(self._leaving)
        p.resumed.connect(self._resumed)
        p.resume_lookup = self._resume_lookup
        p.mp.hasVideoChanged.connect(self._has_video)
        p.mp.setVideoOutput(self.video.video)
        try:
            self.video.video.videoSink().subtitleTextChanged.connect(self._embedded_sub)
        except Exception:
            pass

    def _state(self, playing):
        self.transport.set_playing(playing)
        self.acts["play"].setIcon(cm_icons.glossy("pause" if playing else "play", "green", 40))
        self.acts["play"].setText(tr("act.pause") if playing else tr("act.play"))
        self._update_state_label()

    def _update_state_label(self):
        cur = self.player.current()
        if not cur:
            self.st_state.setText(tr("st.ready"))
        else:
            self.st_state.setText(("▶ " + tr("st.playing")) if self.player.is_playing() else ("❚❚ " + tr("st.paused")))

    def _position(self, ms):
        if self.player.is_playing():
            if self._listen_last is not None and 0 < ms - self._listen_last < 1500:
                self._listen_acc += ms - self._listen_last
            self._listen_last = ms
        else:
            self._listen_last = None
        self.lyrics.update_position(ms)
        if self.subs:
            self._set_sub(subtitle_at(self.subs, ms))

    def _embedded_sub(self, text):
        self.embedded_sub = text
        if not self.subs:
            self._set_sub(text)

    def _set_sub(self, text):
        if text != getattr(self, "_last_sub", None):
            self._last_sub = text
            self.video.set_subtitle(text)

    def _play_error(self, msg):
        cur = self.player.current() or ""
        self.message(tr("msg.play_error", name=os.path.basename(cur) or cur, error=msg), 8000)
        if len(self.player.queue) > 1 and self.player.index < len(self.player.queue) - 1:
            QTimer.singleShot(800, lambda: self.player.next())

    def _has_video(self, has):
        if has:
            self.video.set_video_mode()
            if self.center.currentIndex() != 2:
                self.center.setCurrentIndex(1)
        else:
            self._audio_view()
        self._show_info()

    def _tracks_changed(self):
        self._show_info()

    def _show_track(self, index):
        cur = self.player.current()
        self.subs = []
        self._last_sub = None
        self.video.set_subtitle("")
        self.table.model_.set_playing(cur)
        self._mark_queue()
        self._update_state_label()
        if not cur:
            self.current_info = {}
            self.transport.set_track(tr("np.nothing"), tr("np.hint"), None, "")
            self.big_cover.set_cover(None, "")
            self.np_title.setText(tr("np.nothing"))
            self.np_sub.setText(tr("np.hint"))
            self._set_lyrics_text("", "")
            self.video.set_audio_mode(cm_icons.logo_pixmap(256), APP_NAME, tr("np.hint"))
            self.st_tech.setText("")
            self.acts["favourite"].setChecked(False)
            return
        if is_url(cur):
            info = {"title": cur, "artist": tr("np.stream"), "album": "", "duration": 0, "codec": "URL"}
            cover = None
        else:
            info = cm_tags.read(cur)
            if not info.get("title"):
                info["title"] = os.path.splitext(os.path.basename(cur))[0]
            cover = cm_tags.cover(cur) if not is_video(cur) or info.get("has_cover") else None
        self.current_info = info
        self.current_cover = cover
        sub = " — ".join(x for x in (info.get("artist"), info.get("album")) if x)
        if not sub and is_video(cur):
            sub = tr("side.videos") + " · " + os.path.splitext(cur)[1].lstrip(".").upper()
        seed = info.get("album") or info.get("title") or ""
        self.transport.set_track(info["title"], sub or info.get("codec", ""), cover, seed)
        self.big_cover.set_cover(cover, seed)
        self.np_title.setText(info["title"])
        self.np_sub.setText(sub)
        self.setWindowTitle(f'{info["title"]} — {APP_NAME}')
        row = cm_library.get(cur) or {}
        self.acts["favourite"].setChecked(bool(row.get("favourite")))
        self.transport.set_glyph(self.transport.heart, "heartf" if row.get("favourite") else "heart")
        self._audio_view()
        self._show_info()
        # lyrics (music) or subtitles (video)
        if is_video(cur) or is_url(cur):
            self._set_lyrics_text("", "")
            self._auto_subtitles(cur)
            self.rtabs.setCurrentIndex(2)
            self.big_cover.setVisible(bool(cover))
        else:
            self.big_cover.setVisible(True)
            if self.rtabs.currentIndex() == 2:
                self.rtabs.setCurrentIndex(0)
            text = cm_tags.lyrics(cur)
            src = "lrc" if os.path.isfile(cm_tags.lrc_path(cur)) else ("tag" if text else "")
            self._set_lyrics_text(text, src)
            if not text and settings.get("online", True) and settings.get("auto_lyrics", True) and info.get("title"):
                self._auto_lyrics(cur, info)

    def _audio_view(self):
        if self.player.has_video():
            return
        pm = QPixmap()
        if getattr(self, "current_cover", None):
            pm.loadFromData(self.current_cover)
        if pm.isNull():
            pm = cm_icons.placeholder_cover(512, self.current_info.get("album") or self.current_info.get("title") or "")
        info = self.current_info
        self.video.set_audio_mode(pm, info.get("title", APP_NAME),
                                  " — ".join(x for x in (info.get("artist"), info.get("album")) if x))

    def _show_info(self):
        info = self.current_info
        cur = self.player.current()
        if not cur:
            self.info_lab.setText("")
            self.st_tech.setText("")
            return
        rows = []
        for key in ("artist", "album", "albumartist", "year", "genre", "track", "composer"):
            if info.get(key):
                rows.append((tr("field." + key), info[key]))
        tech = [info.get("codec") or ""]
        if info.get("bits") and info.get("samplerate"):
            tech.append(f'{info["bits"]}-bit / {info["samplerate"] / 1000:g} kHz')
        elif info.get("samplerate"):
            tech.append(f'{info["samplerate"] / 1000:g} kHz')
        if info.get("bitrate"):
            tech.append(f'{info["bitrate"]} kbps')
        if self.player.has_video():
            size = self.video.video.nativeSize()
            if size.width() > 0:
                tech.append(f"{int(size.width())}×{int(size.height())}")
            na = len(self.player.audio_tracks())
            ns = len(self.player.subtitle_tracks())
            if na > 1:
                tech.append(tr("st.audio_tracks", n=na))
            if ns or self.subs:
                tech.append(tr("st.subtitles"))
        tech_text = " · ".join(t for t in tech if t)
        rows.append((tr("info.format"), tech_text))
        if info.get("duration"):
            rows.append((tr("info.duration"), fmt_time(info["duration"])))
        r = cm_library.get(cur) if not is_url(cur) else None
        if r:
            rows.append((tr("col.plays"), str(r.get("play_count") or 0)))
        rows.append((tr("info.file"), cur))
        c = cm_theme.colours()
        self.info_lab.setText("<table cellspacing=4>" + "".join(
            f'<tr><td style="color:{c["muted"]};padding-right:10px">{k}</td><td>{_esc(v)}</td></tr>' for k, v in rows) + "</table>")
        self.st_tech.setText(tech_text)

    # ---------------------------------------------------------------- lyrics
    def _set_lyrics_text(self, text, source):
        self._lyrics_text = text
        self.current_lyrics_source = source
        self.lyrics.set_lyrics(text, tr("lyr.none") if self.player.current() else "")
        cur = self.player.current()
        if not cur:
            self.lyr_status.setText("")
            return
        if not text:
            self.lyr_status.setText(tr("lyr.none_hint"))
            return
        kind = tr("lyr.kind_synced") if self.lyrics.synced else tr("lyr.kind_plain")
        where = {"lrc": tr("lyr.src_lrc"), "tag": tr("lyr.src_tag"), "online": "LRCLIB"}.get(source, source)
        self.lyr_status.setText(f"{kind} · {where}")
        if self.lyrics.synced:
            self.lyrics.update_position(self.player.mp.position())

    def _auto_lyrics(self, path, info):
        self._lyrics_req = path
        self.lyr_status.setText(tr("lyr.searching"))

        def done(res, path=path):
            if self.player.current() != path:
                return
            if not res:
                self.lyr_status.setText(tr("lyr.not_found"))
                return
            text = res.get("synced") or res.get("plain") or ""
            if not text:
                self.lyr_status.setText(tr("lyr.not_found"))
                return
            # the playing file is open, so automatic lyrics go into a .lrc file next to it (when allowed)
            if settings.get("save_lrc_file", True) and not cm_tags.save_lyrics(path, text, embed=False, lrc_file=True):
                cm_library.update_fields(path, has_lyrics=1)
            self._set_lyrics_text(text, "online")
        cm_online.run(cm_online.lyrics_best, info.get("artist", ""), info.get("title", ""), info.get("album", ""),
                      info.get("duration", 0), done=done,
                      failed=lambda m, path=path: self.player.current() == path and self.lyr_status.setText(
                          tr("msg.online_error", error=m)))

    def lyrics_font(self, delta):
        settings["lyrics_font"] = self.lyrics.font_size + delta
        self.lyrics.set_font_size(settings["lyrics_font"])

    def lyrics_offset(self, delta):
        self.lyrics.offset += delta
        self.message(tr("msg.lyrics_offset", ms=self.lyrics.offset))
        self.lyrics.update_position(self.player.mp.position())

    def load_lrc(self):
        cur = self.player.current()
        fn, _ = QFileDialog.getOpenFileName(self, tr("act.load_lrc"), os.path.dirname(cur) if cur and not is_url(cur) else "",
                                            "Lyrics (*.lrc *.txt)")
        if fn:
            text = read_text(fn)
            self._set_lyrics_text(text, "lrc")
            if cur and not is_url(cur) and os.path.normcase(fn) != os.path.normcase(cm_tags.lrc_path(cur)):
                if QMessageBox.question(self, APP_NAME, tr("lyr.keep_q")) == QMessageBox.Yes:
                    cm_tags.save_lyrics(cur, text, embed=False, lrc_file=True)
                    cm_library.update_fields(cur, has_lyrics=1)

    # ---------------------------------------------------------------- subtitles
    def _auto_subtitles(self, path):
        if is_url(path):
            return
        base = os.path.splitext(path)[0]
        folder = os.path.dirname(path)
        try:
            names = os.listdir(folder)
        except OSError:
            return
        stem = os.path.basename(base).lower()
        cands = [n for n in names if os.path.splitext(n)[1].lower() in SUBTITLE_EXT and n.lower().startswith(stem)]
        if cands:
            lang = settings.get("language", "en")
            cands.sort(key=lambda n: (f".{lang}." not in n.lower(), len(n)))
            self.load_subtitles(os.path.join(folder, cands[0]), quiet=True)

    def load_subtitles(self, path, quiet=False):
        cues = parse_subtitles(read_text(path))
        if cues:
            self.subs = cues
            self._last_sub = None
            if not quiet:
                self.video.show_osd(tr("osd.subtitles", name=os.path.basename(path)))
            self.message(tr("msg.subs_loaded", name=os.path.basename(path)))
            self._show_info()

    def _fill_sub_menu(self):
        m = self.menus["subtitles"]
        m.clear()
        m.addAction(cm_icons.glossy("file", "purple", 20), tr("sub.load"), self._pick_subtitles)
        off = m.addAction(tr("sub.off"), self._subs_off)
        off.setCheckable(True)
        off.setChecked(not self.subs and self.player.mp.activeSubtitleTrack() < 0)
        tracks = self.player.subtitle_tracks()
        if tracks:
            m.addSeparator()
            active = self.player.mp.activeSubtitleTrack()
            for i, name in tracks:
                a = m.addAction(name, lambda i=i: self._embedded_track(i))
                a.setCheckable(True)
                a.setChecked(i == active and not self.subs)

    def _pick_subtitles(self):
        cur = self.player.current()
        fn, _ = QFileDialog.getOpenFileName(self, tr("sub.load"), os.path.dirname(cur) if cur and not is_url(cur) else "",
                                            "Subtitles (*.srt *.vtt)")
        if fn:
            self.load_subtitles(fn)

    def _subs_off(self):
        self.subs = []
        self.player.mp.setActiveSubtitleTrack(-1)
        self._set_sub("")

    def _embedded_track(self, i):
        self.subs = []
        self.player.mp.setActiveSubtitleTrack(i)

    def _fill_audio_menu(self):
        m = self.menus["audio_track"]
        m.clear()
        tracks = self.player.audio_tracks()
        if not tracks:
            a = m.addAction(tr("menu.no_tracks"))
            a.setEnabled(False)
            return
        active = self.player.mp.activeAudioTrack()
        for i, name in tracks:
            a = m.addAction(name, lambda i=i: self.player.mp.setActiveAudioTrack(i))
            a.setCheckable(True)
            a.setChecked(i == active or (active < 0 and i == 0))

    def _fill_aspect_menu(self):
        m = self.menus["aspect"]
        m.clear()
        cur = self.video.video.aspectRatioMode()
        for key, mode in (("aspect.fit", Qt.KeepAspectRatio), ("aspect.fill", Qt.KeepAspectRatioByExpanding),
                          ("aspect.stretch", Qt.IgnoreAspectRatio)):
            a = m.addAction(tr(key), lambda mode=mode, key=key: (self.video.video.setAspectRatioMode(mode),
                                                                 self.video.show_osd(tr(key))))
            a.setCheckable(True)
            a.setChecked(cur == mode)

    def _fill_speed_menu(self):
        m = self.menus["speed"]
        m.clear()
        rate = self.player.mp.playbackRate()
        for r in (0.5, 0.75, 0.9, 1.0, 1.1, 1.25, 1.5, 1.75, 2.0):
            a = m.addAction(f"{r:g}×", lambda r=r: self.set_rate(r))
            a.setCheckable(True)
            a.setChecked(abs(rate - r) < 0.01)

    def _fill_lang_menu(self):
        m = self.menus["language"]
        m.clear()
        cur = settings.get("language") or "en"
        for code, name in LANGUAGES:
            a = m.addAction(name, lambda code=code: self.set_lang(code))
            a.setCheckable(True)
            a.setChecked(code == cur)

    def _fill_sort_menu(self):
        m = self.menus["queue_sort"]
        m.clear()

        def key_for(field):
            def k(p):
                r = cm_library.get(p) or {}
                if field == "name":
                    return os.path.basename(p).lower()
                if field == "album":
                    return ((r.get("album") or "").lower(), r.get("disc_no") or 0, r.get("track_no") or 0)
                return str(r.get(field) or os.path.basename(p)).lower()
            return k
        for field, key in (("title", "field.title"), ("artist", "field.artist"), ("album", "field.album"),
                           ("name", "sort.filename")):
            m.addAction(tr(key), lambda f=field: self.player.sort_queue(key_for(f)))

    def _fill_playlist_menu(self, menu, paths):
        menu.clear()
        menu.addAction(cm_icons.glossy("add", "teal", 20), tr("act.new_playlist"), lambda: self.new_playlist(paths))
        lists = cm_library.playlists()
        if lists:
            menu.addSeparator()
        for pid, name, n in lists:
            menu.addAction(f"{name}  ({n})", lambda pid=pid, name=name: self._add_to_pl(pid, name, paths))

    def _add_to_pl(self, pid, name, paths):
        paths = [p for p in paths if not is_url(p)]
        if not paths:
            self.message(tr("msg.select_first"))
            return
        cm_library.add_to_playlist(pid, paths)
        self.message(tr("msg.added_to", n=len(paths), name=name))
        self.reload_sidebar()

    # ================================================================ transport helpers
    def change_volume(self, delta):
        self.transport.volume.setValue(max(0, min(100, self.player.volume() + delta)))
        self.video.show_osd(tr("osd.volume", v=self.player.volume()))

    def toggle_mute(self):
        on = not self.player.audio.isMuted()
        self.player.set_muted(on)
        self.acts["mute"].setChecked(on)
        self.transport.set_glyph(self.transport.mute, "mute" if on else "volume")
        self.video.show_osd(tr("osd.muted") if on else tr("osd.volume", v=self.player.volume()))

    def change_rate(self, delta):
        self.set_rate(self.player.mp.playbackRate() + delta)

    def set_rate(self, rate):
        self.player.set_rate(rate)
        self.transport.speed.setText(f"{self.player.mp.playbackRate():g}×")
        self.video.show_osd(tr("osd.speed", v=f"{self.player.mp.playbackRate():g}"))

    def _update_modes(self):
        rep = self.player.repeat
        self.acts["repeat"].setText(tr("act.repeat") + " · " + tr("repeat." + rep))
        self.transport.repeat.setChecked(rep != "off")
        self.transport.set_glyph(self.transport.repeat, "repeatone" if rep == "one" else "repeat")
        self.acts["repeat"].setIcon(cm_icons.glossy("repeatone" if rep == "one" else "repeat",
                                                    "purple" if rep != "off" else "gray", 40))
        self.acts["shuffle"].setChecked(self.player.shuffle)
        self.transport.speed.setText(f"{self.player.mp.playbackRate():g}×")
        self.transport.set_glyph(self.transport.mute, "mute" if self.player.audio.isMuted() else "volume")

    def snapshot(self):
        if not self.player.has_video():
            self.message(tr("msg.no_video"))
            return
        frame = self.video.video.videoSink().videoFrame()
        img = frame.toImage() if frame.isValid() else QImage()
        if img.isNull():
            self.message(tr("msg.snapshot_failed"))
            return
        folder = settings.get("snapshot_dir") or cm_dialogs.default_snapshot_dir()
        os.makedirs(folder, exist_ok=True)
        cur = self.player.current() or "snapshot"
        stem = os.path.splitext(os.path.basename(cur))[0][:60] or "snapshot"
        ms = self.player.mp.position()
        fn = os.path.join(folder, f"{stem} {ms // 3600000:02d}-{(ms // 60000) % 60:02d}-{(ms // 1000) % 60:02d}.png")
        img.save(fn)
        self.video.show_osd(tr("osd.snapshot"))
        self.message(tr("msg.snapshot_saved", path=fn), 6000)

    # ================================================================ queue panel
    def _fill_queue(self):
        self.queue.blockSignals(True)
        self.queue.clear()
        for i, p in enumerate(self.player.queue):
            r = cm_library.get(p) if not is_url(p) else None
            if r:
                second = " · ".join(x for x in (r.get("artist") or "", fmt_time(r["duration"]) if r.get("duration") else "") if x)
                text = (r.get("title") or os.path.basename(p)) + ("\n" + second if second else "")
            else:
                text = os.path.basename(p) if not is_url(p) else p
            it = QListWidgetItem(cm_icons.flat("video" if is_video(p) else "lyrics", "#8a93a3", 18), text)
            it.setData(Qt.UserRole, p)
            self.queue.addItem(it)
        self.queue.blockSignals(False)
        self._mark_queue()
        self._save_queue()

    def _mark_queue(self):
        c = cm_theme.colours()
        for i in range(self.queue.count()):
            it = self.queue.item(i)
            f = it.font()
            f.setBold(i == self.player.index)
            it.setFont(f)
            it.setForeground(QColor(c["accent"]) if i == self.player.index else QColor(c["text"]))
        if 0 <= self.player.index < self.queue.count():
            self.queue.scrollToItem(self.queue.item(self.player.index))

    def _queue_moved(self, _parent, start, _end, _dest, row):
        dst = row if row < start else row - 1
        self.player.queue = [self.queue.item(i).data(Qt.UserRole) for i in range(self.queue.count())]
        if self.player.index == start:
            self.player.index = dst
        elif start < self.player.index <= dst:
            self.player.index -= 1
        elif dst <= self.player.index < start:
            self.player.index += 1
        self.player._rebuild_order(self.player.index)
        self._mark_queue()
        self._save_queue()

    def queue_remove(self):
        rows = [self.queue.row(it) for it in self.queue.selectedItems()]
        self.player.remove_rows(rows)

    def _queue_menu(self, pos):
        m = QMenu(self)
        rows = [self.queue.row(it) for it in self.queue.selectedItems()]
        if rows:
            m.addAction(tr("act.play"), lambda: self.player.play_index(rows[0]))
            m.addAction(tr("act.queue_remove"), self.queue_remove)
            paths = [self.player.queue[r] for r in rows]
            sub = m.addMenu(tr("act.add_to_playlist"))
            self._fill_playlist_menu(sub, paths)
            m.addAction(tr("act.edit_tags"), lambda: self.edit_tags(paths=paths))
            m.addSeparator()
        m.addAction(self.acts["queue_shuffle"])
        m.addAction(self.acts["save_playlist"])
        m.addAction(self.acts["clear_queue"])
        m.exec(self.queue.mapToGlobal(pos))

    def _save_queue(self):
        if settings.get("remember_queue", True):
            settings["queue"] = self.player.queue[:5000]
            settings["queue_index"] = self.player.index

    def _restore_queue(self):
        if settings.get("remember_queue", True) and settings.get("queue"):
            q = [p for p in settings["queue"] if is_url(p) or os.path.exists(p)]
            if q:
                idx = min(max(0, settings.get("queue_index", 0)), len(q) - 1)
                self.player.set_queue(q, idx, play=False)

    # ================================================================ library
    # ---------------------------------------------------------------- sidebar
    def reload_sidebar(self):
        self.sidelist.clear()
        counts = cm_library.counts()
        sel = self.view
        L = self.sidelist
        c = cm_theme.colours()
        L.heading("side.library")
        for key, glyph, colour in (("music", "lyrics", "blue"), ("videos", "video", "purple"), ("favourites", "heartf", "red")):
            it = L.entry(tr("side." + key), cm_icons.glossy(glyph, colour, 22), ("view", key), counts.get(key))
            if sel == (key, None):
                it.setSelected(True)
        L.heading("side.smart")
        smart = [("recent", "clock"), ("most", "star"), ("nocover", "image"), ("nolyrics", "lyrics")]
        if counts.get("missing"):
            smart.append(("missing", "info"))
        for key, glyph in smart:
            warn = key == "missing"
            it = L.entry(tr("side." + key), cm_icons.flat(glyph, "#d97706" if warn else c["muted"], 20), ("view", key),
                         counts.get(key), warn=warn)
            if sel == (key, None):
                it.setSelected(True)
        L.heading("side.playlists")
        for sid, name, _spec in cm_library.smart_playlists():
            it = L.entry(name, cm_icons.flat("star", c["accent"], 20), ("smart", sid))
            it.setToolTip(tr("smart.tip"))
            if sel == ("smart", sid):
                it.setSelected(True)
        for pid, name, n in cm_library.playlists():
            it = L.entry(name, cm_icons.flat("playlist", c["muted"], 20), ("playlist", pid), n)
            it.setToolTip(tr("pl.drop_tip"))
            if sel == ("playlist", pid):
                it.setSelected(True)
        L.entry(tr("act.new_playlist"), cm_icons.flat("add", c["accent"], 20), ("newpl", None))
        L.entry(tr("act.new_smart"), cm_icons.flat("star", c["accent"], 20), ("newsmart", None))

    def _side_clicked(self, it):
        data = it.data(Qt.UserRole)
        if not data:
            return
        kind, value = data
        if kind == "newpl":
            self.new_playlist()
            return
        if kind == "newsmart":
            self.edit_smart(None)
            return
        self.view = (value, None) if kind == "view" else (kind, value)
        self.browse_value = None
        self.table.clear_sort()
        self.show_page(0)
        self.reload_library()

    def _side_menu(self, pos):
        it = self.sidelist.itemAt(pos)
        data = it.data(Qt.UserRole) if it else None
        if not data:
            return
        kind, value = data
        m = QMenu(self)
        if kind == "playlist":
            pid = value
            m.addAction(cm_icons.glossy("play", "green", 20), tr("act.play"),
                        lambda: self._play_list(cm_library.query(playlist=pid)))
            m.addAction(tr("btn.shuffle_all"), lambda: self._play_list(cm_library.query(playlist=pid), shuffle=True))
            m.addSeparator()
            m.addAction(tr("pl.rename"), lambda: self._rename_pl(pid))
            m.addAction(tr("pl.export"), lambda: self._export_pl(pid))
            m.addSeparator()
            m.addAction(tr("pl.delete"), lambda: self._delete_pl(pid))
        elif kind == "smart":
            sid = value
            m.addAction(cm_icons.glossy("play", "green", 20), tr("act.play"), lambda: self._play_list(self._smart_rows(sid)))
            m.addAction(tr("btn.shuffle_all"), lambda: self._play_list(self._smart_rows(sid), shuffle=True))
            m.addSeparator()
            m.addAction(cm_icons.glossy("edit", "purple", 20), tr("smart.edit"), lambda: self.edit_smart(sid))
            m.addAction(tr("smart.to_playlist"), lambda: self._smart_to_playlist(sid))
            m.addAction(tr("pl.export"), lambda: self._export_rows(self._smart_rows(sid), (cm_library.get_smart(sid) or (0, "smart"))[1]))
            m.addSeparator()
            m.addAction(tr("pl.delete"), lambda: self._delete_smart(sid))
        elif kind == "view":
            m.addAction(cm_icons.glossy("play", "green", 20), tr("act.play"), lambda: self._play_list(cm_library.query(value)))
            m.addAction(tr("btn.shuffle_all"), lambda: self._play_list(cm_library.query(value), shuffle=True))
            if value == "missing":
                m.addSeparator()
                m.addAction(tr("lib.forget_missing"), self.forget_missing)
        else:
            return
        m.exec(self.sidelist.mapToGlobal(pos))

    def _side_drop(self, data, paths):
        kind, value = data
        paths = [p for p in paths if not is_url(p)]
        if not paths:
            return
        if kind == "playlist":
            name = next((n for i, n, _ in cm_library.playlists() if i == value), "")
            self._add_to_pl(value, name, paths)
        elif kind == "newpl":
            self.new_playlist(paths)
        elif data == ("view", "favourites"):
            self._set_fav(paths, True)
            self.message(tr("msg.fav_added", n=len(paths)))

    def _queue_drop(self, paths, row):
        paths = [p for p in paths if not is_url(p) and os.path.isfile(p)]
        if paths:
            self.player.insert(paths, row)

    def _rename_pl(self, pid):
        old = next((n for i, n, _ in cm_library.playlists() if i == pid), "")
        name, ok = QInputDialog.getText(self, tr("pl.rename"), tr("pl.name"), text=old)
        if ok and name.strip():
            cm_library.rename_playlist(pid, name.strip())
            self.reload_sidebar()

    def _export_pl(self, pid):
        name = next((n for i, n, _ in cm_library.playlists() if i == pid), "playlist")
        self._export_rows(cm_library.query(playlist=pid), name)

    def _export_rows(self, rows, name):
        fn, _ = QFileDialog.getSaveFileName(self, tr("pl.export"), name + ".m3u8", "M3U8 (*.m3u8)")
        if fn:
            write_m3u(fn, [(r["path"], f'{r["artist"]} - {r["title"]}' if r.get("artist") else r["title"], r["duration"])
                           for r in rows])
            self.message(tr("msg.saved", name=os.path.basename(fn)))

    def _delete_pl(self, pid):
        if QMessageBox.question(self, APP_NAME, tr("pl.delete_q")) == QMessageBox.Yes:
            cm_library.delete_playlist(pid)
            if self.view == ("playlist", pid):
                self.view = ("music", None)
            self.reload_sidebar()
            self.reload_library()

    def new_playlist(self, paths=None):
        name, ok = QInputDialog.getText(self, tr("act.new_playlist"), tr("pl.name"))
        if ok and name.strip():
            pid = cm_library.create_playlist(name.strip())
            paths = paths if isinstance(paths, list) else None
            if paths:
                cm_library.add_to_playlist(pid, [p for p in paths if not is_url(p)])
                self.message(tr("msg.added_to", n=len(paths), name=name.strip()))
            self.reload_sidebar()

    # ---------------------------------------------------------------- smart playlists
    def _smart_rows(self, sid):
        cur = cm_library.get_smart(sid)
        return cm_library.query(smart=cur[2]) if cur else []

    def edit_smart(self, sid=None):
        import cm_smart
        cur = cm_library.get_smart(sid) if sid else None
        dlg = cm_smart.SmartDialog(self, cur[1] if cur else "", cur[2] if cur else None)
        if not dlg.exec():
            return
        name, spec = dlg.result_value
        try:
            sid = cm_library.save_smart(sid, name, spec)
        except sqlite3.IntegrityError:
            QMessageBox.warning(self, APP_NAME, tr("smart.name_taken", name=name))
            return
        self.view = ("smart", sid)
        self.browse_value = None
        self.show_page(0)
        self.reload_sidebar()
        self.reload_library()

    def _delete_smart(self, sid):
        if QMessageBox.question(self, APP_NAME, tr("smart.delete_q")) == QMessageBox.Yes:
            cm_library.delete_smart(sid)
            if self.view == ("smart", sid):
                self.view = ("music", None)
            self.reload_sidebar()
            self.reload_library()

    def _smart_to_playlist(self, sid):
        cur = cm_library.get_smart(sid)
        if not cur:
            return
        name, ok = QInputDialog.getText(self, tr("smart.to_playlist"), tr("pl.name"), text=cur[1] + " " + time.strftime("%Y-%m-%d"))
        if ok and name.strip():
            pid = cm_library.create_playlist(name.strip())
            cm_library.add_to_playlist(pid, [r["path"] for r in cm_library.query(smart=cur[2])])
            self.reload_sidebar()

    # ---------------------------------------------------------------- browsing
    def set_browse(self, mode):
        self.browse = mode
        settings["browse"] = mode
        self.browse_value = None
        self.acts["browse_" + mode].setChecked(True)
        self.show_page(0)
        self.reload_library()

    def set_album_view(self, mode):
        settings["album_view"] = mode
        (self.b_grid if mode == "grid" else self.b_strip).setChecked(True)
        self.acts["album_grid"].setChecked(mode == "grid")
        if mode == "grid" and self._lib_mode() == "albums":
            self.browse_value = None
        self.show_page(0)
        self.reload_library()

    def _tile_size_changed(self, v):
        settings["tile_size"] = v
        self.tiles.configure(tile=v)
        self._fix_strip_height()

    def _album_sort_changed(self, _i):
        settings["album_sort"] = self.sort_combo.currentData() or "artist"
        self.reload_library()

    def _lib_mode(self):
        """What the library page shows: albums / videos (tiles), groups (artists, genres), folders, tracks."""
        view, _ = self.view
        if view in ("playlist", "smart", "missing", "most"):
            return "tracks"
        if self.browse == "folders":
            return "folders"
        if self.browse == "tracks":
            return "tracks"
        if view == "videos":
            return "videos"
        if self.browse in ("artists", "genres"):
            return "groups"
        return "albums"

    def _fix_strip_height(self):
        if self.tiles.mode == "strip":
            self.tiles.apply()

    def reload_library(self, keep=False):
        mode = self._lib_mode()
        grid = settings.get("album_view", "strip") == "grid"
        if keep:
            saved = (self.table.verticalScrollBar().value(), self.tiles.verticalScrollBar().value(),
                     self.tiles.horizontalScrollBar().value())
        tiles = mode in ("albums", "videos")
        album_open = mode == "albums" and self.browse_value is not None
        self.tiles.configure(mode="grid" if grid else "strip", wide=mode == "videos")
        self.tiles.setVisible(tiles and not (grid and album_open))
        self.lib_layout.setStretchFactor(self.tiles, 1 if grid else 0)
        self.lower.setVisible(not (tiles and grid and not album_open))
        self.lib_bar.setVisible(tiles)
        self.group_list.setVisible(mode == "groups")
        self.folder_tree.setVisible(mode == "folders")
        if tiles:
            if mode == "videos":
                self._load_video_tiles()
            else:
                self._load_album_tiles()
        elif mode == "groups":
            self.group_list.clear()
            all_it = QListWidgetItem(tr("browse.all"))
            all_it.setData(Qt.UserRole, None)
            self.group_list.addItem(all_it)
            for name, n in cm_library.groups(self.browse, self.view[0] if self.view[0] in cm_library.WHERE else "music"):
                it = QListWidgetItem(f"{name}  ({n})")
                it.setData(Qt.UserRole, name)
                self.group_list.addItem(it)
                if name == self.browse_value:
                    it.setSelected(True)
        elif mode == "folders":
            view = self.view[0] if self.view[0] in cm_library.WHERE else "all"
            self.folder_tree.load(cm_library.folders(view), settings.get("library_folders", []), tr("lib.other_places"),
                                  cm_icons.flat("open", cm_theme.colours()["muted"], 18))
            if self.browse_value:
                self._select_folder(self.browse_value)
        self._update_bar(mode, grid, album_open)
        self._load_tracks()
        if keep:
            QTimer.singleShot(0, lambda: (self.table.verticalScrollBar().setValue(saved[0]),
                                          self.tiles.verticalScrollBar().setValue(saved[1]),
                                          self.tiles.horizontalScrollBar().setValue(saved[2])))

    def _update_bar(self, mode, grid, album_open):
        self.b_back.setVisible(mode == "albums" and grid and album_open)
        self.b_back.setIcon(cm_icons.flat("prev", cm_theme.colours()["accent"], 16))
        self.sort_label.setVisible(mode == "albums")
        self.sort_combo.setVisible(mode == "albums")
        self.size_icon.setPixmap(cm_icons.flat("grid", cm_theme.colours()["muted"], 16).pixmap(16, 16))
        c = cm_theme.colours()
        self.b_strip.setIcon(cm_icons.flat("list", c["accent"] if not grid else c["muted"], 18))
        self.b_grid.setIcon(cm_icons.flat("grid", c["accent"] if grid else c["muted"], 18))
        n = self.tile_model.rowCount()
        if mode == "videos":
            self.bar_title.setText(tr("lib.n_videos", n=n))
        elif mode == "albums":
            self.bar_title.setText(tr("lib.n_albums", n=n) if not (grid and album_open) else "")

    def _back_to_grid(self):
        self.browse_value = None
        self.reload_library()
        QTimer.singleShot(0, lambda: self.tiles.verticalScrollBar().setValue(getattr(self, "_grid_scroll", 0)))

    def _placeholder(self, key, wide=False):
        cache = self.__dict__.setdefault("_ph_cache", {})
        k = ("v" if wide else "a", sum(map(ord, key or "x")) % 6)
        if k not in cache:
            cache[k] = QIcon(_video_placeholder(key) if wide else cm_icons.placeholder_cover(160, key))
        return cache[k]

    def _load_album_tiles(self):
        view = self.view[0]
        albums = cm_library.albums(view, settings.get("album_sort", "artist"), self.header.search.text().strip())
        self.tile_model.clear()
        self._tile_items = {}
        self._tile_rows = {}
        todo = []
        sel_index = None
        for a in albums:
            who = a["artist"] if a["artist"] is not None else tr("lib.various")
            it = QStandardItem(f'{a["album"]}\n{who}')
            it.setData(a["key"], Qt.UserRole)
            it.setToolTip(" · ".join(x for x in (a["album"], who, a["year"], tr("lib.n_tracks", n=a["count"])) if x))
            tp = cm_library.thumb_path("album|" + a["key"])
            if os.path.isfile(tp):
                it.setIcon(QIcon(tp))
            else:
                it.setIcon(self._placeholder(a["album"]))
                todo.append((a["key"], a["sample"], tp))
            self._tile_items[a["key"]] = it
            self._tile_rows[a["key"]] = a
            self.tile_model.appendRow(it)
            if a["key"] == self.browse_value:
                sel_index = it.index()
        if sel_index is not None:
            from PySide6.QtCore import QItemSelectionModel
            self.tiles.selectionModel().setCurrentIndex(sel_index, QItemSelectionModel.ClearAndSelect)
            self.tiles.scrollTo(sel_index)
        if todo:
            cm_online.run(_make_thumbs, todo, progress=self._thumb_ready)

    def _thumb_ready(self, _i, _n, key):
        it = getattr(self, "_tile_items", {}).get(key)
        tp = cm_library.thumb_path("album|" + key)
        if it is not None and os.path.isfile(tp):
            try:
                it.setIcon(QIcon(tp))
            except RuntimeError:
                pass

    def _load_video_tiles(self):
        rows = cm_library.query(self.view[0], search=self.header.search.text().strip())
        self.tile_model.clear()
        self._tile_items = {}
        self._tile_rows = {r["path"]: r for r in rows}
        self._video_rows = rows
        self.thumbnailer.clear()
        for r in rows:
            p = r["path"]
            dur = r.get("duration") or 0
            sub = fmt_time(dur) if dur else os.path.splitext(p)[1].lstrip(".").upper()
            it = QStandardItem(f'{r.get("title") or os.path.basename(p)}\n{sub}')
            it.setData(p, Qt.UserRole)
            if r.get("resume_ms") and dur:
                it.setData(min(1.0, r["resume_ms"] / 1000.0 / dur), Qt.UserRole + 2)
                it.setToolTip(tr("lib.resume_tip", time=fmt_time(r["resume_ms"] / 1000)))
            else:
                it.setToolTip(p)
            tp = cm_library.video_thumb_path(p, r.get("mtime"))
            if os.path.isfile(tp):
                it.setIcon(QIcon(tp))
            else:
                it.setIcon(self._placeholder(r.get("title") or p, wide=True))
                if not r.get("missing") and os.path.isfile(p):
                    self.thumbnailer.request(p, tp)
            self._tile_items[p] = it
            self.tile_model.appendRow(it)

    def _video_thumb_ready(self, path, out):
        it = getattr(self, "_tile_items", {}).get(path)
        if it is not None:
            try:
                it.setIcon(QIcon(out))
            except RuntimeError:
                pass
        if path == self.player.current() and not self.player.has_video():
            pass

    def _tile_clicked(self, idx):
        if self._lib_mode() == "videos":
            return
        key = idx.data(Qt.UserRole)
        if settings.get("album_view") == "grid":
            if QApplication.keyboardModifiers() & (Qt.ControlModifier | Qt.ShiftModifier):
                return
            self._grid_scroll = self.tiles.verticalScrollBar().value()
            self.browse_value = key
            self.reload_library()
        else:
            if QApplication.keyboardModifiers() & (Qt.ControlModifier | Qt.ShiftModifier):
                return
            self.browse_value = None if self.browse_value == key else key
            if self.browse_value is None:
                self.tiles.clearSelection()
            self.table.clear_sort()
            self._load_tracks()

    def _tile_activated(self, idx):
        key = idx.data(Qt.UserRole)
        if self._lib_mode() == "videos":
            rows = getattr(self, "_video_rows", [])
            start = next((i for i, r in enumerate(rows) if r["path"] == key), 0)
            self._play_list(rows, start)
        else:
            self._play_list(cm_library.query(self.view[0], album_key=key))

    def _tile_paths(self, keys):
        if self._lib_mode() == "videos":
            return [k for k in keys if k]
        out = []
        for k in keys:
            out += [r["path"] for r in cm_library.query(self.view[0], album_key=k)]
        return out

    def _tile_selected_paths(self):
        keys = [i.data(Qt.UserRole) for i in sorted(self.tiles.selectedIndexes(), key=lambda i: i.row())]
        return self._tile_paths(keys)

    def _tile_menu(self, pos):
        idx = self.tiles.indexAt(pos)
        if not idx.isValid():
            return
        if not self.tiles.selectionModel().isSelected(idx):
            self.tiles.setCurrentIndex(idx)
        paths = self._tile_selected_paths()
        rows = self._rows_for(paths)
        self._track_menu(rows, self.tiles.viewport().mapToGlobal(pos), source="tiles")

    def _group_clicked(self, it):
        self.browse_value = it.data(Qt.UserRole)
        self._load_tracks()

    def _group_menu(self, pos):
        it = self.group_list.itemAt(pos)
        if it is None or it.data(Qt.UserRole) is None:
            return
        name = it.data(Qt.UserRole)
        key = "artist" if self.browse == "artists" else "genre"
        rows = cm_library.query(self.view[0] if self.view[0] in cm_library.WHERE else "music", **{key: name})
        self._track_menu(rows, self.group_list.viewport().mapToGlobal(pos), source="group")

    def _folder_clicked(self, it):
        self.browse_value = it.data(0, Qt.UserRole)
        self._load_tracks()

    def _select_folder(self, folder):
        from PySide6.QtWidgets import QTreeWidgetItemIterator
        itr = QTreeWidgetItemIterator(self.folder_tree)
        while itr.value():
            item = itr.value()
            if item.data(0, Qt.UserRole) == folder:
                self.folder_tree.setCurrentItem(item)
                return
            itr += 1

    def _folder_menu(self, pos):
        it = self.folder_tree.itemAt(pos)
        folder = it.data(0, Qt.UserRole) if it else None
        if not folder:
            return
        view = self.view[0] if self.view[0] in cm_library.WHERE else "all"
        rows = cm_library.query(view, folder=folder)
        extra = [(tr("lib.rescan_folder"), lambda: self.rescan_folders([folder]))]
        roots = [os.path.normpath(r) for r in settings.get("library_folders", [])]
        if os.path.normpath(folder) in roots:
            extra.append((tr("lib.unwatch_folder"), lambda: self._remove_root(folder)))
        self._track_menu(rows, self.folder_tree.viewport().mapToGlobal(pos), source="folder", extra=extra)

    def _remove_root(self, folder):
        if QMessageBox.question(self, APP_NAME, tr("lib.unwatch_q", folder=folder)) != QMessageBox.Yes:
            return
        settings["library_folders"] = [f for f in settings.get("library_folders", [])
                                       if os.path.normpath(f) != os.path.normpath(folder)]
        settings.save()
        cm_library.remove_folder(folder)
        self.browse_value = None
        self.setup_watch()
        self._library_changed()

    def _load_tracks(self):
        view, val = self.view
        mode = self._lib_mode()
        search = self.header.search.text().strip()
        kw = {"search": search}
        title = ""
        if view == "playlist":
            kw["playlist"] = val
            title = next((n for i, n, _ in cm_library.playlists() if i == val), "")
        elif view == "smart":
            cur = cm_library.get_smart(val)
            kw["smart"] = cur[2] if cur else {"rules": []}
            title = cur[1] if cur else ""
        else:
            kw["view"] = view
            title = tr("side." + view)
        if self.browse_value is not None:
            if mode == "albums":
                kw["album_key"] = self.browse_value
            elif mode == "groups":
                kw["artist" if self.browse == "artists" else "genre"] = self.browse_value
                title = self.browse_value
            elif mode == "folders":
                kw["folder"] = self.browse_value
                title = os.path.basename(self.browse_value.rstrip("\\/")) or self.browse_value
        if mode == "videos" and settings.get("album_view") == "grid":
            rows = []
        else:
            rows = cm_library.query(**kw)
        if mode == "albums" and self.browse_value is not None and not rows and not search:
            self.browse_value = None
            self.reload_library()
            return
        self.table.model_.set_rows(rows)
        self.table.model_.set_playing(self.player.current())
        has = bool(rows)
        self.table.setVisible(has)
        self.empty.setVisible(not has)
        if not has:
            if view == "missing":
                self.empty.setText(tr("lib.no_missing"))
            elif view == "smart":
                self.empty.setText(tr("smart.empty"))
            else:
                self.empty.setText(tr("lib.empty") if not settings.get("library_folders") else tr("lib.nothing"))
        total = sum(r.get("duration") or 0 for r in rows)
        if mode == "albums" and self.browse_value is not None and rows:
            a = getattr(self, "_tile_rows", {}).get(self.browse_value) or {}
            r0 = rows[0]
            who = a.get("artist") if a else (r0.get("albumartist") or r0.get("artist"))
            if who is None:
                who = tr("lib.various")
            self.head_title.setText(r0.get("album") or a.get("album") or "")
            bits = [who or "", r0.get("year") or "", r0.get("genre") or "", tr("lib.n_tracks", n=len(rows)), fmt_time(total)]
            self.head_sub.setText(" · ".join(b for b in bits if b))
            sample = next((r["path"] for r in rows if not r.get("missing")), r0["path"])
            self.head_cover.set_cover(cm_tags.cover(sample) if os.path.isfile(sample) else None, r0.get("album") or "")
        else:
            self.head_title.setText(title)
            self.head_sub.setText(" · ".join(x for x in (tr("lib.n_tracks", n=len(rows)), fmt_time(total) if total else "") if x))
            self.head_cover.set_cover(None, title)
        extra = {"missing": "lib.forget_missing", "smart": "smart.edit"}.get(view)
        self.b_extra.setVisible(bool(extra) and has or view == "smart")
        if extra:
            self.b_extra.setText(tr(extra))
        self.b_more.setVisible(has)
        self.b_play_all.setEnabled(has)
        self.b_shuffle_all.setEnabled(has)
        self.album_head.setVisible(True)

    def _head_extra(self):
        if self.view[0] == "missing":
            self.forget_missing()
        elif self.view[0] == "smart":
            self.edit_smart(self.view[1])

    # ---------------------------------------------------------------- playing from the library
    def _play_list(self, rows, start=0, shuffle=False):
        rows = list(rows)
        if not rows:
            return
        start = max(0, min(start, len(rows) - 1))
        if rows[start].get("missing") and not shuffle:
            self._missing_prompt(rows[start])
            return
        playable = [r for r in rows if not r.get("missing")]
        if not playable:
            self._missing_prompt(rows[start])
            return
        paths = [r["path"] for r in playable]
        idx = paths.index(rows[start]["path"]) if rows[start]["path"] in paths else 0
        if shuffle:
            self.player.set_shuffle(True)
            idx = random.randrange(len(paths))
        self.player.set_queue(paths, idx, True)
        if is_video(paths[idx]):
            self.center.setCurrentIndex(1)

    def play_rows(self, start, shuffle=False):
        self._play_list(self.table.model_.rows, start, shuffle)

    def _table_activated(self, idx):
        if self.table.state() == QAbstractItemView.EditingState:
            return
        self.play_rows(idx.row())

    def _rows_for(self, paths):
        got = cm_library.get_many(paths)
        return [got[p] for p in paths if p in got]

    def _table_menu(self, pos):
        rows = self.table.selected_rows()
        if rows:
            self._track_menu(rows, self.table.viewport().mapToGlobal(pos), source="table")

    def _track_menu(self, rows, gpos, source="table", extra=None):
        """The one right-click menu for tracks, albums, artists, genres, folders and videos."""
        if not rows:
            return
        paths = [r["path"] for r in rows]
        playable = [r["path"] for r in rows if not r.get("missing")]
        audio = [r["path"] for r in rows if r.get("kind") != "video" and not r.get("missing")]
        m = QMenu(self)
        m.addAction(cm_icons.glossy("play", "green", 20), tr("act.play"), lambda: self._play_list(rows))
        if len(rows) > 1:
            m.addAction(cm_icons.glossy("shuffle", "purple", 20), tr("btn.shuffle_all"),
                        lambda: self._play_list(rows, shuffle=True))
        m.addAction(tr("menu.play_next"), lambda: self.player.insert_next(playable))
        m.addAction(tr("menu.add_queue"), lambda: self.player.add(playable))
        sub = m.addMenu(cm_icons.glossy("playlist", "teal", 20), tr("act.add_to_playlist"))
        self._fill_playlist_menu(sub, paths)
        if source == "table" and self.view[0] == "playlist":
            pid = self.view[1]
            m.addAction(tr("menu.remove_from_pl"), lambda: (cm_library.remove_from_playlist(pid, paths),
                                                           self.reload_library(keep=True), self.reload_sidebar()))
        m.addSeparator()
        if len(rows) == 1 and rows[0].get("missing"):
            m.addAction(cm_icons.glossy("search", "orange", 20), tr("lib.locate"), lambda: self.locate_missing(rows[0]))
        if playable:
            m.addAction(cm_icons.glossy("tag", "orange", 20), tr("act.edit_tags") + "\tCtrl+T",
                        lambda: self.edit_tags(paths=playable))
        if audio:
            m.addAction(cm_icons.glossy("image", "pink", 20), tr("act.find_cover"), lambda: self.find_cover(paths=audio))
            if len(audio) == 1:
                m.addAction(cm_icons.glossy("lyrics", "pink", 20), tr("act.find_lyrics"),
                            lambda: self.find_lyrics(path=audio[0]))
            else:
                m.addAction(cm_icons.glossy("cloud", "purple", 20), tr("menu.lyrics_for_these"),
                            lambda: self.batch_lyrics(paths=audio))
        rate = m.addMenu(tr("menu.rating"))
        for n in range(6):
            rate.addAction("★" * n + "☆" * (5 - n) if n else tr("menu.no_rating"), lambda n=n: self._set_rating(paths, n))
        fav = all(r.get("favourite") for r in rows)
        m.addAction(cm_icons.flat("heartf" if not fav else "heart", "#e5484d", 18),
                    tr("menu.unfavourite") if fav else tr("menu.favourite"), lambda: self._set_fav(paths, not fav))
        m.addSeparator()
        if extra:
            for text, fn in extra:
                m.addAction(text, fn)
        m.addAction(cm_icons.glossy("open", "blue", 20), tr("menu.show_folder"), lambda: self.show_in_folder(paths[0]))
        m.addSeparator()
        n = len(rows)
        m.addAction(cm_icons.glossy("remove", "gray", 20), tr("menu.remove_lib", n=n) + "\tDel",
                    lambda: self.remove_from_library(paths))
        m.addAction(cm_icons.glossy("trash", "red", 20), tr("menu.delete_files", n=n) + "\tShift+Del",
                    lambda: self.delete_files(paths))
        m.exec(gpos)

    def _update_rows_in_place(self, paths, **fields):
        """Change rows of the table without reloading (keeps the scroll position and selection)."""
        model = self.table.model_
        want = set(paths)
        for i, r in enumerate(model.rows):
            if r["path"] in want:
                r.update(fields)
                model.row_changed(i)

    def _set_rating(self, paths, n):
        for p in paths:
            cm_library.update_fields(p, rating=n)
        self._update_rows_in_place(paths, rating=n)

    def _rate_row(self, row, n):
        self._set_rating([row["path"]], n)

    def _set_fav(self, paths, on):
        for p in paths:
            cm_library.update_fields(p, favourite=int(on))
        if self.view == ("favourites", None):
            self.reload_library(keep=True)
        else:
            self._update_rows_in_place(paths, favourite=int(on))
        self.reload_sidebar()
        if self.player.current() in paths:
            self.acts["favourite"].setChecked(on)
            self.transport.set_glyph(self.transport.heart, "heartf" if on else "heart")

    def toggle_favourite(self):
        cur = self.player.current()
        if not cur or is_url(cur):
            self.acts["favourite"].setChecked(False)
            return
        cm_library.ensure([cur])
        r = cm_library.get(cur) or {}
        self._set_fav([cur], not r.get("favourite"))

    def _edit_cell(self, row, field, value):
        """F2 in the track table: write one tag straight into the file."""
        path = row["path"]
        if not os.path.isfile(path) or not cm_tags.can_write(path):
            QMessageBox.information(self, APP_NAME, tr("tag.cannot_write"))
            return None
        if field == "year" and value and not re.fullmatch(r"\d{4}", value):
            self.message(tr("tag.bad_year"))
            return None
        if field == "track" and value and not re.fullmatch(r"\d{1,3}(/\d{1,3})?", value):
            self.message(tr("tag.bad_track"))
            return None
        try:
            self.release_file(path, lambda: cm_tags.write(path, {field: value}))
        except Exception as e:
            QMessageBox.warning(self, APP_NAME, tr("msg.save_failed") + f"\n\n{os.path.basename(path)}: {e}")
            return None
        old_key = row.get("album_key") or ""
        cm_library.refresh_file(path)
        new = cm_library.get(path)
        if new and (new.get("album_key") != old_key or path == self.player.current()):
            QTimer.singleShot(0, lambda: self._after_tag_change([path], old_keys=[old_key]))
        return new

    # ---------------------------------------------------------------- removing and deleting
    def remove_from_library(self, paths, confirm=True):
        """Hide from the library; the files stay. Missing files are dropped completely."""
        paths = [p for p in dict.fromkeys(paths) if p and not is_url(p)]
        if not paths:
            self.message(tr("msg.select_first"))
            return False
        if confirm and QMessageBox.question(self, APP_NAME, tr("lib.remove_q", n=len(paths))) != QMessageBox.Yes:
            return False
        rows = cm_library.get_many(paths)
        gone = [p for p in paths if rows.get(p, {}).get("missing")]
        keep = [p for p in paths if p not in gone]
        if gone:
            cm_library.forget(gone)
        if keep:
            cm_library.hide(keep)
        self.message(tr("msg.removed", n=len(paths)), 7000)
        self._library_changed()
        return True

    def delete_files(self, paths, confirm=True):
        """Move files to the Recycle Bin (asks first)."""
        paths = [p for p in dict.fromkeys(paths) if p and not is_url(p)]
        if not paths:
            self.message(tr("msg.select_first"))
            return False
        if confirm:
            box = QMessageBox(QMessageBox.Warning, APP_NAME, tr("lib.delete_q", n=len(paths)),
                              QMessageBox.Yes | QMessageBox.No, self)
            box.setDefaultButton(QMessageBox.No)
            if len(paths) <= 8:
                box.setInformativeText("\n".join(os.path.basename(p) for p in paths))
            if box.exec() != QMessageBox.Yes:
                return False
        want = set(paths)
        if self.player.current() in want:
            self.player.release()
            QApplication.processEvents()
            time.sleep(0.2)
        rows = [i for i, p in enumerate(self.player.queue) if p in want]
        if rows:
            self.player.remove_rows(rows)
        done, failed = cm_library.trash(paths)
        if failed:
            QMessageBox.warning(self, APP_NAME, tr("lib.delete_failed") + "\n\n" +
                                "\n".join(os.path.basename(p) for p, _r in failed[:15]))
        if done:
            self.message(tr("msg.deleted", n=len(done)), 7000)
        self._library_changed()
        return bool(done)

    def _library_changed(self):
        self.reload_sidebar()
        self.reload_library(keep=True)
        self._update_stats()

    # ---------------------------------------------------------------- missing files
    def _missing_prompt(self, row):
        box = QMessageBox(QMessageBox.Warning, APP_NAME, tr("lib.missing_q", name=os.path.basename(row["path"])),
                          QMessageBox.Cancel, self)
        box.setInformativeText(row["path"])
        loc = box.addButton(tr("lib.locate"), QMessageBox.AcceptRole)
        rem = box.addButton(tr("act.remove_lib"), QMessageBox.DestructiveRole)
        box.exec()
        if box.clickedButton() is loc:
            self.locate_missing(row)
        elif box.clickedButton() is rem:
            cm_library.forget([row["path"]])
            self._library_changed()

    def locate_missing(self, row):
        old = row["path"]
        start = os.path.dirname(old)
        while start and not os.path.isdir(start) and os.path.dirname(start) != start:
            start = os.path.dirname(start)
        ext = os.path.splitext(old)[1]
        fn, _ = QFileDialog.getOpenFileName(self, tr("lib.locate_title", name=os.path.basename(old)), start,
                                            f"{tr('dlg.media_files')} (*{ext});;{tr('dlg.all_files')} (*.*)")
        if not fn:
            return
        others = cm_library.relocate(old, os.path.normpath(fn))
        self.message(tr("msg.located", n=others) if others else tr("msg.located_one"), 7000)
        if others:
            QMessageBox.information(self, APP_NAME, tr("msg.located", n=others))
        self._library_changed()

    def forget_missing(self):
        rows = cm_library.query("missing")
        if not rows:
            self.message(tr("lib.no_missing"))
            return
        if QMessageBox.question(self, APP_NAME, tr("lib.forget_missing_q", n=len(rows))) != QMessageBox.Yes:
            return
        cm_library.forget([r["path"] for r in rows])
        if self.view == ("missing", None):
            self.view = ("music", None)
        self._library_changed()

    def show_missing(self):
        if not cm_library.counts().get("missing"):
            QMessageBox.information(self, APP_NAME, tr("lib.no_missing"))
            return
        self.view = ("missing", None)
        self.browse_value = None
        self.show_page(0)
        self.reload_sidebar()
        self.reload_library()

    # ---------------------------------------------------------------- tools
    def show_hidden(self):
        dlg = cm_dialogs.HiddenDialog(self)
        dlg.exec()
        if dlg.changed:
            self._library_changed()

    def show_duplicates(self):
        import cm_duplicates
        dlg = cm_duplicates.DuplicatesDialog(self)
        dlg.exec()
        if dlg.changed:
            self._library_changed()

    def show_statistics(self):
        cm_dialogs.StatsDialog(self).exec()

    def backup_library(self):
        name = f"{APP_NAME} backup {time.strftime('%Y-%m-%d')}{cm_library.BACKUP_EXT}"
        fn, _ = QFileDialog.getSaveFileName(self, tr("act.backup"), os.path.join(os.path.expanduser("~"), name),
                                            f"{tr('dlg.backup_files')} (*{cm_library.BACKUP_EXT})")
        if not fn:
            return
        if not fn.lower().endswith(cm_library.BACKUP_EXT):
            fn += cm_library.BACKUP_EXT
        self._save_state()
        try:
            cm_library.backup(fn, settings.path)
        except Exception as e:
            QMessageBox.warning(self, APP_NAME, tr("msg.backup_failed") + f"\n\n{e}")
            return
        self.message(tr("msg.backup_saved", name=os.path.basename(fn)), 7000)

    def restore_library(self):
        fn, _ = QFileDialog.getOpenFileName(self, tr("act.restore"), os.path.expanduser("~"),
                                            f"{tr('dlg.backup_files')} (*{cm_library.BACKUP_EXT})")
        if not fn:
            return
        try:
            info = cm_library.read_backup_info(fn)
        except cm_library.BackupError:
            QMessageBox.warning(self, APP_NAME, tr("msg.not_backup"))
            return
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(info.get("created") or 0))
        if QMessageBox.question(self, APP_NAME, tr("lib.restore_q", date=when)) != QMessageBox.Yes:
            return
        if self.batch_task is not None:
            self.batch_task.cancelled = True
        try:
            data = cm_library.restore(fn)
        except Exception as e:
            QMessageBox.warning(self, APP_NAME, tr("msg.not_backup") + f"\n\n{e}")
            return
        keep = ("geometry", "queue", "queue_index")
        for k, v in data.items():
            if k in settings and k not in keep:
                settings[k] = v
        settings.save()
        self.view = ("music", None)
        self.browse_value = None
        self.browse = settings.get("browse", "albums")
        self.acts["browse_" + self.browse].setChecked(True)
        set_language(settings.get("language") or "en")
        self.set_lang(settings.get("language") or "en")
        self.apply_theme()
        self._library_changed()
        self.setup_watch()
        QMessageBox.information(self, APP_NAME, tr("msg.restored"))
        self.rescan(quiet=True)

    # ---------------------------------------------------------------- watching the library folders
    def setup_watch(self):
        dirs = self.watcher.directories()
        if dirs:
            self.watcher.removePaths(dirs)
        self.periodic_timer.stop()
        self.acts["watch_folders"].setChecked(bool(settings.get("watch_folders", True)))
        if not settings.get("watch_folders", True):
            return
        roots = [f for f in settings.get("library_folders", []) if os.path.isdir(f)]
        if not roots:
            return
        self.periodic_timer.start()
        cm_online.run(_watch_dirs, roots, done=self._add_watch_dirs)

    def _add_watch_dirs(self, dirs):
        if not settings.get("watch_folders", True):
            return
        have = set(self.watcher.directories())
        new = [d for d in dirs if d not in have]
        if new:
            self.watcher.addPaths(new)

    def toggle_watch(self, on):
        settings["watch_folders"] = bool(on)
        self.setup_watch()
        self.message(tr("msg.watch_on") if on else tr("msg.watch_off"))

    def _dir_changed(self, d):
        self._pending_dirs.add(d)
        self.watch_timer.start()

    def _watch_scan(self):
        if self.watch_task is not None or self.batch_task is not None:
            self.watch_timer.start()
            return
        dirs = sorted(self._pending_dirs, key=len)
        self._pending_dirs = set()
        top = []
        for d in dirs:
            if not any(d == t or d.startswith(t.rstrip("\\/") + os.sep) for t in top):
                top.append(d)
        if top:
            self.watch_task = cm_online.run(cm_library.scan, top, done=self._watch_done,
                                            failed=lambda _m: setattr(self, "watch_task", None))

    def changeEvent(self, e):
        super().changeEvent(e)
        from PySide6.QtCore import QEvent
        if e.type() == QEvent.ActivationChange and self.isActiveWindow() and settings.get("watch_folders", True) \
                and time.monotonic() - self._last_quiet_scan > 120:
            QTimer.singleShot(500, self._periodic_scan)

    def _periodic_scan(self):
        if self.watch_task is not None or self.batch_task is not None:
            return
        self._last_quiet_scan = time.monotonic()
        folders = [f for f in settings.get("library_folders", []) if os.path.isdir(f)]
        if folders:
            self.watch_task = cm_online.run(cm_library.scan, folders, done=self._watch_done,
                                            failed=lambda _m: setattr(self, "watch_task", None))

    def _watch_done(self, res):
        self.watch_task = None
        if res.get("added") or res.get("missing") or res.get("back"):
            self._library_changed()
            self.message(tr("msg.watch_found", added=res.get("added", 0), missing=res.get("missing", 0)), 6000)
            roots = [f for f in settings.get("library_folders", []) if os.path.isdir(f)]
            if roots and settings.get("watch_folders", True):
                cm_online.run(_watch_dirs, roots, done=self._add_watch_dirs)

    def show_in_folder(self, path):
        if sys.platform == "win32":
            import subprocess
            target = path if os.path.exists(path) else os.path.dirname(path)
            subprocess.Popen(["explorer", "/select,", os.path.normpath(target)])
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path if os.path.isdir(path) else os.path.dirname(path)))

    def add_library_folder(self):
        d = QFileDialog.getExistingDirectory(self, tr("act.add_folder"))
        if d:
            d = os.path.normpath(d)
            folders = settings.get("library_folders", [])
            if d not in folders:
                settings["library_folders"] = folders + [d]
                settings.save()
            self.rescan()
            self.setup_watch()

    def rescan(self, quiet=False):
        folders = [f for f in settings.get("library_folders", []) if os.path.isdir(f)]
        if not folders:
            if not quiet:
                self.add_library_folder()
            return
        self.rescan_folders(folders)

    def rescan_folders(self, folders):
        if self.batch_task is not None:
            return
        self._start_progress(tr("msg.scanning"))
        self.batch_task = cm_online.run(cm_library.scan, folders, done=self._scan_done, failed=self._batch_failed,
                                        progress=self._batch_progress)

    def _scan_done(self, res):
        self._end_progress()
        self.message(tr("msg.scan_done", added=res.get("added", 0), missing=res.get("missing", 0)), 6000)
        self._library_changed()

    def _start_progress(self, text):
        self.st_msg.setText(text)
        self.st_progress.setRange(0, 0)
        self.st_progress.show()
        self.st_cancel.show()

    def _batch_progress(self, i, n, text):
        self.st_progress.setRange(0, max(1, n))
        self.st_progress.setValue(i)
        self.st_msg.setText(f"{i}/{n} · {text[:50]}")

    def _end_progress(self):
        self.batch_task = None
        self.st_progress.hide()
        self.st_cancel.hide()
        self.st_msg.setText("")

    def _batch_failed(self, msg):
        self._end_progress()
        QMessageBox.warning(self, APP_NAME, msg)

    def _cancel_batch(self):
        if self.batch_task is not None:
            self.batch_task.cancelled = True
            self.st_msg.setText(tr("msg.cancelling"))

    def _update_stats(self):
        s = cm_library.stats()
        self.st_stats.setText(tr("st.library", tracks=s["a"], videos=s["v"], albums=s["al"],
                                 size=f'{s["s"] / 1073741824:.1f} GB'))

    # ---------------------------------------------------------------- resume and listening time
    def _resume_lookup(self, path):
        if not settings.get("resume", True):
            return 0
        r = cm_library.get(path)
        return int(r.get("resume_ms") or 0) if r else 0

    def _resumed(self, ms):
        self.video.show_osd(tr("osd.resumed", time=fmt_time(ms / 1000)))
        self.message(tr("msg.resumed", time=fmt_time(ms / 1000)), 6000)

    def _leaving(self, path, pos, dur):
        secs = self._listen_acc / 1000.0
        self._listen_acc = 0
        self._listen_last = None
        if is_url(path):
            return
        if secs >= 5:
            cm_library.record_listen(path, secs)
        if not settings.get("resume", True):
            return
        if not (is_video(path) or dur >= RESUME_MIN_MS):
            return
        near_end = dur > 0 and pos >= dur - max(60000, dur * 0.05)
        if pos < 30000 and not near_end and secs < 5:
            return      # opened but hardly played (e.g. the queue restored at start-up): keep the old position
        new = 0 if (pos < 30000 or near_end) else pos
        cm_library.set_resume(path, new)
        it = getattr(self, "_tile_items", {}).get(path)
        if it is not None and dur > 0:
            try:
                it.setData(new / dur if new else 0, Qt.UserRole + 2)
            except RuntimeError:
                pass

    def _start_over(self):
        cur = self.player.current()
        if cur:
            self.player.seek(0)
            if not is_url(cur):
                cm_library.set_resume(cur, 0)

    # ================================================================ tags, covers, lyrics
    def target_paths(self, all_rows=False, library_only=False):
        """Selected albums / videos / library rows when the library is shown, otherwise the playing track."""
        if all_rows:
            return [r["path"] for r in self.table.model_.rows]
        if self.center.currentIndex() == 0:
            if self.tiles.isVisible() and self.tiles.selectedIndexes() and (
                    self.tiles.hasFocus() or not (self.table.isVisible() and self.table.selected_paths())):
                return self._tile_selected_paths()
            if self.table.isVisible():
                sel = self.table.selected_paths()
                if sel:
                    return sel
        if library_only:
            return []
        if self.queue.hasFocus() and self.queue.selectedItems():
            return [self.player.queue[self.queue.row(it)] for it in self.queue.selectedItems()]
        cur = self.player.current()
        return [cur] if cur and not is_url(cur) else []

    def release_file(self, path, fn, new_path=None):
        """Run fn(); if Windows refuses because the file is playing, let go of it for a moment and try again."""
        try:
            fn()
            if new_path:
                self._path_renamed(path, new_path)
            return
        except PermissionError:
            if os.path.normcase(path) != os.path.normcase(self.player.current() or ""):
                raise
        pos, playing = self.player.mp.position(), self.player.is_playing()
        self.player.mp.setSource(QUrl())
        QApplication.processEvents()
        time.sleep(0.15)
        try:
            fn()
        finally:
            target = new_path or path
            if new_path:
                self._path_renamed(path, new_path)
            self.player.mp.setSource(QUrl.fromLocalFile(target))
            self.player.mp.setPosition(pos)
            if playing:
                self.player.mp.play()

    def _path_renamed(self, old, new):
        cm_library.rename_path(old, new)
        self.player.queue = [new if p == old else p for p in self.player.queue]

    def _after_tag_change(self, paths, old_keys=()):
        for k in old_keys:
            if k:
                cm_library.forget_thumb("album|" + k)
        for p in paths:
            before = cm_library.get(p) or {}
            if before.get("album_key"):
                cm_library.forget_thumb("album|" + before["album_key"])
            try:
                cm_library.refresh_file(p)
            except Exception:
                pass
            r = cm_library.get(p) or {}
            if r.get("album_key"):
                cm_library.forget_thumb("album|" + r["album_key"])
        cur = self.player.current()
        self.reload_library(keep=True)
        self.reload_sidebar()
        self._fill_queue()
        if cur in paths:
            idx = self.player.index
            pos = self.player.mp.position()
            info = cm_tags.read(cur)
            self.current_cover = cm_tags.cover(cur)
            self.current_info = dict(info, title=info.get("title") or os.path.splitext(os.path.basename(cur))[0])
            sub = " — ".join(x for x in (info.get("artist"), info.get("album")) if x)
            seed = info.get("album") or info.get("title") or ""
            self.transport.set_track(self.current_info["title"], sub, self.current_cover, seed)
            self.big_cover.set_cover(self.current_cover, seed)
            self.np_title.setText(self.current_info["title"])
            self.np_sub.setText(sub)
            self._audio_view()
            self._show_info()
            text = cm_tags.lyrics(cur)
            if text != self._lyrics_text:
                self._set_lyrics_text(text, "lrc" if os.path.isfile(cm_tags.lrc_path(cur)) else "tag")
            _ = idx, pos

    def edit_tags(self, paths=None, all_rows=False):
        paths = paths or self.target_paths(all_rows)
        paths = [p for p in paths if p and not is_url(p) and os.path.isfile(p)]
        if not paths:
            self.message(tr("msg.select_first"))
            return
        dlg = cm_dialogs.TagEditor(self, paths[:500], release_file=self.release_file)
        dlg.saved.connect(self._after_tag_change)
        dlg.exec()

    def mb_lookup(self):
        paths = self.target_paths()
        if len(paths) != 1:
            self.edit_tags(paths)
            return
        dlg = cm_dialogs.TagEditor(self, paths, release_file=self.release_file)
        dlg.saved.connect(self._after_tag_change)
        QTimer.singleShot(50, dlg.musicbrainz)
        dlg.exec()

    def tags_from_name(self):
        paths = [p for p in self.target_paths() if cm_tags.can_write(p)]
        if not paths:
            self.message(tr("msg.select_first"))
            return
        from cm_parse import title_from_filename
        if QMessageBox.question(self, APP_NAME, tr("tag.from_name_q", n=len(paths))) != QMessageBox.Yes:
            return
        for p in paths:
            vals = title_from_filename(p)
            if vals:
                self.release_file(p, lambda p=p, vals=vals: cm_tags.write(p, vals))
        self._after_tag_change(paths)

    def find_cover(self, paths=None):
        if not cm_dialogs.ask_online(self):
            return
        paths = [p for p in (paths or self.target_paths()) if not is_url(p)]
        if not paths:
            self.message(tr("msg.select_first"))
            return
        dlg = cm_dialogs.CoverPicker(self, *cm_dialogs.cover_search_fields(paths[0]))
        ok = dlg.exec()
        data = dlg.result_data
        dlg.deleteLater()
        if ok and data:
            img = QImage.fromData(data)
            if img.isNull():
                QMessageBox.warning(self, APP_NAME, tr("msg.not_image"))
                return
            self._apply_cover(paths, cm_dialogs._to_jpeg(img))

    def _apply_cover(self, paths, data):
        errors = []
        for p in paths:
            if cm_tags.can_write(p):
                try:
                    self.release_file(p, lambda p=p: cm_tags.write(p, {}, cover=data))
                except Exception as e:
                    errors.append(f"{os.path.basename(p)}: {e}")
            else:
                try:
                    with open(os.path.join(os.path.dirname(p), "cover.jpg"), "wb") as fh:
                        fh.write(data)
                except OSError as e:
                    errors.append(str(e))
        if errors:
            QMessageBox.warning(self, APP_NAME, tr("msg.save_failed") + "\n\n" + "\n".join(errors[:10]))
        self._after_tag_change(paths)
        self.message(tr("msg.cover_saved", n=len(paths) - len(errors)))

    def cover_from_file(self):
        paths = [p for p in self.target_paths() if not is_url(p)]
        if not paths:
            self.message(tr("msg.select_first"))
            return
        fn, _ = QFileDialog.getOpenFileName(self, tr("act.cover_from_file"), os.path.dirname(paths[0]),
                                            "Images (*.jpg *.jpeg *.png *.webp *.bmp)")
        if fn:
            img = QImage(fn)
            if not img.isNull():
                self._apply_cover(paths, cm_dialogs._to_jpeg(img))

    def remove_cover(self):
        paths = [p for p in self.target_paths() if cm_tags.can_write(p)]
        if paths and QMessageBox.question(self, APP_NAME, tr("tag.remove_cover_q", n=len(paths))) == QMessageBox.Yes:
            for p in paths:
                self.release_file(p, lambda p=p: cm_tags.write(p, {}, cover=b""))
            self._after_tag_change(paths)

    def export_cover(self):
        paths = self.target_paths()
        data = cm_tags.cover(paths[0]) if paths else None
        if not data:
            self.message(tr("tag.no_cover"))
            return
        ext = ".png" if data[:4] == b"\x89PNG" else ".jpg"
        fn, _ = QFileDialog.getSaveFileName(self, tr("act.export_cover"), os.path.join(os.path.dirname(paths[0]), "cover" + ext))
        if fn:
            with open(fn, "wb") as fh:
                fh.write(data)

    def find_lyrics(self, path=None):
        path = path or (self.target_paths() or [None])[0]
        if not path or is_url(path):
            self.message(tr("msg.select_first"))
            return
        info = cm_tags.read(path)
        if not info.get("title"):
            info.update(cm_dialogs.title_from_filename(path))
        dlg = cm_dialogs.LyricsDialog(self, path, info, cm_tags.lyrics(path))
        if dlg.exec() and dlg.result_text is not None:
            text = dlg.result_text
            errs = []
            if settings.get("save_lrc_file", True):
                errs += cm_tags.save_lyrics(path, text, embed=False, lrc_file=True)
            if settings.get("embed_lyrics", True) and cm_tags.can_write(path):
                try:
                    self.release_file(path, lambda: cm_tags.write(path, {}, lyrics=text))
                except Exception as e:
                    errs.append(str(e))
            if not settings.get("save_lrc_file", True) and os.path.isfile(cm_tags.lrc_path(path)):
                os.remove(cm_tags.lrc_path(path))
            if errs:
                QMessageBox.warning(self, APP_NAME, tr("msg.save_failed") + "\n\n" + "\n".join(errs))
            cm_library.update_fields(path, has_lyrics=int(bool(text)))
            if path == self.player.current():
                self._set_lyrics_text(text, "lrc" if settings.get("save_lrc_file", True) else "tag")
            self._load_tracks()

    def batch_covers(self, paths=None):
        if not cm_dialogs.ask_online(self) or self.batch_task is not None:
            return
        if not paths:
            paths = self.target_paths(library_only=True) or [r["path"] for r in cm_library.query("nocover")]
        paths = [p for p in paths if not is_video(p)]
        if not paths:
            self.message(tr("msg.nothing_to_do"))
            return
        if QMessageBox.question(self, APP_NAME, tr("batch.covers_q", n=len(paths))) != QMessageBox.Yes:
            return
        self._start_progress(tr("msg.searching"))
        busy = self.player.current()
        self.batch_task = cm_online.run(_batch_covers, paths, busy, done=self._batch_done, failed=self._batch_failed,
                                        progress=self._batch_progress)

    def batch_lyrics(self, paths=None):
        if not cm_dialogs.ask_online(self) or self.batch_task is not None:
            return
        if not paths:
            paths = self.target_paths(library_only=True) or [r["path"] for r in cm_library.query("nolyrics")]
        paths = [p for p in paths if not is_video(p)]
        if not paths:
            self.message(tr("msg.nothing_to_do"))
            return
        if QMessageBox.question(self, APP_NAME, tr("batch.lyrics_q", n=len(paths))) != QMessageBox.Yes:
            return
        self._start_progress(tr("msg.searching"))
        busy = self.player.current()
        self.batch_task = cm_online.run(_batch_lyrics, paths, busy, settings.get("embed_lyrics", True),
                                        settings.get("save_lrc_file", True), done=self._batch_done,
                                        failed=self._batch_failed, progress=self._batch_progress)

    def _batch_done(self, res):
        self._end_progress()
        done, missing, failed = res
        self.reload_library()
        self.reload_sidebar()
        msg = tr("batch.done", done=done, missing=missing)
        if failed:
            msg += "\n\n" + "\n".join(failed[:10])
        QMessageBox.information(self, APP_NAME, msg)

    def rename_files(self):
        paths = [p for p in self.target_paths() if not is_url(p)]
        if not paths:
            self.message(tr("msg.select_first"))
            return
        dlg = cm_dialogs.RenameDialog(self, paths, release_file=self.release_file)
        if dlg.exec():
            self.reload_library()
            self._fill_queue()

    # ================================================================ settings, about, misc
    def open_settings(self, page=0):
        old_lang = settings.get("language")
        dlg = cm_dialogs.SettingsDialog(self, page)
        if dlg.exec():
            if settings.get("language") != old_lang:
                self.set_lang(settings["language"])
            self.acts["theme_" + settings.get("theme", "system")].setChecked(True)
            self.apply_theme()
            for f in getattr(dlg, "removed_folders", []):
                cm_library.remove_folder(f)
            if dlg.folders_changed:
                self.rescan(quiet=True)
            self.setup_watch()
            self._library_changed()

    def show_shortcuts(self):
        d = cm_dialogs.Dialog(self, tr("set.shortcuts"), "keyboard", "teal")
        d.resize(560, 640)
        lay = QVBoxLayout(d)
        lay.addWidget(cm_dialogs.shortcuts_table(), 1)
        ok = cm_dialogs.primary(tr("btn.close"))
        ok.clicked.connect(d.accept)
        d.footer(lay, ok)
        d.exec()

    def open_doc(self, which):
        if which == "web":
            QDesktopServices.openUrl(QUrl(APP_URL))
        elif which == "freeware":
            cm_dialogs.TextDialog(self, tr("about.freeware_notice"), cm_dialogs.read_doc("FREEWARE.txt") or tr("about.freeware_text"),
                                  "heartf", "green").exec()
        else:
            cm_dialogs.TextDialog(self, tr("about.third_party"), cm_dialogs.THIRD_PARTY).exec()

    def _video_menu(self, pos):
        m = QMenu(self)
        for aid in ("play", "stop", "prev", "next"):
            m.addAction(self.acts[aid])
        m.addSeparator()
        m.addMenu(self.menus["audio_track"]).setText(tr("act.audio_track"))
        m.addMenu(self.menus["subtitles"]).setText(tr("act.subtitles"))
        m.addMenu(self.menus["aspect"]).setText(tr("act.aspect"))
        m.addMenu(self.menus["speed"]).setText(tr("act.speed"))
        m.addSeparator()
        for aid in ("snapshot", "fullscreen", "mini", "open_file"):
            m.addAction(self.acts[aid])
        m.exec(self.video.mapToGlobal(pos))

    def message(self, text, ms=4000):
        if self.batch_task is not None:
            return
        self.st_msg.setText(text)
        QTimer.singleShot(ms, lambda t=text: self.st_msg.text() == t and self.st_msg.setText(""))

    def receive_paths(self, paths):
        """Files sent from a second start of the program (double-click in Explorer)."""
        if paths:
            self.open_paths(paths)
        self.showNormal() if self.isMinimized() else None
        self.raise_()
        self.activateWindow()

    def _save_state(self):
        if self._mini_geometry is None and not self.isFullScreen():
            settings["geometry"] = bytes(self.saveGeometry().toBase64()).decode()
        self._save_queue()
        settings.save()

    def showEvent(self, e):
        super().showEvent(e)
        cm_theme.set_windows_dark_titlebar(self)

    def closeEvent(self, e):
        if self._mini_geometry is not None:
            self.toggle_mini()
        if self.isFullScreen():
            self.toggle_fullscreen()
        if self.batch_task is not None:
            self.batch_task.cancelled = True
        self.thumbnailer.clear()
        self.periodic_timer.stop()
        self.player.stop()
        self._save_state()
        super().closeEvent(e)


def _esc(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _make_thumbs(items, progress=None, task=None):
    """Worker: album cover thumbnails into the disk cache."""
    for i, (album, sample, tp) in enumerate(items):
        if task is not None and task.cancelled:
            break
        try:
            data = cm_tags.cover(sample)
            if data:
                img = QImage.fromData(data)
                if not img.isNull():
                    img = img.scaled(248, 248, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                    x, y = (img.width() - 248) // 2, (img.height() - 248) // 2
                    img.copy(x, y, 248, 248).save(tp, "JPG", 88)
                    if progress:
                        progress(i + 1, len(items), album)
        except Exception:
            continue
    return True


def _batch_covers(paths, busy, progress=None, task=None):
    """Worker: one cover per album, written into every file of that album (or cover.jpg when the file can't be tagged)."""
    albums = {}
    for p in paths:
        i = cm_tags.read(p)
        key = (i.get("albumartist") or i.get("artist") or "", i.get("album") or "",
               cm_library.album_key(i.get("album"), i.get("albumartist"), os.path.dirname(p)) or p)
        albums.setdefault(key, []).append((p, i))
    done = missing = 0
    failed = []
    for n, ((artist, album, akey), items) in enumerate(albums.items()):
        if task is not None and task.cancelled:
            break
        if progress:
            progress(n, len(albums), album or items[0][1].get("title", ""))
        try:
            data = cm_online.cover_best(artist, album, items[0][1].get("title", "") if not album else "")
        except cm_online.OnlineError as e:
            failed.append(str(e))
            data = None
        if not data:
            missing += len(items)
            continue
        img = QImage.fromData(data)
        if not img.isNull() and max(img.width(), img.height()) > 1400:
            data = cm_dialogs._to_jpeg(img)
        for p, _i in items:
            try:
                if p == busy or not cm_tags.can_write(p):
                    with open(os.path.join(os.path.dirname(p), "cover.jpg"), "wb") as fh:
                        fh.write(data)
                else:
                    cm_tags.write(p, {}, cover=data)
                cm_library.update_fields(p, has_cover=1)
                done += 1
            except Exception as e:
                failed.append(f"{os.path.basename(p)}: {e}")
        cm_library.forget_thumb("album|" + akey)
    return done, missing, failed


def _batch_lyrics(paths, busy, embed, lrc_file, progress=None, task=None):
    done = missing = 0
    failed = []
    for n, p in enumerate(paths):
        if task is not None and task.cancelled:
            break
        i = cm_tags.read(p)
        if progress:
            progress(n, len(paths), i.get("title") or os.path.basename(p))
        if not i.get("title"):
            missing += 1
            continue
        try:
            res = cm_online.lyrics_best(i.get("artist", ""), i["title"], i.get("album", ""), i.get("duration", 0))
        except cm_online.OnlineError as e:
            failed.append(f"{os.path.basename(p)}: {e}")
            continue
        text = (res or {}).get("synced") or (res or {}).get("plain") or ""
        if not text:
            missing += 1
            continue
        errs = cm_tags.save_lyrics(p, text, embed=embed and p != busy, lrc_file=lrc_file or p == busy)
        if errs:
            failed.append(f"{os.path.basename(p)}: {errs[0]}")
        else:
            cm_library.update_fields(p, has_lyrics=1)
            done += 1
    return done, missing, failed


def _watch_dirs(roots):
    """Only the library folders themselves are watched: on Windows a watched folder can't be renamed or deleted in
    Explorer, so album folders are left free. Changes deeper down are found by the quiet background check
    (every 10 minutes and when the window becomes active again)."""
    return [os.path.normpath(r) for r in roots if os.path.isdir(r)]


def _video_placeholder(seed):
    """16:9 tile for a video whose thumbnail is not made yet."""
    w, h = 320, 180
    pm = QPixmap(w, h)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    g = QLinearGradient(0, 0, w, h)
    tones = [("#1e293b", "#334155"), ("#1e1b4b", "#3730a3"), ("#0f172a", "#155e75"), ("#3b0764", "#6b21a8"),
             ("#14532d", "#166534"), ("#431407", "#9a3412")]
    a, b = tones[sum(map(ord, seed or "x")) % len(tones)]
    g.setColorAt(0, QColor(a))
    g.setColorAt(1, QColor(b))
    p.setBrush(g)
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(QRectF(0, 0, w, h), 10, 10)
    icon = cm_icons.render_svg(cm_icons.flat_svg("video", "#ffffff"), 56, 1.0)
    p.setOpacity(0.55)
    p.drawPixmap(int((w - 56) / 2), int((h - 56) / 2), icon)
    p.end()
    return pm
