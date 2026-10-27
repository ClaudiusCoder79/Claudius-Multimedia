"""Claudius Multimedia - music & video player for Windows 11 (x64).
Created by Michal Czapla & Claude AI. Freeware - see FREEWARE.txt and LICENSE.

Start:  python claudius_multimedia.py [files or folders to play]
"""
import os
import sys

from cm_core import (APP_NAME, APP_VERSION, APP_AUTHORS, data_dir, resource_dir, set_language, settings,
                     system_language, tr)

_log_file = None


def _setup_log():
    """Errors go to %APPDATA%\\Claudius Multimedia\\claudius.log (the built program has no console window).
    A Python error inside the program is written there and the program keeps running; if the program ever
    crashes outright, faulthandler writes where it happened."""
    global _log_file
    import faulthandler
    import time
    import traceback
    path = os.path.join(data_dir(), "claudius.log")
    try:
        if os.path.isfile(path) and os.path.getsize(path) > 1024 * 1024:
            os.replace(path, path + ".old")
        _log_file = open(path, "a", encoding="utf-8", buffering=1)
    except OSError:
        return
    _log_file.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')}  {APP_NAME} {APP_VERSION}  {sys.platform} =====\n")
    if sys.stderr is None or getattr(sys, "frozen", False):
        sys.stderr = _log_file
        sys.stdout = _log_file
    try:
        faulthandler.enable(_log_file, all_threads=True)
    except Exception:
        pass

    def hook(exc_type, exc, tb):
        traceback.print_exception(exc_type, exc, tb, file=_log_file)
    sys.excepthook = hook
    threading_hook = getattr(__import__("threading"), "excepthook", None)
    if threading_hook is not None:
        import threading
        threading.excepthook = lambda a: traceback.print_exception(a.exc_type, a.exc_value, a.exc_traceback,
                                                                   file=_log_file)

SERVER_NAME = "ClaudiusMultimedia-" + (os.environ.get("USERNAME") or os.environ.get("USER") or "user")


def _close_pyinstaller_splash():
    try:
        import pyi_splash  # only exists inside the built EXE (PyInstaller --splash)
        pyi_splash.close()
    except Exception:
        pass


def _send_to_running_instance(paths):
    """If Claudius Multimedia is already open, hand it the files and return True."""
    from PySide6.QtNetwork import QLocalSocket
    sock = QLocalSocket()
    sock.connectToServer(SERVER_NAME)
    if not sock.waitForConnected(400):
        return False
    payload = "\n".join(os.path.abspath(p) if "://" not in p[:12] else p for p in paths) or "\n"
    sock.write(payload.encode("utf-8"))
    sock.flush()
    sock.waitForBytesWritten(1500)
    sock.disconnectFromServer()
    return True


def _listen(window):
    from PySide6.QtNetwork import QLocalServer
    QLocalServer.removeServer(SERVER_NAME)
    server = QLocalServer(window)
    if not server.listen(SERVER_NAME):
        return None

    def incoming():
        conn = server.nextPendingConnection()
        if conn is None:
            return

        def read():
            data = bytes(conn.readAll()).decode("utf-8", "replace")
            conn.buffer_ = getattr(conn, "buffer_", "") + data

        def done():
            paths = [p for p in getattr(conn, "buffer_", "").split("\n") if p.strip()]
            window.receive_paths(paths)
            conn.deleteLater()
        conn.readyRead.connect(read)
        conn.disconnected.connect(done)
    server.newConnection.connect(incoming)
    return server


