import random
import time
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication, QPixmap, QKeyEvent
from PySide6.QtWidgets import QWidget, QVBoxLayout

from models.settings import AppSettings, OrderType
from core.transition_canvas import TransitionCanvas
from core.audio_player import AudioPlayer
from core.subtitles import load_srt


IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def list_images(folder: Path) -> List[Path]:
    if not folder.exists():
        return []
    return [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in IMG_EXT]


class SlideShowWindow(QWidget):
    FADEOUT_TRIGGER_SECONDS = 1
    FADEOUT_DURATION_MS = 3000
    FADEOUT_POST_ZERO_HOLD_MS = 2000

    def __init__(self, settings: AppSettings):
        super().__init__()
        self.settings = settings

        self.canvas = TransitionCanvas()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.canvas)

        self._all_files: List[Path] = []
        self._deck: List[Path] = []
        self._running = False

        self.hold_timer = QTimer(self)
        self.hold_timer.timeout.connect(self._on_hold_timeout)

        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self._on_anim_tick)
        self._anim_start_ts = 0.0

        self.render_timer = QTimer(self)
        self.render_timer.timeout.connect(self.canvas.update)
        self.render_timer.setInterval(33)

        self.audio = AudioPlayer()
        self.audio.position_ms_changed.connect(self.canvas.set_subtitle_time_ms)

        self._fadeout_timer = QTimer(self)
        self._fadeout_timer.setInterval(33)
        self._fadeout_timer.timeout.connect(self._on_fadeout_tick)
        self._timer_fadeout_started = False
        self._fadeout_start_ts = 0.0
        self._fadeout_from_volume = 0

        self.setVisible(False)
        self.apply_settings(settings)
        self.render_timer.timeout.connect(self._tick_overlay)

    def _tick_overlay(self):
        if self.canvas.timer_active:
            rem = self.canvas.timer_remaining_seconds()
            if rem <= self._fadeout_trigger_seconds():
                self._start_timer_fadeout()

    def _fadeout_trigger_seconds(self) -> int:
        return max(0, int(getattr(self.settings, "timer_fadeout_trigger_seconds", self.FADEOUT_TRIGGER_SECONDS)))

    def _reset_fadeout_state(self):
        self._timer_fadeout_started = False
        self._fadeout_timer.stop()
        self._fadeout_start_ts = 0.0
        self._fadeout_from_volume = int(getattr(self.settings, "music_volume", 80))
        self.canvas.black_alpha = 0.0
        self.canvas.subtitle_alpha_mul = 1.0
        self.audio.set_volume_0_100(self._fadeout_from_volume)
        self.canvas.update()

    def _start_timer_fadeout(self):
        if self._timer_fadeout_started or not self._running:
            return
        self._timer_fadeout_started = True
        self._fadeout_start_ts = time.monotonic()
        self._fadeout_from_volume = int(getattr(self.settings, "music_volume", 80))
        self._fadeout_timer.start()

    def _apply_window_flags(self):
        flags = Qt.FramelessWindowHint
        if self.settings.stay_on_top:
            flags |= Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        if self.settings.hide_cursor:
            self.setCursor(Qt.BlankCursor)
        else:
            self.unsetCursor()

    def move_to_display(self, display_index: int):
        screens = QGuiApplication.screens()
        if not screens:
            return
        if display_index is None:
            display_index = 0
        idx = max(0, min(int(display_index), len(screens) - 1))
        self.settings.display_index = idx
        self.setGeometry(screens[idx].geometry())

    def apply_settings(self, s: AppSettings):
        self.settings = s
        folder = Path(s.image_folder)
        folder.mkdir(parents=True, exist_ok=True)

        self.audio.load_files(s.music_files)
        self.audio.set_volume_0_100(s.music_volume)

        cues = load_srt(s.subtitle_file) if s.subtitle_file else []
        self.canvas.set_subtitles(
            cues,
            s.subtitle_font_family,
            s.subtitle_font_size,
            getattr(s, "subtitle_kr_font_family", s.subtitle_font_family),
            getattr(s, "subtitle_kr_font_size", s.subtitle_font_size),
            getattr(s, "subtitle_kr_bold", False),
            getattr(s, "subtitle_en_font_family", s.subtitle_font_family),
            getattr(s, "subtitle_en_font_size", s.subtitle_font_size),
            getattr(s, "subtitle_en_bold", False),
            getattr(s, "subtitle_fade_in_ms", 250),
            getattr(s, "subtitle_fade_out_ms", 250),
            getattr(s, "subtitle_bg_color", "#000000"),
            getattr(s, "subtitle_bg_opacity_percent", 45),
            getattr(s, "subtitle_bg_pad_top", 16),
            getattr(s, "subtitle_bg_pad_bottom", 20),
        )

        self.canvas.set_effects(
            transition_type=s.transition_type,
            transition_ms=s.transition_ms,
            hold_ms=s.hold_ms,
            kenburns=s.kenburns,
            ken_strength_percent=s.kenburns_strength_percent,
        )
        self.canvas.set_timer_style(s.timer_font_family, s.timer_font_size)

        self._apply_window_flags()
        self.move_to_display(s.display_index)
        self.refresh_files(force=True)

        print("[apply_settings] music_files:", getattr(s, "music_files", None))
        print("[apply_settings] music_volume:", getattr(s, "music_volume", None))

    def refresh_files(self, force: bool = False):
        folder = Path(self.settings.image_folder)
        files = list_images(folder)
        files.sort(key=lambda p: p.name.lower())

        if force or files != self._all_files:
            self._all_files = files
            self._rebuild_deck()

    def _rebuild_deck(self):
        self._deck = self._all_files[:]
        if self.settings.order == OrderType.RANDOM:
            seed = int(getattr(self.settings, "shuffle_seed", 0))
            if seed > 0:
                rng = random.Random(seed)
                rng.shuffle(self._deck)
            else:
                random.shuffle(self._deck)

    def start(self):
        if self._running:
            return
        self._running = True
        self._reset_fadeout_state()
        self.refresh_files(force=True)
        if not self._all_files:
            self._running = False
            print(f"[start] No images found in: {self.settings.image_folder}")
            return

        self.move_to_display(self.settings.display_index)
        self.showFullScreen()
        if getattr(self.settings, "music_files", None):
            if len(self.settings.music_files) > 0:
                self.audio.load_files(self.settings.music_files)
                self.audio.set_volume_0_100(getattr(self.settings, "music_volume", 80))
                self.audio.play()
                print("[audio] autoplay:", self.settings.music_files[0])
            else:
                print("[audio] no music files")
        else:
            print("[audio] settings has no music_files")

        self.activateWindow()
        self.raise_()

        if self.canvas.current_src is None or self.canvas.current_src.isNull():
            pix = self._pop_next_pix()
            if pix:
                self.canvas.set_current(pix)

        self.hold_timer.start(self.settings.hold_ms)
        self.render_timer.start()

    def stop(self):
        self._running = False
        self.hold_timer.stop()
        self.anim_timer.stop()
        self.render_timer.stop()
        self._fadeout_timer.stop()
        self.canvas.stop_timer()
        self.canvas.black_alpha = 0.0
        self.canvas.subtitle_alpha_mul = 1.0
        self.canvas.clear()
        self.hide()
        self.audio.stop()
        self.audio.set_volume_0_100(int(getattr(self.settings, "music_volume", 80)))
        self._timer_fadeout_started = False

    def start_timer_now(self):
        if not self._running:
            return
        self._reset_fadeout_state()
        self.canvas.start_timer(self.settings.timer_start_seconds)

    def _on_fadeout_tick(self):
        if not self.canvas.timer_active or not self._timer_fadeout_started:
            self._fadeout_timer.stop()
            return

        elapsed_ms = (time.monotonic() - self._fadeout_start_ts) * 1000.0
        total_fade_ms = self._fadeout_trigger_seconds() * 1000 + self.FADEOUT_POST_ZERO_HOLD_MS
        fade_ms = max(self.FADEOUT_DURATION_MS, total_fade_ms)
        p = max(0.0, min(1.0, elapsed_ms / float(fade_ms)))

        self.audio.set_volume_0_100(int(round(self._fadeout_from_volume * (1.0 - p))))
        self.canvas.subtitle_alpha_mul = 1.0 - p
        self.canvas.black_alpha = p
        self.canvas.update()

        if p >= 1.0:
            self._fadeout_timer.stop()
            self.stop()

    def stop_timer_now(self):
        self.canvas.stop_timer()
        self._reset_fadeout_state()

    def next_now(self):
        if not self._running:
            return
        nxt = self._pop_next_pix()
        if nxt is None:
            return
        if self.settings.transition_ms <= 0:
            self.canvas.set_current(nxt)
            return
        self.canvas.start_transition(nxt)
        self._anim_start_ts = time.time()
        self.anim_timer.start(16)
        self.hold_timer.stop()

    def _pop_next_pix(self) -> Optional[QPixmap]:
        self.refresh_files()
        if not self._all_files:
            return None
        if not self._deck:
            self._rebuild_deck()

        path = self._deck.pop(0)
        pix = QPixmap(str(path))
        if pix.isNull():
            return None
        return pix

    def _on_hold_timeout(self):
        if self._running:
            self.next_now()

    def _on_anim_tick(self):
        elapsed_ms = (time.time() - self._anim_start_ts) * 1000.0
        p = elapsed_ms / float(max(1, self.settings.transition_ms))
        self.canvas.set_progress(p)

        if p >= 1.0:
            self.anim_timer.stop()
            if self._running:
                self.hold_timer.start(self.settings.hold_ms)

    def keyPressEvent(self, e: QKeyEvent):
        k = e.key()
        if k in (Qt.Key_Escape, Qt.Key_F6):
            self.stop()
            return
        if k == Qt.Key_F5:
            if not self._running:
                self.start()
            return
        if k == Qt.Key_Space:
            self.next_now()
            return
        if k == Qt.Key_T and not (e.modifiers() & Qt.ShiftModifier):
            self.start_timer_now()
            return
        if k == Qt.Key_T and (e.modifiers() & Qt.ShiftModifier):
            self.stop_timer_now()
            return
        super().keyPressEvent(e)
