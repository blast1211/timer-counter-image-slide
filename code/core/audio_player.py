from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QObject, Signal, QUrl
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput


class AudioPlayer(QObject):
    position_ms_changed = Signal(int)  # 자막 싱크용

    def __init__(self):
        super().__init__()
        self._player = QMediaPlayer()
        self._audio = QAudioOutput()
        self._player.setAudioOutput(self._audio)

        self._playlist: List[QUrl] = []
        self._index = 0

        self._player.positionChanged.connect(self.position_ms_changed.emit)
        self._player.mediaStatusChanged.connect(self._on_status)

    def set_volume_0_100(self, v: int):
        v = max(0, min(100, int(v)))
        self._audio.setVolume(v / 100.0)

    def load_files(self, paths: List[str]):
        self._playlist = []
        for p in paths:
            if not p:
                continue
            url = QUrl.fromLocalFile(str(Path(p).resolve()))
            self._playlist.append(url)
        self._index = 0

    def play(self):
        if not self._playlist:
            return
        self._player.setSource(self._playlist[self._index])
        self._player.play()
        print("[audio] state:", self._player.playbackState())
        print("[audio] source:", self._player.source().toString())


    def stop(self):
        self._player.stop()

    def is_playing(self) -> bool:
        return self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    def _on_status(self, st: QMediaPlayer.MediaStatus):
        # 곡 끝나면 다음 곡
        if st == QMediaPlayer.MediaStatus.EndOfMedia:
            if not self._playlist:
                return
            self._index = (self._index + 1) % len(self._playlist)
            self._player.setSource(self._playlist[self._index])
            self._player.play()
