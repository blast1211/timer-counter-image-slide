import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, QTimer, QRect, QObject, Signal
from PySide6.QtGui import (
    QGuiApplication, QPixmap, QPainter, QKeyEvent, QShortcut, QKeySequence,
    QFont, QPen
)
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QMainWindow,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QComboBox,
    QSpinBox,
    QFileDialog,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QMessageBox,
    QFontComboBox,
)

IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


# ---------------------------
# Settings / enums
# ---------------------------
class TransitionType:
    FADE = "Fade (Opacity)"
    SWEEP = "Sweep (Wipe L→R)"


class KenBurnsType:
    NONE = "None"
    ZOOM_IN = "Zoom In"
    ZOOM_OUT = "Zoom Out"


class OrderType:
    RANDOM = "Random"
    NAME = "Name (A→Z)"


@dataclass
class AppSettings:
    image_folder: str
    display_index: int = 1

    transition_type: str = TransitionType.FADE
    transition_ms: int = 600
    hold_ms: int = 3000

    kenburns: str = KenBurnsType.NONE
    kenburns_strength_percent: int = 10

    order: str = OrderType.RANDOM

    stay_on_top: bool = True
    hide_cursor: bool = True

    # Timer settings
    timer_start_seconds: int = 5 * 60 + 0   # default 5:00
    timer_font_family: str = "Arial"
    timer_font_size: int = 140


def list_images(folder: Path) -> List[Path]:
    if not folder.exists():
        return []
    files: List[Path] = []
    for p in folder.iterdir():
        if p.is_file() and p.suffix.lower() in IMG_EXT:
            files.append(p)
    return files