class Splash:
    """Start-up window: splash.png with the version, a status line and a progress bar painted on top."""
    def __init__(self, app):
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QPixmap
        from PySide6.QtWidgets import QSplashScreen
        import cm_icons
        pm = QPixmap(os.path.join(resource_dir(), "splash.png"))
        if pm.isNull():
            pm = cm_icons.logo_pixmap(256)
        self.base = pm
        self.widget = QSplashScreen(self._compose("", 0))
        self.widget.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.widget.show()
        app.processEvents()
        self.app = app

    def _compose(self, text, pct):
        from PySide6.QtCore import QRectF, Qt
        from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter
        pm = self.base.copy()
        ratio = pm.devicePixelRatio() or 1
        w, h = pm.width() / ratio, pm.height() / ratio
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        f = QFont("Segoe UI")
        f.setPixelSize(12)
        p.setFont(f)
        p.setPen(QColor(255, 255, 255, 220))
        left, right, bar_y = 44, w - 44, h - 74
        p.drawText(QRectF(left, bar_y - 24, right - left, 18), Qt.AlignLeft | Qt.AlignVCenter, text)
        p.drawText(QRectF(left, bar_y - 24, right - left, 18), Qt.AlignRight | Qt.AlignVCenter, f"{pct}%")
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 64))
        p.drawRoundedRect(QRectF(left, bar_y, right - left, 5), 2.5, 2.5)
        g = QLinearGradient(left, 0, right, 0)
        g.setColorAt(0, QColor("#ffc24a"))
        g.setColorAt(1, QColor("#ffffff"))
        p.setBrush(g)
        p.drawRoundedRect(QRectF(left, bar_y, (right - left) * pct / 100, 5), 2.5, 2.5)
        p.setPen(QColor(255, 255, 255, 190))
        p.drawText(QRectF(left, h - 40, right - left, 18), Qt.AlignLeft | Qt.AlignVCenter,
                   tr("splash.version", version=APP_VERSION))
        p.drawText(QRectF(left, h - 40, right - left, 18), Qt.AlignRight | Qt.AlignVCenter, tr("splash.created_by", authors=APP_AUTHORS))
        p.end()
        return pm

    def step(self, text, pct):
        self.widget.setPixmap(self._compose(text, pct))
        self.app.processEvents()

    def finish(self, window):
        self.widget.finish(window)


def _selftest(app, window, report):
    """Used by the GitHub build: start, play a short generated tone, write a report and quit."""
    import math
    import struct
    import tempfile
    import wave
    from PySide6.QtCore import QTimer
    tone = os.path.join(tempfile.gettempdir(), "claudius_selftest.wav")
    with wave.open(tone, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(44100)
        w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(i / 20))) for i in range(44100 * 2)))
    window.player.set_queue([tone], 0, True)

    def finish():
        mp = window.player.mp
        lines = ["START OK", f"version={APP_VERSION}", f"duration_ms={mp.duration()}", f"status={mp.mediaStatus()}",
                 f"error={mp.errorString()}", "PLAYBACK OK" if mp.duration() > 0 else "PLAYBACK FAIL"]
        with open(report, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        window.player.clear()
        settings["queue"] = []
        app.exit(0)
    QTimer.singleShot(5000, finish)


def main():
    _setup_log()
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MichalCzapla.ClaudiusMultimedia")
        except Exception:
            pass
    os.environ.setdefault("QT_MEDIA_BACKEND", "ffmpeg")
    from PySide6.QtWidgets import QApplication
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("Michal Czapla")
    if not any(a.startswith("--selftest") for a in sys.argv) and _send_to_running_instance(args):
        _close_pyinstaller_splash()
        return 0

    # --lang=xx comes from the installer (language chosen in setup) and is used until the user picks another one
    lang_arg = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--lang=")), "")
    if not settings.get("language"):
        settings["language"] = lang_arg or system_language()
    set_language(settings["language"])

    import cm_icons
    import cm_theme
    app.setWindowIcon(cm_icons.logo_icon())
    cm_theme.apply(app)
    _close_pyinstaller_splash()
    splash = Splash(app)
    splash.step(tr("splash.settings"), 15)
    splash.step(tr("splash.engine"), 40)
    from cm_main import MainWindow
    splash.step(tr("splash.library"), 70)
    window = MainWindow()
    splash.step(tr("splash.ready"), 100)
    server = _listen(window)
    window.show()
    splash.finish(window)
    window._server = server
    if args:
        window.open_paths(args)
    selftest = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--selftest=")), None)
    if selftest:
        _selftest(app, window, selftest)
    elif settings.get("scan_on_start", True) and settings.get("library_folders"):
        from PySide6.QtCore import QTimer
        QTimer.singleShot(1500, lambda: window.rescan(quiet=True))
    code = app.exec()
    settings.save()
    return code


if __name__ == "__main__":
    sys.exit(main())
