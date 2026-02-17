from __future__ import annotations

from dataclasses import replace
from typing import Dict, List

from PySide6.QtGui import QGuiApplication

from core.slideshow_window import SlideShowWindow
from models.settings import AppSettings


class MultiDisplaySlideShow:
    def __init__(self, settings: AppSettings):
        self.settings = settings
        self._windows: Dict[int, SlideShowWindow] = {}
        self._primary_index = 0
        self.apply_settings(settings)

    def _normalized_indices(self) -> List[int]:
        screens = QGuiApplication.screens()
        if not screens:
            return [0]
        n = len(screens)
        raw = list(getattr(self.settings, "display_indices", []) or [])
        if not raw:
            raw = [int(getattr(self.settings, "display_index", 0))]
        out: List[int] = []
        for idx in raw:
            i = max(0, min(int(idx), n - 1))
            if i not in out:
                out.append(i)
        if not out:
            out = [0]
        return out

    def _settings_for_window(self, idx: int, primary: bool) -> AppSettings:
        s = replace(self.settings)
        s.display_index = idx
        if not primary:
            s.music_files = []
        else:
            s.music_files = list(getattr(self.settings, "music_files", []))
        s.display_indices = list(self._normalized_indices())
        return s

    def _rebuild_windows(self):
        indices = self._normalized_indices()
        self.settings.display_indices = list(indices)
        self.settings.display_index = indices[0]
        self._primary_index = indices[0]

        for idx in list(self._windows.keys()):
            if idx not in indices:
                self._windows[idx].stop()
                self._windows[idx].deleteLater()
                del self._windows[idx]

        for idx in indices:
            if idx not in self._windows:
                self._windows[idx] = SlideShowWindow(self._settings_for_window(idx, idx == self._primary_index))

        for idx in indices:
            self._windows[idx].apply_settings(self._settings_for_window(idx, idx == self._primary_index))

        self._wire_subtitle_sync(indices)

    def _wire_subtitle_sync(self, indices: List[int]):
        if not indices:
            return
        primary = self._windows[indices[0]]
        for idx in indices[1:]:
            secondary = self._windows[idx]
            try:
                primary.audio.position_ms_changed.disconnect(secondary.canvas.set_subtitle_time_ms)
            except Exception:
                pass
            primary.audio.position_ms_changed.connect(secondary.canvas.set_subtitle_time_ms)

    def set_display_indices(self, indices: List[int]):
        self.settings.display_indices = list(indices)
        if self.settings.display_indices:
            self.settings.display_index = self.settings.display_indices[0]
        self._rebuild_windows()

    def move_to_display(self, display_index: int):
        self.set_display_indices([int(display_index)])

    def apply_settings(self, s: AppSettings):
        self.settings = s
        self._rebuild_windows()

    def start(self):
        self._rebuild_windows()
        for idx in self._normalized_indices():
            self._windows[idx].start()

    def stop(self):
        for w in self._windows.values():
            w.stop()

    def start_timer_now(self):
        for idx in self._normalized_indices():
            self._windows[idx].start_timer_now()

    def stop_timer_now(self):
        for w in self._windows.values():
            w.stop_timer_now()
