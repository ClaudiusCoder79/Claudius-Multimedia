"""Claudius Multimedia - main window."""
import os
import sys
import time

from PySide6.QtCore import QByteArray, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QActionGroup, QColor, QDesktopServices, QIcon, QImage, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QFileDialog, QHBoxLayout, QInputDialog, QLabel,
                               QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox, QProgressBar, QPushButton,
                               QSplitter, QStackedWidget, QTabWidget, QVBoxLayout, QWidget)
from PySide6.QtGui import QStandardItem, QStandardItemModel

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
from cm_player import Player
from cm_widgets import bind, muted

TABS = ["file", "home", "playback", "library", "tags", "lyrics", "playlist", "view", "about"]

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
                ("browse", ["browse_artists", "browse_albums", "browse_genres", "browse_tracks"]),
                ("tags", ["edit_tags", "find_cover", "find_lyrics"]),
                ("batch", ["batch_covers", "batch_lyrics"]),
                ("playlists", ["new_playlist", "add_to_playlist"])],
    "tags": [("edit", ["edit_tags", "mb_lookup", "tags_from_name"]),
             ("artwork", ["find_cover", "cover_from_file", "remove_cover", "export_cover"]),
             ("batch", ["batch_covers", "rename_files"])],
    "lyrics": [("lyrics", ["find_lyrics", "edit_lyrics", "load_lrc", "batch_lyrics"]),
               ("display", ["lyrics_smaller", "lyrics_bigger", "lyrics_earlier", "lyrics_later"])],
    "playlist": [("queue", ["queue_add_files", "queue_add_folder", "queue_remove", "clear_queue"]),
                 ("order", ["queue_shuffle", "queue_sort"]),
                 ("file", ["load_playlist", "save_playlist"]),
                 ("playlists", ["new_playlist", "add_to_playlist"])],
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
        self.browse = "albums"
        self.browse_value = None
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
                           ("browse_tracks", "list")):
            mk(aid, glyph, "green", lambda _=False, m=aid.split("_")[1]: self.set_browse(m), None, True)
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
        for k in ("browse_artists", "browse_albums", "browse_genres", "browse_tracks"):
            g2.addAction(A[k])
        A["browse_albums"].setChecked(True)
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
        self.queue = QListWidget()
        self.queue.setObjectName("Queue")
        self.queue.setDragDropMode(QAbstractItemView.InternalMove)
        self.queue.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.queue.setIconSize(QSize(36, 36))
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
        self.album_model = QStandardItemModel(self)
        self.albums = cm_widgets.AlbumStrip()
        self.albums.setModel(self.album_model)
        self.albums.clicked.connect(self._album_clicked)
        self.albums.doubleClicked.connect(lambda idx: (self._album_clicked(idx), self.play_rows(0)))
        v.addWidget(self.albums)
        h = QHBoxLayout()
        h.setSpacing(0)
        self.group_list = QListWidget()
        self.group_list.setObjectName("SideList")
        self.group_list.setFixedWidth(230)
        self.group_list.itemClicked.connect(self._group_clicked)
        self.group_list.hide()
        h.addWidget(self.group_list)
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
        self.b_tags_all = QPushButton()
        bind(self.b_tags_all, "act.edit_tags")
        self.b_tags_all.clicked.connect(lambda: self.edit_tags(all_rows=True))
        for b in (self.b_play_all, self.b_shuffle_all, self.b_tags_all):
            ah.addWidget(b)
        inner.addWidget(self.album_head)
        self.table = cm_widgets.TrackTable()
        self.table.doubleClicked.connect(lambda idx: self.play_rows(idx.row()))
        self.table.customContextMenuRequested.connect(self._table_menu)
        inner.addWidget(self.table, 1)
        self.empty = QLabel()
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setObjectName("Muted")
        self.empty.setWordWrap(True)
        self.empty.hide()
        inner.addWidget(self.empty, 1)
        h.addLayout(inner, 1)
        v.addLayout(h, 1)
        return page

    def _retranslate_local(self):
        for i, key in enumerate(("panel.lyrics", "panel.info", "panel.queue")):
            self.rtabs.setTabText(i, tr(key))
        self.table.model_.headerDataChanged.emit(Qt.Horizontal, 0, len(self.table.model_.COLS) - 1)
        self.empty.setText(tr("lib.empty"))

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
        self.table.viewport().update()

    def _refresh_icons(self):
        self.transport.refresh_icons()

    def set_lang(self, code):
        settings["language"] = code
        set_language(code)
        cm_widgets.retranslate_all()
        self._retranslate_local()
        self.about.build()
        self.reload_sidebar()
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
    def reload_sidebar(self):
        self.sidelist.clear()
        counts = cm_library.counts()
        sel = self.view
        L = self.sidelist
        L.heading("side.library")
        items = [("music", "lyrics", "blue"), ("videos", "video", "purple"), ("favourites", "heartf", "red")]
        for key, glyph, colour in items:
            it = L.entry(tr("side." + key), cm_icons.glossy(glyph, colour, 22), ("view", key), counts.get(key))
            if sel == (key, None):
                it.setSelected(True)
        L.heading("side.smart")
        for key, glyph in (("recent", "clock"), ("most", "star"), ("nocover", "image"), ("nolyrics", "lyrics")):
            it = L.entry(tr("side." + key), cm_icons.flat(glyph, cm_theme.colours()["muted"], 20), ("view", key), counts.get(key))
            if sel == (key, None):
                it.setSelected(True)
        L.heading("side.playlists")
        for pid, name, n in cm_library.playlists():
            it = L.entry(name, cm_icons.flat("playlist", cm_theme.colours()["muted"], 20), ("playlist", pid), n)
            if sel == ("playlist", pid):
                it.setSelected(True)
        L.entry(tr("act.new_playlist"), cm_icons.flat("add", cm_theme.colours()["accent"], 20), ("newpl", None))

    def _side_clicked(self, it):
        data = it.data(Qt.UserRole)
        if not data:
            return
        kind, value = data
        if kind == "newpl":
            self.new_playlist()
            return
        self.view = (value, None) if kind == "view" else ("playlist", value)
        self.browse_value = None
        self.show_page(0)
        self.reload_library()

    def _side_menu(self, pos):
        it = self.sidelist.itemAt(pos)
        data = it.data(Qt.UserRole) if it else None
        if not data or data[0] != "playlist":
            return
        pid = data[1]
        m = QMenu(self)
        m.addAction(tr("act.play"), lambda: self.player.set_queue([r["path"] for r in cm_library.query(playlist=pid)]))
        m.addAction(tr("pl.rename"), lambda: self._rename_pl(pid))
        m.addAction(tr("pl.export"), lambda: self._export_pl(pid))
        m.addSeparator()
        m.addAction(tr("pl.delete"), lambda: self._delete_pl(pid))
        m.exec(self.sidelist.mapToGlobal(pos))

    def _rename_pl(self, pid):
        old = next((n for i, n, _ in cm_library.playlists() if i == pid), "")
        name, ok = QInputDialog.getText(self, tr("pl.rename"), tr("pl.name"), text=old)
        if ok and name.strip():
            cm_library.rename_playlist(pid, name.strip())
            self.reload_sidebar()

    def _export_pl(self, pid):
        rows = cm_library.query(playlist=pid)
        name = next((n for i, n, _ in cm_library.playlists() if i == pid), "playlist")
        fn, _ = QFileDialog.getSaveFileName(self, tr("pl.export"), name + ".m3u8", "M3U8 (*.m3u8)")
        if fn:
            write_m3u(fn, [(r["path"], f'{r["artist"]} - {r["title"]}', r["duration"]) for r in rows])

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
            self.reload_sidebar()

    def set_browse(self, mode):
        self.browse = mode
        self.browse_value = None
        self.acts["browse_" + mode].setChecked(True)
        self.show_page(0)
        self.reload_library()

    def _album_clicked(self, idx):
        album = idx.data(Qt.UserRole)
        self.browse_value = None if self.browse_value == album else album
        if self.browse_value is None:
            self.albums.clearSelection()
        self._load_tracks()

    def _group_clicked(self, it):
        self.browse_value = it.data(Qt.UserRole)
        self._load_tracks()

    def reload_library(self):
        view, _ = self.view
        is_pl = view == "playlist"
        show_albums = self.browse == "albums" and not is_pl and view in ("music", "favourites", "nocover", "nolyrics", "recent")
        self.albums.setVisible(show_albums)
        self.group_list.setVisible(self.browse in ("artists", "genres") and not is_pl and view != "videos")
        if show_albums:
            self._load_albums(view)
        elif self.group_list.isVisible():
            self.group_list.clear()
            all_it = QListWidgetItem(tr("browse.all"))
            all_it.setData(Qt.UserRole, None)
            self.group_list.addItem(all_it)
            for name, n in cm_library.groups(self.browse, view if view in cm_library.WHERE else "music"):
                it = QListWidgetItem(f"{name}  ({n})")
                it.setData(Qt.UserRole, name)
                self.group_list.addItem(it)
        self._load_tracks()

    def _load_albums(self, view):
        self.album_model.clear()
        albums = cm_library.groups("albums", view)
        ph_cache = {}
        self._album_items = {}
        for album, who, n, sample in albums:
            it = QStandardItem(f"{album}\n{who}")
            it.setData(album, Qt.UserRole)
            it.setToolTip(f"{album}\n{who} · {n}")
            tp = cm_library.thumb_path(album + "|" + who)
            if os.path.isfile(tp):
                it.setIcon(QIcon(QPixmap(tp)))
            else:
                key = sum(map(ord, album)) % 6
                if key not in ph_cache:
                    ph_cache[key] = QIcon(cm_icons.placeholder_cover(124, album))
                it.setIcon(ph_cache[key])
                self._album_items[album] = (it, sample, tp)
            self.album_model.appendRow(it)
        if self._album_items:
            todo = [(a, s, tp) for a, (it, s, tp) in self._album_items.items()]
            cm_online.run(_make_thumbs, todo, progress=self._thumb_ready)

    def _thumb_ready(self, _i, _n, album):
        entry = getattr(self, "_album_items", {}).get(album)
        if entry and os.path.isfile(entry[2]):
            try:
                entry[0].setIcon(QIcon(QPixmap(entry[2])))
            except RuntimeError:
                pass

    def _load_tracks(self):
        view, _ = self.view
        kw = {"search": self.header.search.text().strip()}
        if view == "playlist":
            kw["playlist"] = self.view[1]
        else:
            kw["view"] = view
        if self.browse_value is not None:
            if self.browse == "albums":
                kw["album"] = self.browse_value
            elif self.browse == "artists":
                kw["artist"] = self.browse_value
            elif self.browse == "genres":
                kw["genre"] = self.browse_value
        rows = cm_library.query(**kw)
        self.table.model_.set_rows(rows)
        self.table.model_.set_playing(self.player.current())
        has = bool(rows)
        self.table.setVisible(has)
        self.empty.setVisible(not has)
        if not has:
            self.empty.setText(tr("lib.empty") if not settings.get("library_folders") else tr("lib.nothing"))
        # header line above the table
        if self.browse == "albums" and self.browse_value and rows:
            r0 = rows[0]
            total = sum(r.get("duration") or 0 for r in rows)
            self.head_title.setText(self.browse_value)
            who = r0.get("albumartist") or r0.get("artist") or ""
            bits = [who, r0.get("year") or "", r0.get("genre") or "", tr("lib.n_tracks", n=len(rows)), fmt_time(total)]
            self.head_sub.setText(" · ".join(b for b in bits if b))
            self.head_cover.set_cover(cm_tags.cover(r0["path"]), self.browse_value)
        else:
            title = self.browse_value or (next((n for i, n, _ in cm_library.playlists() if i == self.view[1]), "")
                                          if view == "playlist" else tr("side." + view))
            self.head_title.setText(title)
            total = sum(r.get("duration") or 0 for r in rows)
            self.head_sub.setText(" · ".join(x for x in (tr("lib.n_tracks", n=len(rows)), fmt_time(total) if total else "") if x))
            self.head_cover.set_cover(None, title)
        self.album_head.setVisible(True)

    def play_rows(self, start, shuffle=False):
        rows = self.table.model_.rows
        if not rows:
            return
        paths = [r["path"] for r in rows]
        if shuffle:
            self.player.set_shuffle(True)
            import random
            start = random.randrange(len(paths))
        self.player.set_queue(paths, start, True)
        if is_video(paths[start]):
            self.center.setCurrentIndex(1)

    def _table_menu(self, pos):
        rows = self.table.selected_rows()
        if not rows:
            return
        paths = [r["path"] for r in rows]
        m = QMenu(self)
        m.addAction(cm_icons.glossy("play", "green", 20), tr("act.play"), lambda: self.player.set_queue(paths))
        m.addAction(tr("menu.play_next"), lambda: self.player.insert_next(paths))
        m.addAction(tr("menu.add_queue"), lambda: self.player.add(paths))
        sub = m.addMenu(tr("act.add_to_playlist"))
        self._fill_playlist_menu(sub, paths)
        if self.view[0] == "playlist":
            pid = self.view[1]
            m.addAction(tr("menu.remove_from_pl"), lambda: (cm_library.remove_from_playlist(pid, paths),
                                                           self.reload_library(), self.reload_sidebar()))
        m.addSeparator()
        m.addAction(cm_icons.glossy("tag", "orange", 20), tr("act.edit_tags"), lambda: self.edit_tags(paths=paths))
        m.addAction(cm_icons.glossy("image", "pink", 20), tr("act.find_cover"), lambda: self.find_cover(paths=paths))
        m.addAction(cm_icons.glossy("lyrics", "pink", 20), tr("act.find_lyrics"), lambda: self.find_lyrics(path=paths[0]))
        rate = m.addMenu(tr("menu.rating"))
        for n in range(6):
            rate.addAction("★" * n + "☆" * (5 - n) if n else tr("menu.no_rating"),
                           lambda n=n: self._set_rating(paths, n))
        fav = all(r.get("favourite") for r in rows)
        m.addAction(tr("menu.unfavourite") if fav else tr("menu.favourite"), lambda: self._set_fav(paths, not fav))
        m.addSeparator()
        m.addAction(tr("menu.show_folder"), lambda: self.show_in_folder(paths[0]))
        m.exec(self.table.viewport().mapToGlobal(pos))

    def _set_rating(self, paths, n):
        for p in paths:
            cm_library.update_fields(p, rating=n)
        self._load_tracks()

    def _set_fav(self, paths, on):
        for p in paths:
            cm_library.update_fields(p, favourite=int(on))
        self._load_tracks()
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

    def show_in_folder(self, path):
        if sys.platform == "win32":
            import subprocess
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(path)))

    def add_library_folder(self):
        d = QFileDialog.getExistingDirectory(self, tr("act.add_folder"))
        if d:
            d = os.path.normpath(d)
            folders = settings.get("library_folders", [])
            if d not in folders:
                settings["library_folders"] = folders + [d]
                settings.save()
            self.rescan()

    def rescan(self, quiet=False):
        folders = [f for f in settings.get("library_folders", []) if os.path.isdir(f)]
        if not folders:
            if not quiet:
                self.add_library_folder()
            return
        if self.batch_task is not None:
            return
        self._start_progress(tr("msg.scanning"))
        self.batch_task = cm_online.run(cm_library.scan, folders, done=self._scan_done, failed=self._batch_failed,
                                        progress=self._batch_progress)

    def _scan_done(self, res):
        self._end_progress()
        self.message(tr("msg.scan_done", added=res.get("added", 0), removed=res.get("removed", 0)), 6000)
        self.reload_sidebar()
        self.reload_library()
        self._update_stats()

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

    # ================================================================ tags, covers, lyrics
    def target_paths(self, all_rows=False):
        """Selected library rows when the library is shown, otherwise the playing track."""
        if all_rows:
            return [r["path"] for r in self.table.model_.rows]
        if self.center.currentIndex() == 0 and self.table.isVisible():
            sel = self.table.selected_paths()
            if sel:
                return sel
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

    def _after_tag_change(self, paths):
        for p in paths:
            try:
                cm_library.refresh_file(p)
            except Exception:
                pass
            r = cm_library.get(p) or {}
            cm_library.forget_thumb((r.get("album") or "") + "|" + (r.get("albumartist") or r.get("artist") or ""))
        cur = self.player.current()
        self.reload_library()
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
        info = cm_tags.read(paths[0])
        dlg = cm_dialogs.CoverPicker(self, info.get("albumartist") or info.get("artist", ""), info.get("album", ""),
                                     info.get("title", ""))
        if dlg.exec() and dlg.result_data:
            img = QImage.fromData(dlg.result_data)
            data = cm_dialogs._to_jpeg(img) if not img.isNull() else dlg.result_data
            self._apply_cover(paths, data)

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

    def batch_covers(self):
        if not cm_dialogs.ask_online(self) or self.batch_task is not None:
            return
        paths = self.target_paths() if self.center.currentIndex() == 0 and self.table.selected_paths() else \
            [r["path"] for r in cm_library.query("nocover")]
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

    def batch_lyrics(self):
        if not cm_dialogs.ask_online(self) or self.batch_task is not None:
            return
        paths = self.target_paths() if self.center.currentIndex() == 0 and self.table.selected_paths() else \
            [r["path"] for r in cm_library.query("nolyrics")]
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
            self.reload_library()
            self._update_stats()

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
        self._save_state()
        self.player.stop()
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
        key = (i.get("albumartist") or i.get("artist") or "", i.get("album") or "")
        albums.setdefault(key, []).append((p, i))
    done = missing = 0
    failed = []
    for n, ((artist, album), items) in enumerate(albums.items()):
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
        cm_library.forget_thumb(album + "|" + artist)
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
