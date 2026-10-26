"""Claudius Multimedia - playback engine (Qt Multimedia with its built-in FFmpeg backend), the play queue,
resume positions and the background video thumbnail maker."""
import os
import random

from PySide6.QtCore import QObject, QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QImage
from PySide6.QtMultimedia import QAudioOutput, QMediaMetaData, QMediaPlayer, QVideoSink

from cm_core import is_url, settings


class Player(QObject):
    trackChanged = Signal(int)          # index in the queue (-1 = nothing)
    queueChanged = Signal()
    stateChanged = Signal(bool)         # playing?
    positionChanged = Signal(int)       # ms
    durationChanged = Signal(int)       # ms
    error = Signal(str)
    modeChanged = Signal()
    finished = Signal(str, int)         # path, duration ms (counted as played)
    tracksChanged = Signal()            # audio / subtitle tracks became known
    leaving = Signal(str, int, int)     # path, position ms, duration ms - before another track starts / stop
    resumed = Signal(int)               # playback continued at a remembered position (ms)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mp = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.mp.setAudioOutput(self.audio)
        self.queue = []
        self.index = -1
        self.shuffle = bool(settings.get("shuffle"))
        self.repeat = settings.get("repeat", "off")
        self._order = []
        self._counted = False
        self._pending_seek = 0
        self._seen_loading = False
        self._src_path = None
        self.resume_lookup = None       # callable(path) -> ms to continue at (0 = from the start)
        self.set_volume(settings.get("volume", 72))
        self.audio.setMuted(bool(settings.get("muted")))
        self.mp.setPlaybackRate(float(settings.get("rate", 1.0)))
        self.mp.positionChanged.connect(self._on_position)
        self.mp.durationChanged.connect(lambda d: self.durationChanged.emit(int(d)))
        self.mp.playbackStateChanged.connect(lambda s: self.stateChanged.emit(s == QMediaPlayer.PlayingState))
        self.mp.mediaStatusChanged.connect(self._on_status)
        self.mp.errorOccurred.connect(self._on_error)
        self.mp.tracksChanged.connect(self.tracksChanged)

    # ------------------------------------------------ queue
    def current(self):
        return self.queue[self.index] if 0 <= self.index < len(self.queue) else None

    def set_queue(self, paths, start=0, play=True):
        self.queue = list(paths)
        self._rebuild_order(start)
        self.queueChanged.emit()
        if self.queue:
            self.play_index(max(0, min(start, len(self.queue) - 1)), play)
        else:
            self.stop()
            self.index = -1
            self.trackChanged.emit(-1)

    def add(self, paths, play_now=False):
        first = len(self.queue)
        self.queue.extend(paths)
        self._rebuild_order(self.index if self.index >= 0 else first)
        self.queueChanged.emit()
        if play_now or self.index < 0:
            self.play_index(first, True)

    def insert_next(self, paths):
        pos = self.index + 1 if self.index >= 0 else len(self.queue)
        self.queue[pos:pos] = list(paths)
        self._rebuild_order(self.index)
        self.queueChanged.emit()

    def remove_rows(self, rows):
        rows = sorted(set(r for r in rows if 0 <= r < len(self.queue)), reverse=True)
        playing_removed = self.index in rows
        for r in rows:
            del self.queue[r]
            if r < self.index:
                self.index -= 1
        if playing_removed:
            self.stop()
            self.index = min(self.index, len(self.queue) - 1)
            if self.queue:
                self.play_index(max(0, self.index), False)
            else:
                self.index = -1
                self.trackChanged.emit(-1)
        self._rebuild_order(self.index)
        self.queueChanged.emit()

    def move(self, src, dst):
        if not (0 <= src < len(self.queue)) or not (0 <= dst < len(self.queue)) or src == dst:
            return
        item = self.queue.pop(src)
        self.queue.insert(dst, item)
        if self.index == src:
            self.index = dst
        elif src < self.index <= dst:
            self.index -= 1
        elif dst <= self.index < src:
            self.index += 1
        self._rebuild_order(self.index)
        self.queueChanged.emit()

    def clear(self):
        self.set_queue([], play=False)

    def shuffle_queue(self):
        cur = self.current()
        rest = [p for i, p in enumerate(self.queue) if i != self.index]
        random.shuffle(rest)
        self.queue = ([cur] if cur else []) + rest
        self.index = 0 if cur else -1
        self._rebuild_order(self.index)
        self.queueChanged.emit()
        self.trackChanged.emit(self.index)

    def sort_queue(self, key):
        cur = self.current()
        self.queue.sort(key=key)
        self.index = self.queue.index(cur) if cur in self.queue else -1
        self._rebuild_order(self.index)
        self.queueChanged.emit()
        self.trackChanged.emit(self.index)

    def _rebuild_order(self, start):
        n = len(self.queue)
        if self.shuffle and n:
            rest = [i for i in range(n) if i != start]
            random.shuffle(rest)
            self._order = ([start] if 0 <= start < n else []) + rest
        else:
            self._order = list(range(n))

    # ------------------------------------------------ transport
    def _leave(self, at_end=False):
        """Tell the window how far the open file got (resume position, listening time) - once per opening."""
        src, self._src_path = self._src_path, None
        if src:
            dur = int(self.mp.duration())
            self.leaving.emit(src, dur if at_end else int(self.mp.position()), dur)

    def play_index(self, i, play=True):
        if not (0 <= i < len(self.queue)):
            return
        self._leave()
        self.index = i
        self._counted = False
        src = self.queue[i]
        self._pending_seek = 0
        self._seen_loading = False
        if self.resume_lookup is not None and "://" not in src[:12]:
            try:
                self._pending_seek = int(self.resume_lookup(src) or 0)
            except Exception:
                self._pending_seek = 0
        self.mp.setSource(QUrl(src) if is_url(src) else QUrl.fromLocalFile(os.path.abspath(src)))
        self._src_path = src
        if play:
            self.mp.play()
        self.trackChanged.emit(i)

    def toggle(self):
        if self.index < 0 and self.queue:
            self.play_index(0)
        elif self.mp.playbackState() == QMediaPlayer.PlayingState:
            self.mp.pause()
        else:
            self.play()

    def play(self):
        if self.index < 0 and self.queue:
            self.play_index(0)
        elif self.current() and not self.mp.source().isValid():
            self.play_index(self.index)
        else:
            if self._src_path is None:
                self._src_path = self.current()
            self.mp.play()

    def pause(self):
        self.mp.pause()

    def stop(self):
        self._leave()
        self.mp.stop()

    def release(self):
        """Let go of the playing file (so it can be deleted / renamed)."""
        self._leave()
        self.mp.stop()
        self.mp.setSource(QUrl())

    def insert(self, paths, pos):
        pos = max(0, min(pos, len(self.queue)))
        self.queue[pos:pos] = list(paths)
        if 0 <= self.index and pos <= self.index:
            self.index += len(paths)
        self._rebuild_order(self.index if self.index >= 0 else 0)
        self.queueChanged.emit()
        if self.index < 0 and self.queue:
            self.play_index(pos, True)

    def is_playing(self):
        return self.mp.playbackState() == QMediaPlayer.PlayingState

    def _step(self, direction):
        n = len(self.queue)
        if not n:
            return None
        if self.index not in self._order:
            self._rebuild_order(self.index)
        pos = self._order.index(self.index) if self.index in self._order else -1
        new = pos + direction
        if new >= n or new < 0:
            if self.repeat == "all":
                if self.shuffle and direction > 0:
                    self._rebuild_order(-1)
                new %= n
            else:
                return None
        return self._order[new]

    def next(self, auto=False):
        if auto and self.repeat == "one":
            self._src_path = self.current()
            self.mp.setPosition(0)
            self.mp.play()
            self._counted = False
            return
        nxt = self._step(+1)
        if nxt is None:
            if auto:
                self.stop()
            return
        self.play_index(nxt, True)

    def previous(self):
        if self.mp.position() > 3000:
            self.mp.setPosition(0)
            return
        prv = self._step(-1)
        if prv is not None:
            self.play_index(prv, True)

    def seek(self, ms):
        self.mp.setPosition(max(0, int(ms)))

    def jump(self, delta_ms):
        self.seek(self.mp.position() + delta_ms)

    def set_volume(self, value):
        value = max(0, min(100, int(value)))
        self.audio.setVolume((value / 100.0) ** 2)    # feels linear to the ear
        settings["volume"] = value

    def volume(self):
        return settings.get("volume", 72)

    def set_muted(self, muted):
        self.audio.setMuted(muted)
        settings["muted"] = bool(muted)

    def set_rate(self, rate):
        rate = max(0.25, min(4.0, round(rate, 2)))
        self.mp.setPlaybackRate(rate)
        settings["rate"] = rate

    def set_shuffle(self, on):
        self.shuffle = bool(on)
        settings["shuffle"] = self.shuffle
        self._rebuild_order(self.index)
        self.modeChanged.emit()

    def cycle_repeat(self):
        self.repeat = {"off": "all", "all": "one", "one": "off"}.get(self.repeat, "off")
        settings["repeat"] = self.repeat
        self.modeChanged.emit()

    # ------------------------------------------------ media info
    def has_video(self):
        return self.mp.hasVideo()

    def meta_title(self):
        try:
            return self.mp.metaData().stringValue(QMediaMetaData.Title)
        except Exception:
            return ""

    def audio_tracks(self):
        out = []
        for i, md in enumerate(self.mp.audioTracks()):
            lang = md.stringValue(QMediaMetaData.Language)
            title = md.stringValue(QMediaMetaData.Title)
            out.append((i, " · ".join(x for x in (title, lang) if x) or f"#{i + 1}"))
        return out

    def subtitle_tracks(self):
        out = []
        for i, md in enumerate(self.mp.subtitleTracks()):
            lang = md.stringValue(QMediaMetaData.Language)
            title = md.stringValue(QMediaMetaData.Title)
            out.append((i, " · ".join(x for x in (title, lang) if x) or f"#{i + 1}"))
        return out

    # ------------------------------------------------ internals
    def _on_position(self, ms):
        self.positionChanged.emit(ms)
        dur = self.mp.duration()
        if not self._counted and dur > 0 and (ms > dur * 0.5 or ms > 240000):
            self._counted = True
            cur = self.current()
            if cur and not is_url(cur):
                self.finished.emit(cur, dur)

    def _on_status(self, status):
        if status == QMediaPlayer.LoadingMedia:
            self._seen_loading = True
        # stopping the previous file also reports LoadedMedia - only seek once the new file has really loaded
        ready = (status == QMediaPlayer.LoadedMedia and self._seen_loading) or status == QMediaPlayer.BufferedMedia
        if ready and self._pending_seek:
            ms, self._pending_seek = self._pending_seek, 0
            dur = self.mp.duration()
            if 0 < ms < (dur or ms + 1):
                self.mp.setPosition(ms)
                self.resumed.emit(ms)
        if status == QMediaPlayer.EndOfMedia:
            self._leave(at_end=True)
            self.next(auto=True)
        elif status == QMediaPlayer.InvalidMedia:
            self.error.emit(self.mp.errorString() or "Unsupported or damaged file")

    def _on_error(self, err, text):
        if err != QMediaPlayer.NoError:
            self.error.emit(text or "Playback error")