# ---------------------------
# Transition canvas (cached cover + zoom timeline includes transitions)
# + centered timer overlay
# ---------------------------
class TransitionCanvas(QWidget):
    """
    - Per-frame QPixmap.scaled() 최소화: 이미지/리사이즈 때 cover 캐시
    - KenBurns 시간축: (transition-in + hold + transition-out) = hold + 2*transition
    - Timer overlay: 중앙에 mm:ss 표시
    """
    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self.setAutoFillBackground(False)

        # slideshow images
        self.current_src: Optional[QPixmap] = None
        self.next_src: Optional[QPixmap] = None

        self.current_cover: Optional[QPixmap] = None
        self.next_cover: Optional[QPixmap] = None
        self.current_offset = (0.0, 0.0)
        self.next_offset = (0.0, 0.0)

        self.transition_type = TransitionType.FADE
        self.transition_ms = 600
        self.progress = 1.0

        self.hold_ms = 3000
        self.kenburns = KenBurnsType.NONE
        self.ken_strength = 0.10

        self._current_start = time.monotonic()
        self._next_start = time.monotonic()

        # timer overlay
        self.timer_active = False
        self.timer_end_ts = 0.0  # monotonic
        self.timer_font_family = "Arial"
        self.timer_font_size = 140

    # -------- effects --------
    def set_effects(self, transition_type: str, transition_ms: int, hold_ms: int,
                    kenburns: str, ken_strength_percent: int):
        self.transition_type = transition_type
        self.transition_ms = max(0, int(transition_ms))
        self.hold_ms = max(1, int(hold_ms))
        self.kenburns = kenburns
        self.ken_strength = max(0, ken_strength_percent) / 100.0

    def set_timer_style(self, family: str, size: int):
        self.timer_font_family = family or "Arial"
        self.timer_font_size = max(10, int(size))
        self.update()

    # -------- timer control --------
    def start_timer(self, total_seconds: int):
        total_seconds = max(0, int(total_seconds))
        if total_seconds <= 0:
            self.timer_active = False
            self.update()
            return
        self.timer_active = True
        self.timer_end_ts = time.monotonic() + float(total_seconds)
        self.update()

    def stop_timer(self):
        self.timer_active = False
        self.update()

    def timer_remaining_seconds(self) -> int:
        if not self.timer_active:
            return 0
        rem = int(round(self.timer_end_ts - time.monotonic()))
        return max(0, rem)

    # -------- slideshow cache --------
    def clear(self):
        self.current_src = None
        self.next_src = None
        self.current_cover = None
        self.next_cover = None
        self.progress = 1.0
        self.update()

    def _make_cover(self, src: QPixmap) -> tuple[QPixmap, tuple[float, float]]:
        w, h = self.width(), self.height()
        cover = src.scaled(w, h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        ox = (w - cover.width()) / 2.0
        oy = (h - cover.height()) / 2.0
        return cover, (ox, oy)

    def _refresh_cache(self):
        if self.current_src is not None and not self.current_src.isNull() and self.width() > 0 and self.height() > 0:
            self.current_cover, self.current_offset = self._make_cover(self.current_src)
        else:
            self.current_cover = None

        if self.next_src is not None and not self.next_src.isNull() and self.width() > 0 and self.height() > 0:
            self.next_cover, self.next_offset = self._make_cover(self.next_src)
        else:
            self.next_cover = None

    def set_current(self, pix: QPixmap):
        self.current_src = pix
        self.next_src = None
        self.progress = 1.0
        self._current_start = time.monotonic()
        self._refresh_cache()
        self.update()

    def start_transition(self, next_pix: QPixmap):
        if self.current_src is None:
            self.set_current(next_pix)
            return
        self.next_src = next_pix
        self._next_start = time.monotonic()  # next zoom timeline starts at transition start
        self.progress = 0.0
        self._refresh_cache()
        self.update()

    def set_progress(self, p: float):
        self.progress = max(0.0, min(1.0, p))
        if self.progress >= 1.0 and self.next_src is not None:
            # commit next -> current, and KEEP zoom timeline by inheriting next_start
            self.current_src = self.next_src
            self.next_src = None
            self.progress = 1.0
            self._current_start = self._next_start
            self._next_start = time.monotonic()
            self._refresh_cache()
        self.update()

    # -------- kenburns scale --------
    def _ken_duration_ms(self) -> float:
        # include transitions so zoom doesn't "finish early" during hold
        t = float(max(0, self.transition_ms))
        h = float(max(1, self.hold_ms))
        return h + 2.0 * t

    def _ken_scale(self, start_t: float, now: Optional[float] = None) -> float:
        if self.kenburns == KenBurnsType.NONE or self.ken_strength <= 0:
            return 1.0
        if now is None:
            now = time.monotonic()

        dur = self._ken_duration_ms()
        elapsed_ms = (now - start_t) * 1000.0
        tt = max(0.0, min(1.0, elapsed_ms / dur))

        if self.kenburns == KenBurnsType.ZOOM_IN:
            return 1.0 + self.ken_strength * tt
        if self.kenburns == KenBurnsType.ZOOM_OUT:
            return 1.0 + self.ken_strength * (1.0 - tt)
        return 1.0

    def _draw_cover(self, painter: QPainter, cover: QPixmap, offset: tuple[float, float],
                    alpha: float, scale: float, clip_w: Optional[int] = None):
        if cover is None or cover.isNull():
            return
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return

        painter.save()
        if clip_w is not None:
            painter.setClipRect(0, 0, clip_w, h)

        painter.setOpacity(max(0.0, min(1.0, alpha)))

        cx, cy = w / 2.0, h / 2.0
        painter.translate(cx, cy)
        painter.scale(scale, scale)
        painter.translate(-cx, -cy)

        ox, oy = offset
        painter.drawPixmap(int(ox), int(oy), cover)
        painter.restore()

    def _format_mmss(self, seconds: int) -> str:
        m = seconds // 60
        s = seconds % 60
        return f"{m}:{s:02d}"

    def _draw_timer_overlay(self, painter: QPainter):
        if not self.timer_active:
            return

        rem = self.timer_remaining_seconds()
        txt = self._format_mmss(rem)

        # auto stop when reached 0 (but keep showing 0:00 for one frame is OK)
        if rem <= 0:
            self.timer_active = False

        w, h = self.width(), self.height()
        font = QFont(self.timer_font_family, self.timer_font_size)
        font.setBold(True)
        painter.save()
        painter.setFont(font)

        # Outline for readability
        painter.setOpacity(1.0)
        painter.setPen(QPen(Qt.black, 8))
        painter.drawText(QRect(0, 0, w, h), Qt.AlignCenter, txt)

        painter.setPen(QPen(Qt.white, 1))
        painter.drawText(QRect(0, 0, w, h), Qt.AlignCenter, txt)

        painter.restore()

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.fillRect(self.rect(), Qt.black)

        if self.current_cover is None:
            # still draw timer if running (rare)
            self._draw_timer_overlay(painter)
            painter.end()
            return

        now = time.monotonic()
        cur_scale = self._ken_scale(self._current_start, now=now)

        if self.next_cover is None:
            self._draw_cover(painter, self.current_cover, self.current_offset, 1.0, cur_scale)
            self._draw_timer_overlay(painter)
            painter.end()
            return

        nxt_scale = self._ken_scale(self._next_start, now=now)

        p = self.progress
        if self.transition_type == TransitionType.FADE:
            self._draw_cover(painter, self.current_cover, self.current_offset, 1.0 - p, cur_scale)
            self._draw_cover(painter, self.next_cover, self.next_offset, p, nxt_scale)
        elif self.transition_type == TransitionType.SWEEP:
            self._draw_cover(painter, self.current_cover, self.current_offset, 1.0, cur_scale)
            clip_w = int(self.width() * p)
            self._draw_cover(painter, self.next_cover, self.next_offset, 1.0, nxt_scale, clip_w=clip_w)
        else:
            self._draw_cover(painter, self.current_cover, self.current_offset, 1.0, cur_scale)
            self._draw_cover(painter, self.next_cover, self.next_offset, p, nxt_scale)

        self._draw_timer_overlay(painter)
        painter.end()

    def resizeEvent(self, e):
        self._refresh_cache()
        super().resizeEvent(e)


# ---------------------------
# SlideShow output window (ONLY show when started)
# ---------------------------
class SlideShowWindow(QWidget):
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

        # redraw for kenburns + timer (30fps)
        self.render_timer = QTimer(self)
        self.render_timer.timeout.connect(self.canvas.update)
        self.render_timer.setInterval(33)

        # start hidden
        self.setVisible(False)
        self.apply_settings(settings)

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
        geom = screens[idx].geometry()
        self.setGeometry(geom)

    def apply_settings(self, s: AppSettings):
        self.settings = s
        folder = Path(s.image_folder)
        folder.mkdir(parents=True, exist_ok=True)

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

    def refresh_files(self, force: bool = False):
        folder = Path(self.settings.image_folder)
        files = list_images(folder)

        if self.settings.order == OrderType.NAME:
            files.sort(key=lambda p: p.name.lower())
        else:
            files.sort(key=lambda p: p.name.lower())

        if force or files != self._all_files:
            self._all_files = files
            self._rebuild_deck()

    def _rebuild_deck(self):
        self._deck = self._all_files[:]
        if self.settings.order == OrderType.RANDOM:
            random.shuffle(self._deck)

    def start(self):
        if self._running:
            return
        self._running = True

        self.refresh_files(force=True)
        if not self._all_files:
            self._running = False
            return

        self.move_to_display(self.settings.display_index)
        self.showFullScreen()
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
        self.canvas.stop_timer()
        self.canvas.clear()
        self.hide()

    def start_timer_now(self):
        # start/restart timer during slideshow
        if not self._running:
            return
        self.canvas.start_timer(self.settings.timer_start_seconds)

    def stop_timer_now(self):
        self.canvas.stop_timer()

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

        path = self._deck.pop(0) if self.settings.order == OrderType.NAME else self._deck.pop()
        pix = QPixmap(str(path))
        if pix.isNull():
            return None
        return pix

    def _on_hold_timeout(self):
        if not self._running:
            return
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


# ---------------------------
# Settings dialogs
# ---------------------------
class SettingsDialog(QDialog):
    def __init__(self, parent: QWidget, settings: AppSettings):
        super().__init__(parent)
        self.setWindowTitle("Slideshow Settings")
        self._settings = settings

        self.folder_btn = QPushButton("폴더 선택")
        self.folder_label = QLabel(settings.image_folder)

        self.combo_transition = QComboBox()
        self.combo_transition.addItems([TransitionType.FADE, TransitionType.SWEEP])
        self.combo_transition.setCurrentText(settings.transition_type)

        self.spin_transition = QSpinBox()
        self.spin_transition.setRange(0, 10000)
        self.spin_transition.setValue(settings.transition_ms)

        self.spin_hold = QSpinBox()
        self.spin_hold.setRange(200, 600000)
        self.spin_hold.setSingleStep(200)
        self.spin_hold.setValue(settings.hold_ms)

        self.combo_ken = QComboBox()
        self.combo_ken.addItems([KenBurnsType.NONE, KenBurnsType.ZOOM_IN, KenBurnsType.ZOOM_OUT])
        self.combo_ken.setCurrentText(settings.kenburns)

        self.spin_ken_strength = QSpinBox()
        self.spin_ken_strength.setRange(0, 50)
        self.spin_ken_strength.setValue(settings.kenburns_strength_percent)

        self.combo_order = QComboBox()
        self.combo_order.addItems([OrderType.RANDOM, OrderType.NAME])
        self.combo_order.setCurrentText(settings.order)

        form = QFormLayout()
        row_folder = QHBoxLayout()
        row_folder.addWidget(self.folder_btn)
        row_folder.addWidget(self.folder_label, 1)

        form.addRow("Image folder", row_folder)
        form.addRow("Transition type", self.combo_transition)
        form.addRow("Transition time (ms)", self.spin_transition)
        form.addRow("Hold time per image (ms)", self.spin_hold)
        form.addRow("Zoom effect", self.combo_ken)
        form.addRow("Zoom strength (%)", self.spin_ken_strength)
        form.addRow("Order", self.combo_order)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addWidget(buttons)

        self.folder_btn.clicked.connect(self.pick_folder)

    def pick_folder(self):
        start = self.folder_label.text()
        path = QFileDialog.getExistingDirectory(self, "이미지 폴더 선택", start)
        if not path:
            return
        self.folder_label.setText(path)

    def get_settings(self) -> AppSettings:
        # keep timer settings as-is
        return AppSettings(
            image_folder=self.folder_label.text(),
            display_index=self._settings.display_index,
            transition_type=self.combo_transition.currentText(),
            transition_ms=int(self.spin_transition.value()),
            hold_ms=int(self.spin_hold.value()),
            kenburns=self.combo_ken.currentText(),
            kenburns_strength_percent=int(self.spin_ken_strength.value()),
            order=self.combo_order.currentText(),
            stay_on_top=self._settings.stay_on_top,
            hide_cursor=self._settings.hide_cursor,
            timer_start_seconds=self._settings.timer_start_seconds,
            timer_font_family=self._settings.timer_font_family,
            timer_font_size=self._settings.timer_font_size,
        )


class TimerSettingsDialog(QDialog):
    def __init__(self, parent: QWidget, settings: AppSettings):
        super().__init__(parent)
        self.setWindowTitle("Timer Settings")
        self._settings = settings

        # start time (min/sec)
        total = max(0, int(settings.timer_start_seconds))
        self.spin_min = QSpinBox()
        self.spin_min.setRange(0, 999)
        self.spin_min.setValue(total // 60)

        self.spin_sec = QSpinBox()
        self.spin_sec.setRange(0, 59)
        self.spin_sec.setValue(total % 60)

        # font
        self.font_combo = QFontComboBox()
        self.font_combo.setCurrentFont(QFont(settings.timer_font_family))

        self.spin_font_size = QSpinBox()
        self.spin_font_size.setRange(10, 400)
        self.spin_font_size.setValue(int(settings.timer_font_size))

        form = QFormLayout()
        row_time = QHBoxLayout()
        row_time.addWidget(QLabel("Minutes"))
        row_time.addWidget(self.spin_min)
        row_time.addSpacing(12)
        row_time.addWidget(QLabel("Seconds"))
        row_time.addWidget(self.spin_sec)

        form.addRow("Start time", row_time)
        form.addRow("Font family", self.font_combo)
        form.addRow("Font size", self.spin_font_size)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addWidget(QLabel("Tip: 슬라이드 중 'T' = 타이머 시작, 'Shift+T' = 타이머 숨김"))
        root.addWidget(buttons)

    def apply_to(self, settings: AppSettings) -> AppSettings:
        mins = int(self.spin_min.value())
        secs = int(self.spin_sec.value())
        settings.timer_start_seconds = mins * 60 + secs
        settings.timer_font_family = self.font_combo.currentFont().family()
        settings.timer_font_size = int(self.spin_font_size.value())
        return settings


# ---------------------------
# Main window
# ---------------------------
class MainWindow(QMainWindow):
    def __init__(self, settings: AppSettings, slideshow: SlideShowWindow):
        super().__init__()
        self.setWindowTitle("Slideshow Main")

        self.settings = settings
        self.slideshow = slideshow

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        self.combo_display = QComboBox()
        self._populate_displays()
        self.combo_display.currentIndexChanged.connect(self._on_display_changed)

        row_disp = QHBoxLayout()
        row_disp.addWidget(QLabel("Display:"))
        row_disp.addWidget(self.combo_display, 1)

        self.btn_start = QPushButton("Start (F5)")
        self.btn_stop = QPushButton("Stop (F6)")
        self.btn_settings = QPushButton("Slideshow Settings")
        self.btn_timer_settings = QPushButton("Timer Settings")
        self.btn_timer_start = QPushButton("Start Timer (T)")

        row_btn1 = QHBoxLayout()
        row_btn1.addWidget(self.btn_start)
        row_btn1.addWidget(self.btn_stop)
        row_btn1.addStretch(1)

        row_btn2 = QHBoxLayout()
        row_btn2.addWidget(self.btn_settings)
        row_btn2.addWidget(self.btn_timer_settings)
        row_btn2.addStretch(1)
        row_btn2.addWidget(self.btn_timer_start)

        root.addLayout(row_disp)
        root.addLayout(row_btn1)
        root.addLayout(row_btn2)

        self.btn_start.clicked.connect(self.start_show)
        self.btn_stop.clicked.connect(self.stop_show)
        self.btn_settings.clicked.connect(self.open_slideshow_settings)
        self.btn_timer_settings.clicked.connect(self.open_timer_settings)
        self.btn_timer_start.clicked.connect(self.start_timer)

        # shortcuts (main window)
        QShortcut(QKeySequence("F5"), self, activated=self.start_show)
        QShortcut(QKeySequence("F6"), self, activated=self.stop_show)
        QShortcut(QKeySequence("T"), self, activated=self.start_timer)
        QShortcut(QKeySequence("Shift+T"), self, activated=self.stop_timer)

        self.resize(720, 160)

    def _populate_displays(self):
        self.combo_display.clear()
        screens = QGuiApplication.screens()
        for i, s in enumerate(screens):
            g = s.geometry()
            self.combo_display.addItem(
                f"[{i}] {s.name()}  {g.width()}x{g.height()} ({g.x()},{g.y()})", i
            )
        idx = max(0, min(self.settings.display_index, self.combo_display.count() - 1))
        self.combo_display.setCurrentIndex(idx)

    def _on_display_changed(self):
        data = self.combo_display.currentData()
        if data is None:
            return
        idx = int(data)
        self.settings.display_index = idx
        self.slideshow.move_to_display(idx)

    def start_show(self):
        self.slideshow.start()

    def stop_show(self):
        self.slideshow.stop()

    def start_timer(self):
        # Start timer even while slideshow running (preferred)
        self.slideshow.start_timer_now()

    def stop_timer(self):
        self.slideshow.stop_timer_now()

    def open_slideshow_settings(self):
        dlg = SettingsDialog(self, self.settings)
        if dlg.exec() != QDialog.Accepted:
            return

        new_s = dlg.get_settings()
        folder = Path(new_s.image_folder)
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"폴더 생성 실패: {e}")
            return

        self.settings = new_s
        self.slideshow.apply_settings(new_s)
        self._populate_displays()

    def open_timer_settings(self):
        dlg = TimerSettingsDialog(self, self.settings)
        if dlg.exec() != QDialog.Accepted:
            return

        self.settings = dlg.apply_to(self.settings)
        self.slideshow.apply_settings(self.settings)  # updates timer font too


# ---------------------------
# App
# ---------------------------
def main():
    app = QApplication(sys.argv)

    root = Path(__file__).resolve().parent
    slides = (root / "slides").resolve()
    slides.mkdir(parents=True, exist_ok=True)

    settings = AppSettings(
        image_folder=str(slides),
        display_index=1,
        transition_type=TransitionType.FADE,
        transition_ms=600,
        hold_ms=3000,
        kenburns=KenBurnsType.NONE,
        kenburns_strength_percent=10,
        order=OrderType.RANDOM,
        timer_start_seconds=5 * 60,
        timer_font_family="Arial",
        timer_font_size=140,
    )

    slideshow = SlideShowWindow(settings)
    mainwin = MainWindow(settings, slideshow)
    mainwin.show()

if __name__ == "__main__":
    main()
