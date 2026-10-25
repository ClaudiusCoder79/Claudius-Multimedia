"""Claudius Multimedia - playback engine (Qt Multimedia with its built-in FFmpeg backend) and the play queue."""
import os
import random

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaMetaData, QMediaPlayer

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
    def play_index(self, i, play=True):
        if not (0 <= i < len(self.queue)):
            return
        self.index = i
        self._counted = False
        src = self.queue[i]
        self.mp.setSource(QUrl(src) if is_url(src) else QUrl.fromLocalFile(os.path.abspath(src)))
        if play:
            self.mp.play()
        self.trackChanged.emit(i)

    def toggle(self):
        if self.index < 0 and self.queue:
            self.play_index(0)
        elif self.mp.playbackState() == QMediaPlayer.PlayingState:
            self.mp.pause()
        else:
            self.mp.play()

    def play(self):
        if self.index < 0 and self.queue:
            self.play_index(0)
        else:
            self.mp.play()

    def pause(self):
        self.mp.pause()

    def stop(self):
        self.mp.stop()

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
        if status == QMediaPlayer.EndOfMedia:
            self.next(auto=True)
        elif status == QMediaPlayer.InvalidMedia:
            self.error.emit(self.mp.errorString() or "Unsupported or damaged file")

    def _on_error(self, err, text):
        if err != QMediaPlayer.NoError:
            self.error.emit(text or "Playback error")
