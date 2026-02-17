from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QVBoxLayout, QHBoxLayout,
    QLabel, QSpinBox, QFontComboBox
)

from models.settings import AppSettings


class TimerSettingsDialog(QDialog):
    def __init__(self, parent, settings: AppSettings):
        super().__init__(parent)
        self.setWindowTitle("Timer Settings")
        self._settings = settings

        total = max(0, int(settings.timer_start_seconds))

        self.spin_min = QSpinBox()
        self.spin_min.setRange(0, 999)
        self.spin_min.setValue(total // 60)

        self.spin_sec = QSpinBox()
        self.spin_sec.setRange(0, 59)
        self.spin_sec.setValue(total % 60)

        self.font_combo = QFontComboBox()
        self.font_combo.setCurrentFont(QFont(settings.timer_font_family))

        self.spin_font_size = QSpinBox()
        self.spin_font_size.setRange(10, 400)
        self.spin_font_size.setValue(int(settings.timer_font_size))

        self.spin_fade_trigger = QSpinBox()
        self.spin_fade_trigger.setRange(0, 60)
        self.spin_fade_trigger.setValue(int(getattr(settings, "timer_fadeout_trigger_seconds", 1)))

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
        form.addRow("Fade start before end (sec)", self.spin_fade_trigger)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addWidget(QLabel("Tip: T=Start timer, Shift+T=Hide timer"))
        root.addWidget(buttons)

    def apply_to(self, s: AppSettings) -> AppSettings:
        mins = int(self.spin_min.value())
        secs = int(self.spin_sec.value())
        s.timer_start_seconds = mins * 60 + secs
        s.timer_font_family = self.font_combo.currentFont().family()
        s.timer_font_size = int(self.spin_font_size.value())
        s.timer_fadeout_trigger_seconds = int(self.spin_fade_trigger.value())
        return s
