from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QTimer, Qt, QUrl, Signal
from PySide6.QtGui import QKeyEvent, QKeySequence, QShortcut
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGridLayout,
    QHeaderView,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
    QAbstractItemView,
    QLineEdit,
    QStyledItemDelegate,
)


@dataclass
class SubtitleLine:
    text: str
    start_ms: Optional[int] = None
    end_ms: Optional[int] = None


class ClickSeekSlider(QSlider):
    clickedValue = Signal(int)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.orientation() == Qt.Orientation.Horizontal:
            x = int(event.position().x())
            x = max(0, min(self.width(), x))
            span = max(1, self.width())
            ratio = x / span
            value = self.minimum() + int(round((self.maximum() - self.minimum()) * ratio))
            self.setValue(value)
            self.clickedValue.emit(value)
            event.accept()
            return
        super().mousePressEvent(event)


class SubtitleTextEditor(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTabChangesFocus(True)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self.insertPlainText("\n")
                return
        super().keyPressEvent(event)


class SubtitleTextDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        if index.column() != 1:
            return super().createEditor(parent, option, index)
        editor = SubtitleTextEditor(parent)
        editor.installEventFilter(self)
        return editor

    def setEditorData(self, editor, index):
        if isinstance(editor, SubtitleTextEditor):
            editor.setPlainText(index.data() or "")
            return
        super().setEditorData(editor, index)

    def setModelData(self, editor, model, index):
        if isinstance(editor, SubtitleTextEditor):
            model.setData(index, editor.toPlainText())
            return
        super().setModelData(editor, model, index)

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)

    def eventFilter(self, editor, event):
        if isinstance(editor, SubtitleTextEditor) and event.type() == event.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    return False
                self.commitData.emit(editor)
                self.closeEditor.emit(editor)
                return True
        return super().eventFilter(editor, event)


def srt_time_to_ms(s: str) -> int:
    hh, mm, rest = s.strip().split(":")
    ss, ms = rest.split(",")
    return (int(hh) * 3600 + int(mm) * 60 + int(ss)) * 1000 + int(ms)


def ms_to_srt_time(ms: int) -> str:
    ms = max(0, int(ms))
    hh = ms // 3600000
    ms %= 3600000
    mm = ms // 60000
    ms %= 60000
    ss = ms // 1000
    ms %= 1000
    return f"{hh:02d}:{mm:02d}:{ss:02d},{ms:03d}"


def ms_to_display(ms: Optional[int]) -> str:
    if ms is None:
        return ""
    ms = max(0, int(ms))
    total_sec = ms // 1000
    msec = ms % 1000
    mm = total_sec // 60
    ss = total_sec % 60
    return f"{mm:02d}:{ss:02d}.{msec:03d}"


def parse_display_to_ms(s: str) -> Optional[int]:
    s = s.strip()
    if not s:
        return None
    if s.isdigit():
        return int(s)

    m = re.fullmatch(r"(\d+):([0-5]?\d)\.(\d{1,3})", s)
    if m:
        mm = int(m.group(1))
        ss = int(m.group(2))
        ms = int(m.group(3).ljust(3, "0"))
        return (mm * 60 + ss) * 1000 + ms
    return None


def parse_srt_file(path: Path) -> list[SubtitleLine]:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    blocks = [b.strip() for b in raw.split("\n\n") if b.strip()]
    out: list[SubtitleLine] = []
    for b in blocks:
        lines = [ln.rstrip("\r") for ln in b.splitlines()]
        if len(lines) < 2:
            continue
        time_line = lines[1] if "-->" in lines[1] else lines[0]
        if "-->" not in time_line:
            continue
        left, right = [x.strip() for x in time_line.split("-->")]
        try:
            start = srt_time_to_ms(left)
            end = srt_time_to_ms(right.split()[0])
        except Exception:
            continue
        text = "\n".join(lines[2:] if "-->" in lines[1] else lines[1:]).strip()
        if text:
            out.append(SubtitleLine(text=text, start_ms=start, end_ms=end))
    return out


def parse_lyrics_blocks(text: str) -> list[str]:
    norm = text.replace("\r\n", "\n").replace("\r", "\n")
    raw_blocks = re.split(r"\n\s*\n+", norm)
    out: list[str] = []
    for b in raw_blocks:
        blk = b.strip("\n")
        if not blk.strip():
            continue
        out.append(blk)
    return out


class SubtitleEditorWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Simple Audio Subtitle Editor")
        self.resize(1200, 760)

        self.lines: list[SubtitleLine] = []
        self.audio_path: Optional[Path] = None
        self._slider_dragging = False
        self._active_row = -1

        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.audio.setVolume(0.8)

        self.player.positionChanged.connect(self._on_position_changed)
        self.player.durationChanged.connect(self._on_duration_changed)

        self._build_ui()

        self.position_timer = QTimer(self)
        self.position_timer.setInterval(120)
        self.position_timer.timeout.connect(self._highlight_active_row)
        self.position_timer.start()

        QShortcut(QKeySequence("Space"), self, activated=self.toggle_play_pause)
        self.shortcut_tap = QShortcut(QKeySequence("Return"), self, activated=self.tap_current_line)
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self.export_srt)
        QShortcut(QKeySequence("["), self, activated=self.set_selected_start)
        QShortcut(QKeySequence("]"), self, activated=self.set_selected_end)
        QShortcut(QKeySequence("Up"), self, activated=lambda: self.move_selected_row(-1))
        QShortcut(QKeySequence("Down"), self, activated=lambda: self.move_selected_row(1))
        QShortcut(QKeySequence("Left"), self, activated=lambda: self.seek_relative(-self.spin_seek_step.value()))
        QShortcut(QKeySequence("Right"), self, activated=lambda: self.seek_relative(self.spin_seek_step.value()))
        QApplication.instance().focusChanged.connect(self._on_focus_changed)
        self._update_tap_shortcut_enabled()

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        audio_box = QGroupBox("Audio")
        audio_layout = QGridLayout(audio_box)
        self.audio_label = QLabel("(No audio selected)")
        self.btn_load_audio = QPushButton("Load Audio")
        self.btn_play = QPushButton("Play/Pause (Space)")
        self.btn_stop = QPushButton("Stop")
        self.slider = ClickSeekSlider(Qt.Horizontal)
        self.slider.setRange(0, 0)
        self.time_label = QLabel("00:00.000 / 00:00.000")
        self.spin_seek_step = QSpinBox()
        self.spin_seek_step.setRange(100, 10000)
        self.spin_seek_step.setSingleStep(100)
        self.spin_seek_step.setValue(1000)

        audio_layout.addWidget(self.btn_load_audio, 0, 0)
        audio_layout.addWidget(self.audio_label, 0, 1, 1, 4)
        audio_layout.addWidget(self.btn_play, 1, 0)
        audio_layout.addWidget(self.btn_stop, 1, 1)
        audio_layout.addWidget(self.time_label, 1, 2)
        audio_layout.addWidget(QLabel("Seek step(ms)"), 1, 3)
        audio_layout.addWidget(self.spin_seek_step, 1, 4)
        audio_layout.addWidget(self.slider, 2, 0, 1, 5)
        layout.addWidget(audio_box)

        body = QHBoxLayout()
        layout.addLayout(body, 1)

        left_box = QGroupBox("Lyrics Input")
        left_layout = QVBoxLayout(left_box)
        self.txt_lyrics = QTextEdit()
        self.txt_lyrics.setPlaceholderText("Paste lyrics here. One subtitle line per newline.")
        row_l = QHBoxLayout()
        self.btn_load_txt = QPushButton("Load TXT")
        self.btn_parse_lines = QPushButton("Parse Lines")
        self.btn_clear_lines = QPushButton("Clear")
        row_l.addWidget(self.btn_load_txt)
        row_l.addWidget(self.btn_parse_lines)
        row_l.addWidget(self.btn_clear_lines)
        left_layout.addWidget(self.txt_lyrics, 1)
        left_layout.addLayout(row_l)
        body.addWidget(left_box, 1)

        right_box = QGroupBox("Subtitle Timeline")
        right_layout = QVBoxLayout(right_box)

        control_row1 = QHBoxLayout()
        self.btn_tap = QPushButton("Tap Current Line (Enter)")
        self.btn_set_start = QPushButton("Set Start")
        self.btn_set_end = QPushButton("Set End")
        self.btn_clear_times = QPushButton("Clear Times")
        control_row1.addWidget(self.btn_tap)
        control_row1.addWidget(self.btn_set_start)
        control_row1.addWidget(self.btn_set_end)
        control_row1.addWidget(self.btn_clear_times)
        right_layout.addLayout(control_row1)

        control_row2 = QHBoxLayout()
        self.btn_add_line = QPushButton("Add Line")
        self.btn_insert_line = QPushButton("Insert Above")
        self.btn_remove_line = QPushButton("Remove Line")
        control_row2.addWidget(self.btn_add_line)
        control_row2.addWidget(self.btn_insert_line)
        control_row2.addWidget(self.btn_remove_line)
        right_layout.addLayout(control_row2)

        control_row3 = QHBoxLayout()
        self.spin_auto_duration = QSpinBox()
        self.spin_auto_duration.setRange(100, 20000)
        self.spin_auto_duration.setValue(2000)
        self.spin_auto_gap = QSpinBox()
        self.spin_auto_gap.setRange(0, 5000)
        self.spin_auto_gap.setValue(120)
        self.btn_auto = QPushButton("Auto Timing")
        self.btn_fill_ends = QPushButton("Fill Missing Ends")
        control_row3.addWidget(QLabel("Duration(ms)"))
        control_row3.addWidget(self.spin_auto_duration)
        control_row3.addWidget(QLabel("Gap(ms)"))
        control_row3.addWidget(self.spin_auto_gap)
        control_row3.addWidget(self.btn_auto)
        control_row3.addWidget(self.btn_fill_ends)
        right_layout.addLayout(control_row3)

        control_row4 = QHBoxLayout()
        self.spin_shift = QSpinBox()
        self.spin_shift.setRange(1, 10000)
        self.spin_shift.setValue(100)
        self.btn_shift_minus = QPushButton("Shift Selected -")
        self.btn_shift_plus = QPushButton("Shift Selected +")
        control_row4.addWidget(QLabel("Shift(ms)"))
        control_row4.addWidget(self.spin_shift)
        control_row4.addWidget(self.btn_shift_minus)
        control_row4.addWidget(self.btn_shift_plus)
        right_layout.addLayout(control_row4)

        file_row = QHBoxLayout()
        self.btn_import_srt = QPushButton("Import SRT")
        self.btn_export_srt = QPushButton("Export SRT (Ctrl+S)")
        self.btn_save_project = QPushButton("Save Project")
        self.btn_load_project = QPushButton("Load Project")
        file_row.addWidget(self.btn_import_srt)
        file_row.addWidget(self.btn_export_srt)
        file_row.addWidget(self.btn_save_project)
        file_row.addWidget(self.btn_load_project)
        right_layout.addLayout(file_row)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["#", "Text", "Start", "End", "Dur"])
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setStyleSheet(
            "QTableWidget::item:selected {"
            "background-color: rgb(20, 120, 220);"
            "color: white;"
            "}"
        )
        self.table.setItemDelegateForColumn(1, SubtitleTextDelegate(self.table))
        right_layout.addWidget(self.table, 1)
        body.addWidget(right_box, 2)

        self.btn_load_audio.clicked.connect(self.load_audio)
        self.btn_play.clicked.connect(self.toggle_play_pause)
        self.btn_stop.clicked.connect(self.stop_audio)
        self.slider.sliderPressed.connect(self._slider_press)
        self.slider.sliderReleased.connect(self._slider_release)
        self.slider.sliderMoved.connect(self._slider_move)
        self.slider.clickedValue.connect(self._seek_to_position)

        self.btn_load_txt.clicked.connect(self.load_txt)
        self.btn_parse_lines.clicked.connect(self.parse_lines)
        self.btn_clear_lines.clicked.connect(self.clear_lines)

        self.btn_tap.clicked.connect(self.tap_current_line)
        self.btn_set_start.clicked.connect(self.set_selected_start)
        self.btn_set_end.clicked.connect(self.set_selected_end)
        self.btn_clear_times.clicked.connect(self.clear_selected_times)
        self.btn_add_line.clicked.connect(self.add_line)
        self.btn_insert_line.clicked.connect(self.insert_line_above)
        self.btn_remove_line.clicked.connect(self.remove_selected_line)
        self.btn_auto.clicked.connect(self.auto_timing)
        self.btn_fill_ends.clicked.connect(self.fill_missing_ends)
        self.btn_shift_minus.clicked.connect(lambda: self.shift_selected(-self.spin_shift.value()))
        self.btn_shift_plus.clicked.connect(lambda: self.shift_selected(self.spin_shift.value()))
        self.btn_import_srt.clicked.connect(self.import_srt)
        self.btn_export_srt.clicked.connect(self.export_srt)
        self.btn_save_project.clicked.connect(self.save_project)
        self.btn_load_project.clicked.connect(self.load_project)
        self.table.itemChanged.connect(self.on_table_item_changed)
        self.table.currentCellChanged.connect(self._on_current_cell_changed)
        self.table.cellClicked.connect(self.on_table_cell_clicked)

    def _on_focus_changed(self, old, new):
        self._update_tap_shortcut_enabled()

    def _update_tap_shortcut_enabled(self):
        fw = QApplication.focusWidget()
        is_text_editing = isinstance(fw, (QTextEdit, QPlainTextEdit, QLineEdit))
        self.shortcut_tap.setEnabled(not is_text_editing)

    def load_audio(self):
        f, _ = QFileDialog.getOpenFileName(
            self,
            "Select audio",
            "",
            "Audio Files (*.mp3 *.wav *.m4a *.aac *.flac *.ogg);;All Files (*.*)",
        )
        if not f:
            return
        self.audio_path = Path(f)
        self.audio_label.setText(str(self.audio_path))
        self.player.setSource(QUrl.fromLocalFile(str(self.audio_path.resolve())))

    def toggle_play_pause(self):
        if self.player.source().isEmpty():
            return
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def stop_audio(self):
        self.player.stop()

    def seek_relative(self, delta_ms: int):
        if self.player.source().isEmpty():
            return
        cur = int(self.player.position())
        dur = int(self.player.duration())
        nxt = max(0, cur + int(delta_ms))
        if dur > 0:
            nxt = min(dur, nxt)
        self.player.setPosition(nxt)

    def _slider_press(self):
        self._slider_dragging = True

    def _slider_release(self):
        self._slider_dragging = False
        self.player.setPosition(self.slider.value())

    def _slider_move(self, v: int):
        self._update_time_label(v, self.player.duration())

    def _seek_to_position(self, pos: int):
        self.player.setPosition(int(pos))
        self._update_time_label(int(pos), self.player.duration())

    def _on_position_changed(self, pos: int):
        if not self._slider_dragging:
            self.slider.setValue(pos)
            self._update_time_label(pos, self.player.duration())

    def _on_duration_changed(self, dur: int):
        self.slider.setRange(0, max(0, int(dur)))
        self._update_time_label(self.player.position(), dur)

    def _update_time_label(self, pos: int, dur: int):
        self.time_label.setText(f"{ms_to_display(pos)} / {ms_to_display(dur)}")

    def load_txt(self):
        f, _ = QFileDialog.getOpenFileName(self, "Load TXT lyrics", "", "Text Files (*.txt);;All Files (*.*)")
        if not f:
            return
        text = Path(f).read_text(encoding="utf-8", errors="ignore")
        self.txt_lyrics.setPlainText(text)

    def parse_lines(self):
        text = self.txt_lyrics.toPlainText()
        blocks = parse_lyrics_blocks(text)
        self.lines = [SubtitleLine(text=b) for b in blocks]
        self.refresh_table(select_row=0 if self.lines else None)

    def clear_lines(self):
        self.lines = []
        self.refresh_table()

    def refresh_table(self, select_row: Optional[int] = None):
        cur = self.table.currentRow() if select_row is None else select_row
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.lines))
        for i, ln in enumerate(self.lines):
            idx_label = f"▶ {i + 1}" if i == self._active_row else str(i + 1)
            idx = QTableWidgetItem(idx_label)
            idx.setFlags(idx.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(i, 0, idx)
            self.table.setItem(i, 1, QTableWidgetItem(ln.text))
            self.table.setItem(i, 2, QTableWidgetItem(ms_to_display(ln.start_ms)))
            self.table.setItem(i, 3, QTableWidgetItem(ms_to_display(ln.end_ms)))
            line_count = max(1, ln.text.count("\n") + 1)
            self.table.setRowHeight(i, 26 + (line_count - 1) * 16)
            dur = None
            if ln.start_ms is not None and ln.end_ms is not None:
                dur = max(0, ln.end_ms - ln.start_ms)
            d_item = QTableWidgetItem("" if dur is None else str(dur))
            d_item.setFlags(d_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(i, 4, d_item)
        self.table.blockSignals(False)
        if 0 <= cur < self.table.rowCount():
            self.table.setCurrentCell(cur, 1)
            self.table.selectRow(cur)

    def _on_current_cell_changed(self, current_row: int, current_col: int, prev_row: int, prev_col: int):
        if current_row >= 0:
            self.table.selectRow(current_row)

    def on_table_cell_clicked(self, row: int, col: int):
        if col != 0:
            return
        if row < 0 or row >= len(self.lines):
            return
        ln = self.lines[row]
        target = ln.start_ms if ln.start_ms is not None else ln.end_ms
        if target is None:
            return
        self._seek_to_position(target)

    def on_table_item_changed(self, item: QTableWidgetItem):
        r, c = item.row(), item.column()
        if r < 0 or r >= len(self.lines):
            return
        ln = self.lines[r]
        if c == 1:
            ln.text = item.text().replace("\r\n", "\n").replace("\r", "\n")
        elif c == 2:
            ln.start_ms = parse_display_to_ms(item.text())
        elif c == 3:
            ln.end_ms = parse_display_to_ms(item.text())
        self.refresh_table(select_row=r)

    def _selected_row(self) -> int:
        r = self.table.currentRow()
        if r < 0 and self.lines:
            r = 0
            self.table.setCurrentCell(0, 1)
        return r

    def set_selected_start(self):
        r = self._selected_row()
        if r < 0:
            return
        self.lines[r].start_ms = self.player.position()
        self.refresh_table(select_row=r)

    def set_selected_end(self):
        r = self._selected_row()
        if r < 0:
            return
        self.lines[r].end_ms = self.player.position()
        self.refresh_table(select_row=r)

    def clear_selected_times(self):
        r = self._selected_row()
        if r < 0:
            return
        self.lines[r].start_ms = None
        self.lines[r].end_ms = None
        self.refresh_table(select_row=r)

    def move_selected_row(self, delta: int):
        if not self.lines:
            return
        r = self._selected_row()
        if r < 0:
            r = 0
        n = max(0, min(len(self.lines) - 1, r + delta))
        self.table.setCurrentCell(n, 1)
        self.table.selectRow(n)

    def add_line(self):
        self.lines.append(SubtitleLine(text=""))
        self.refresh_table(select_row=len(self.lines) - 1)

    def insert_line_above(self):
        r = self._selected_row()
        if r < 0:
            self.add_line()
            return
        self.lines.insert(r, SubtitleLine(text=""))
        self.refresh_table(select_row=r)

    def remove_selected_line(self):
        r = self._selected_row()
        if r < 0 or r >= len(self.lines):
            return
        del self.lines[r]
        if not self.lines:
            self._active_row = -1
            self.refresh_table()
            return
        next_row = min(r, len(self.lines) - 1)
        if self._active_row >= len(self.lines):
            self._active_row = len(self.lines) - 1
        self.refresh_table(select_row=next_row)

    def tap_current_line(self):
        r = self._selected_row()
        if r < 0:
            return
        now = self.player.position()
        self.lines[r].start_ms = now

        if r > 0:
            prev = self.lines[r - 1]
            prev_end = max(0, now - 1)
            if prev.start_ms is not None and prev_end < prev.start_ms:
                prev_end = prev.start_ms
            prev.end_ms = prev_end

        self.refresh_table(select_row=min(r + 1, len(self.lines) - 1))

    def auto_timing(self):
        if not self.lines:
            return
        dur = int(self.spin_auto_duration.value())
        gap = int(self.spin_auto_gap.value())
        t = 0
        for ln in self.lines:
            ln.start_ms = t
            ln.end_ms = t + dur
            t = ln.end_ms + gap
        self.refresh_table(select_row=0)

    def fill_missing_ends(self):
        if not self.lines:
            return
        default_dur = int(self.spin_auto_duration.value())
        for i, ln in enumerate(self.lines):
            if ln.start_ms is None:
                continue
            if ln.end_ms is not None:
                continue
            if i + 1 < len(self.lines) and self.lines[i + 1].start_ms is not None:
                ln.end_ms = max(ln.start_ms, self.lines[i + 1].start_ms - 1)
            else:
                ln.end_ms = ln.start_ms + default_dur
        self.refresh_table(select_row=self._selected_row())

    def shift_selected(self, delta_ms: int):
        r = self._selected_row()
        if r < 0:
            return
        ln = self.lines[r]
        if ln.start_ms is not None:
            ln.start_ms = max(0, ln.start_ms + delta_ms)
        if ln.end_ms is not None:
            ln.end_ms = max(0, ln.end_ms + delta_ms)
        if ln.start_ms is not None and ln.end_ms is not None and ln.end_ms < ln.start_ms:
            ln.end_ms = ln.start_ms
        self.refresh_table(select_row=r)

    def _highlight_active_row(self):
        pos = self.player.position()
        active = -1
        for i, ln in enumerate(self.lines):
            if ln.start_ms is None or ln.end_ms is None:
                continue
            if ln.start_ms <= pos <= ln.end_ms:
                active = i
                break
        if active != self._active_row:
            self._active_row = active
            self.refresh_table()

    def import_srt(self):
        f, _ = QFileDialog.getOpenFileName(self, "Import SRT", "", "SubRip (*.srt);;All Files (*.*)")
        if not f:
            return
        self.lines = parse_srt_file(Path(f))
        self.txt_lyrics.setPlainText("\n\n".join([ln.text for ln in self.lines]))
        self.refresh_table(select_row=0 if self.lines else None)

    def _validate_lines_for_export(self) -> bool:
        if not self.lines:
            QMessageBox.warning(self, "Export Error", "No subtitle lines.")
            return False
        for i, ln in enumerate(self.lines, start=1):
            if not ln.text:
                QMessageBox.warning(self, "Export Error", f"Line {i}: empty text.")
                return False
            if ln.start_ms is None or ln.end_ms is None:
                QMessageBox.warning(self, "Export Error", f"Line {i}: missing start/end.")
                return False
            if ln.end_ms < ln.start_ms:
                QMessageBox.warning(self, "Export Error", f"Line {i}: end < start.")
                return False
        return True

    def export_srt(self):
        if not self._validate_lines_for_export():
            return
        f, _ = QFileDialog.getSaveFileName(self, "Export SRT", "", "SubRip (*.srt)")
        if not f:
            return
        if not f.lower().endswith(".srt"):
            f += ".srt"

        chunks = []
        for i, ln in enumerate(self.lines, start=1):
            chunks.append(str(i))
            chunks.append(f"{ms_to_srt_time(ln.start_ms)} --> {ms_to_srt_time(ln.end_ms)}")
            chunks.append(ln.text)
            chunks.append("")
        Path(f).write_text("\n".join(chunks), encoding="utf-8")
        QMessageBox.information(self, "Export", f"Saved:\n{f}")

    def save_project(self):
        f, _ = QFileDialog.getSaveFileName(self, "Save Project", "", "JSON (*.json)")
        if not f:
            return
        if not f.lower().endswith(".json"):
            f += ".json"
        data = {
            "audio_path": str(self.audio_path) if self.audio_path else "",
            "lyrics": self.txt_lyrics.toPlainText(),
            "lines": [
                {"text": ln.text, "start_ms": ln.start_ms, "end_ms": ln.end_ms}
                for ln in self.lines
            ],
        }
        Path(f).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_project(self):
        f, _ = QFileDialog.getOpenFileName(self, "Load Project", "", "JSON (*.json);;All Files (*.*)")
        if not f:
            return
        data = json.loads(Path(f).read_text(encoding="utf-8"))
        self.txt_lyrics.setPlainText(str(data.get("lyrics", "")))
        self.lines = [
            SubtitleLine(
                text=str(row.get("text", "")),
                start_ms=row.get("start_ms"),
                end_ms=row.get("end_ms"),
            )
            for row in data.get("lines", [])
        ]
        ap = data.get("audio_path", "")
        if ap:
            self.audio_path = Path(ap)
            self.audio_label.setText(str(self.audio_path))
            if self.audio_path.exists():
                self.player.setSource(QUrl.fromLocalFile(str(self.audio_path.resolve())))
        self.refresh_table(select_row=0 if self.lines else None)


def main():
    app = QApplication(sys.argv)
    win = SubtitleEditorWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