class ThumbnailMaker(QObject):
    """Grabs one frame (about 10 % into the video) of each requested video, one at a time, without sound,
    and saves it as a small JPEG. ready(video path, thumbnail file) is emitted for each one made."""
    ready = Signal(str, str)
    WIDTH, HEIGHT = 384, 216

    def __init__(self, parent=None):
        super().__init__(parent)
        self.player = QMediaPlayer(self)
        self.sink = QVideoSink(self)
        self.player.setVideoSink(self.sink)
        self.sink.videoFrameChanged.connect(self._frame)
        self.player.mediaStatusChanged.connect(self._status)
        self.player.errorOccurred.connect(lambda *_: self._finish(None))
        self.todo = []
        self.current = None
        self.target = 0
        self.best = None
        self.timer = QTimer(self, singleShot=True, interval=8000, timeout=lambda: self._finish(self.best))

    def request(self, path, out):
        if self.current and self.current[0] == path:
            return
        if any(p == path for p, _o in self.todo):
            return
        self.todo.append((path, out))
        if self.current is None:
            QTimer.singleShot(0, self._next)

    def clear(self):
        self.todo.clear()

    def _next(self):
        if self.current is not None or not self.todo:
            return
        self.current = self.todo.pop(0)
        self.best = None
        self.target = 0
        self.timer.start()
        self.player.setSource(QUrl.fromLocalFile(self.current[0]))

    def _status(self, status):
        if self.current is None:
            return
        if status == QMediaPlayer.LoadedMedia:
            dur = self.player.duration()
            self.target = int(min(max(dur * 0.1, 0), 120000)) if dur > 0 else 0
            if self.target:
                self.player.setPosition(self.target)
            self.player.play()
        elif status == QMediaPlayer.InvalidMedia:
            self._finish(None)

    def _frame(self, frame):
        if self.current is None or not frame.isValid():
            return
        img = frame.toImage()
        if img.isNull():
            return
        self.best = img
        if self.player.position() >= self.target - 1500:
            self._finish(img)

    def _finish(self, img):
        if self.current is None:
            return
        path, out = self.current
        self.current = None
        self.timer.stop()
        self.player.stop()
        self.player.setSource(QUrl())
        if isinstance(img, QImage) and not img.isNull():
            img = img.scaled(self.WIDTH, self.HEIGHT, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            x, y = (img.width() - self.WIDTH) // 2, (img.height() - self.HEIGHT) // 2
            if img.copy(x, y, self.WIDTH, self.HEIGHT).save(out, "JPG", 85):
                self.ready.emit(path, out)
        QTimer.singleShot(50, self._next)
