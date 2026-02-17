from typing import List

from PySide6.QtGui import QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.settings_store import save_settings
from models.settings import AppSettings
from ui.media_subtitle_dialog import MediaSubtitleDialog
from ui.slideshow_settings_dialog import SlideshowSettingsDialog
from ui.timer_settings_dialog import TimerSettingsDialog


class DisplaySelectDialog(QDialog):
    def __init__(self, parent, selected: List[int]):
        super().__init__(parent)
        self.setWindowTitle("Select Displays")
        self._checks: List[QCheckBox] = []

        root = QVBoxLayout(self)
        screens = QGuiApplication.screens()
        selected_set = set(selected)
        for i, s in enumerate(screens):
            g = s.geometry()
            chk = QCheckBox(f"[{i}] {s.name()}  {g.width()}x{g.height()} ({g.x()},{g.y()})")
            chk.setChecked(i in selected_set)
            self._checks.append(chk)
            root.addWidget(chk)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def selected_indices(self) -> List[int]:
        out = [i for i, chk in enumerate(self._checks) if chk.isChecked()]
        return out if out else [0]


class MainWindow(QMainWindow):
    def __init__(self, settings: AppSettings, slideshow):
        super().__init__()
        self.setWindowTitle("Slideshow Main")

        self.settings = settings
        self.slideshow = slideshow

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        row_disp = QHBoxLayout()
        row_disp.addWidget(QLabel("Displays:"))
        self.lbl_displays = QLabel("")
        self.btn_select_displays = QPushButton("Select Displays")
        row_disp.addWidget(self.lbl_displays, 1)
        row_disp.addWidget(self.btn_select_displays)

        self.btn_start = QPushButton("Start (F5)")
        self.btn_stop = QPushButton("Stop (F6)")
        self.btn_slide_settings = QPushButton("Slideshow Settings")
        self.btn_timer_settings = QPushButton("Timer Settings")
        self.btn_timer_start = QPushButton("Start Timer (T)")
        self.btn_media_settings = QPushButton("Music & Subtitle Settings")

        row1 = QHBoxLayout()
        row1.addWidget(self.btn_start)
        row1.addWidget(self.btn_stop)
        row1.addStretch(1)

        row2 = QHBoxLayout()
        row2.addWidget(self.btn_slide_settings)
        row2.addWidget(self.btn_timer_settings)
        row2.addWidget(self.btn_media_settings)
        row2.addStretch(1)
        row2.addWidget(self.btn_timer_start)

        root.addLayout(row_disp)
        root.addLayout(row1)
        root.addLayout(row2)

        self.btn_select_displays.clicked.connect(self.open_display_selector)
        self.btn_start.clicked.connect(self.start_show)
        self.btn_stop.clicked.connect(self.stop_show)
        self.btn_slide_settings.clicked.connect(self.open_slideshow_settings)
        self.btn_timer_settings.clicked.connect(self.open_timer_settings)
        self.btn_timer_start.clicked.connect(self.start_timer)
        self.btn_media_settings.clicked.connect(self.open_media_settings)

        QShortcut(QKeySequence("F5"), self, activated=self.start_show)
        QShortcut(QKeySequence("F6"), self, activated=self.stop_show)
        QShortcut(QKeySequence("T"), self, activated=self.start_timer)
        QShortcut(QKeySequence("Shift+T"), self, activated=self.stop_timer)

        self._ensure_display_defaults()
        self._refresh_display_summary()
        self.slideshow.set_display_indices(self.settings.display_indices)

        self.resize(880, 180)

    def _ensure_display_defaults(self):
        screens = QGuiApplication.screens()
        if not screens:
            self.settings.display_indices = [0]
            self.settings.display_index = 0
            return
        max_idx = len(screens) - 1
        raw = list(getattr(self.settings, "display_indices", []) or [])
        if not raw:
            raw = [int(getattr(self.settings, "display_index", 0))]
        out: List[int] = []
        for idx in raw:
            i = max(0, min(int(idx), max_idx))
            if i not in out:
                out.append(i)
        if not out:
            out = [0]
        self.settings.display_indices = out
        self.settings.display_index = out[0]

    def _refresh_display_summary(self):
        screens = QGuiApplication.screens()
        labels: List[str] = []
        for idx in self.settings.display_indices:
            if 0 <= idx < len(screens):
                labels.append(f"[{idx}] {screens[idx].name()}")
            else:
                labels.append(f"[{idx}]")
        self.lbl_displays.setText(", ".join(labels))

    def open_display_selector(self):
        dlg = DisplaySelectDialog(self, self.settings.display_indices)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self.settings.display_indices = dlg.selected_indices()
        self.settings.display_index = self.settings.display_indices[0]
        self.slideshow.set_display_indices(self.settings.display_indices)
        self._refresh_display_summary()
        save_settings(self.settings)

    def start_show(self):
        self.slideshow.start()

    def stop_show(self):
        self.slideshow.stop()

    def start_timer(self):
        self.slideshow.start_timer_now()

    def stop_timer(self):
        self.slideshow.stop_timer_now()

    def open_slideshow_settings(self):
        dlg = SlideshowSettingsDialog(self, self.settings)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self.settings = dlg.apply_to(self.settings)
        self.slideshow.apply_settings(self.settings)
        self._ensure_display_defaults()
        self._refresh_display_summary()
        save_settings(self.settings)

    def open_timer_settings(self):
        dlg = TimerSettingsDialog(self, self.settings)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self.settings = dlg.apply_to(self.settings)
        self.slideshow.apply_settings(self.settings)
        save_settings(self.settings)

    def open_media_settings(self):
        dlg = MediaSubtitleDialog(self, self.settings)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self.settings = dlg.apply_to(self.settings)
        self.slideshow.apply_settings(self.settings)
        save_settings(self.settings)
