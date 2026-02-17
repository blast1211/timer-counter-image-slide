from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFontComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from models.settings import AppSettings


class MediaSubtitleDialog(QDialog):
    def __init__(self, parent, settings: AppSettings):
        super().__init__(parent)
        self.setWindowTitle("Music & Subtitle Settings")
        self._settings = settings

        self.btn_pick_music = QPushButton("Select Music Files")
        self.lbl_music = QLabel(", ".join(settings.music_files) if settings.music_files else "(none)")

        self.spin_vol = QSpinBox()
        self.spin_vol.setRange(0, 100)
        self.spin_vol.setValue(int(settings.music_volume))

        self.btn_pick_srt = QPushButton("Select Subtitle (.srt)")
        self.lbl_srt = QLabel(settings.subtitle_file if settings.subtitle_file else "(none)")

        self.font_combo_kr = QFontComboBox()
        self.font_combo_kr.setCurrentFont(QFont(getattr(settings, "subtitle_kr_font_family", "Malgun Gothic")))
        self.spin_font_size_kr = QSpinBox()
        self.spin_font_size_kr.setRange(10, 300)
        self.spin_font_size_kr.setValue(int(getattr(settings, "subtitle_kr_font_size", 50)))
        self.chk_bold_kr = QCheckBox("Bold")
        self.chk_bold_kr.setChecked(bool(getattr(settings, "subtitle_kr_bold", False)))

        self.font_combo_en = QFontComboBox()
        self.font_combo_en.setCurrentFont(QFont(getattr(settings, "subtitle_en_font_family", "Arial")))
        self.spin_font_size_en = QSpinBox()
        self.spin_font_size_en.setRange(10, 300)
        self.spin_font_size_en.setValue(int(getattr(settings, "subtitle_en_font_size", 42)))
        self.chk_bold_en = QCheckBox("Bold")
        self.chk_bold_en.setChecked(bool(getattr(settings, "subtitle_en_bold", False)))

        self.spin_fade_in = QSpinBox()
        self.spin_fade_in.setRange(0, 5000)
        self.spin_fade_in.setSingleStep(50)
        self.spin_fade_in.setValue(int(getattr(settings, "subtitle_fade_in_ms", 250)))

        self.spin_fade_out = QSpinBox()
        self.spin_fade_out.setRange(0, 5000)
        self.spin_fade_out.setSingleStep(50)
        self.spin_fade_out.setValue(int(getattr(settings, "subtitle_fade_out_ms", 250)))

        self._subtitle_bg_color = str(getattr(settings, "subtitle_bg_color", "#000000"))
        self.btn_pick_bg_color = QPushButton("Pick Subtitle BG Color")
        self.lbl_bg_color = QLabel(self._subtitle_bg_color)
        self.lbl_bg_color.setStyleSheet(f"padding: 4px; background: {self._subtitle_bg_color}; color: white;")

        self.spin_bg_opacity = QSpinBox()
        self.spin_bg_opacity.setRange(0, 100)
        self.spin_bg_opacity.setValue(int(getattr(settings, "subtitle_bg_opacity_percent", 45)))

        self.spin_bg_pad_top = QSpinBox()
        self.spin_bg_pad_top.setRange(0, 200)
        self.spin_bg_pad_top.setValue(int(getattr(settings, "subtitle_bg_pad_top", 16)))

        self.spin_bg_pad_bottom = QSpinBox()
        self.spin_bg_pad_bottom.setRange(0, 200)
        self.spin_bg_pad_bottom.setValue(int(getattr(settings, "subtitle_bg_pad_bottom", 20)))

        form = QFormLayout()

        row_music = QHBoxLayout()
        row_music.addWidget(self.btn_pick_music)
        row_music.addWidget(self.lbl_music, 1)
        form.addRow("Music", row_music)
        form.addRow("Volume (0-100)", self.spin_vol)

        row_srt = QHBoxLayout()
        row_srt.addWidget(self.btn_pick_srt)
        row_srt.addWidget(self.lbl_srt, 1)
        form.addRow("Subtitle", row_srt)

        form.addRow(QLabel("---- Language Font ----"), QWidget())
        line_a = QFrame()
        line_a.setFrameShape(QFrame.HLine)
        line_a.setFrameShadow(QFrame.Sunken)
        form.addRow(line_a)
        form.addRow("Korean font", self.font_combo_kr)
        form.addRow("Korean size", self.spin_font_size_kr)
        form.addRow("Korean style", self.chk_bold_kr)
        form.addRow("English font", self.font_combo_en)
        form.addRow("English size", self.spin_font_size_en)
        form.addRow("English style", self.chk_bold_en)

        form.addRow(QLabel("---- Subtitle Motion ----"), QWidget())
        line_b = QFrame()
        line_b.setFrameShape(QFrame.HLine)
        line_b.setFrameShadow(QFrame.Sunken)
        form.addRow(line_b)
        form.addRow("Subtitle fade in (ms)", self.spin_fade_in)
        form.addRow("Subtitle fade out (ms)", self.spin_fade_out)

        form.addRow(QLabel("---- Subtitle Background ----"), QWidget())
        line_c = QFrame()
        line_c.setFrameShape(QFrame.HLine)
        line_c.setFrameShadow(QFrame.Sunken)
        form.addRow(line_c)
        row_bg_color = QHBoxLayout()
        row_bg_color.addWidget(self.btn_pick_bg_color)
        row_bg_color.addWidget(self.lbl_bg_color, 1)
        form.addRow("Subtitle BG color", row_bg_color)
        form.addRow("Subtitle BG opacity (%)", self.spin_bg_opacity)
        form.addRow("Subtitle BG top pad", self.spin_bg_pad_top)
        form.addRow("Subtitle BG bottom pad", self.spin_bg_pad_bottom)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addWidget(buttons)

        self.btn_pick_music.clicked.connect(self.pick_music)
        self.btn_pick_srt.clicked.connect(self.pick_srt)
        self.btn_pick_bg_color.clicked.connect(self.pick_subtitle_bg_color)

    def pick_music(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select music files",
            "",
            "Audio Files (*.mp3 *.wav *.m4a *.aac *.flac);;All Files (*.*)",
        )
        if not files:
            return
        self.lbl_music.setText(", ".join(files))
        self._picked_music = files

    def pick_srt(self):
        f, _ = QFileDialog.getOpenFileName(
            self,
            "Select subtitle file",
            "",
            "SubRip (*.srt);;All Files (*.*)",
        )
        if not f:
            return
        self.lbl_srt.setText(f)
        self._picked_srt = f

    def pick_subtitle_bg_color(self):
        c = QColorDialog.getColor(parent=self, title="Pick subtitle background color")
        if not c.isValid():
            return
        self._subtitle_bg_color = c.name()
        self.lbl_bg_color.setText(self._subtitle_bg_color)
        self.lbl_bg_color.setStyleSheet(f"padding: 4px; background: {self._subtitle_bg_color}; color: white;")

    def apply_to(self, s: AppSettings) -> AppSettings:
        if hasattr(self, "_picked_music"):
            s.music_files = list(self._picked_music)
        s.music_volume = int(self.spin_vol.value())

        if hasattr(self, "_picked_srt"):
            s.subtitle_file = str(self._picked_srt)

        s.subtitle_kr_font_family = self.font_combo_kr.currentFont().family()
        s.subtitle_kr_font_size = int(self.spin_font_size_kr.value())
        s.subtitle_kr_bold = bool(self.chk_bold_kr.isChecked())
        s.subtitle_en_font_family = self.font_combo_en.currentFont().family()
        s.subtitle_en_font_size = int(self.spin_font_size_en.value())
        s.subtitle_en_bold = bool(self.chk_bold_en.isChecked())
        s.subtitle_fade_in_ms = int(self.spin_fade_in.value())
        s.subtitle_fade_out_ms = int(self.spin_fade_out.value())
        s.subtitle_bg_color = str(self._subtitle_bg_color)
        s.subtitle_bg_opacity_percent = int(self.spin_bg_opacity.value())
        s.subtitle_bg_pad_top = int(self.spin_bg_pad_top.value())
        s.subtitle_bg_pad_bottom = int(self.spin_bg_pad_bottom.value())
        return s
