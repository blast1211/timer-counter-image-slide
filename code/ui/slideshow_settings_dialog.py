from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QPushButton, QLabel, QComboBox, QSpinBox, QFileDialog,
    QDialogButtonBox, QFormLayout, QVBoxLayout, QHBoxLayout
)

from models.settings import AppSettings, TransitionType, KenBurnsType, OrderType


class SlideshowSettingsDialog(QDialog):
    def __init__(self, parent, settings: AppSettings):
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
        self.combo_ken.addItems([KenBurnsType.NONE, KenBurnsType.ZOOM_IN, KenBurnsType.ZOOM_OUT, KenBurnsType.ALTERNATE])
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

    def apply_to(self, s: AppSettings) -> AppSettings:
        folder = Path(self.folder_label.text())
        folder.mkdir(parents=True, exist_ok=True)

        s.image_folder = str(folder)
        s.transition_type = self.combo_transition.currentText()
        s.transition_ms = int(self.spin_transition.value())
        s.hold_ms = int(self.spin_hold.value())
        s.kenburns = self.combo_ken.currentText()
        s.kenburns_strength_percent = int(self.spin_ken_strength.value())
        s.order = self.combo_order.currentText()
        return s
