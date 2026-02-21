import time
from typing import Optional

from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from models.settings import KenBurnsType, TransitionType


class TransitionCanvas(QWidget):
    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self.setAutoFillBackground(False)

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
        self._ken_dir_cur = +1
        self._ken_dir_next = +1

        self.timer_active = False
        self.timer_end_ts = 0.0
        self.timer_font_family = "Arial"
        self.timer_font_size = 140
        self._timer_cache_text = ""
        self._timer_cache_pix: Optional[QPixmap] = None

        self.subtitle_cues = []
        self.subtitle_time_ms = 0
        self.subtitle_font_family = "Arial"
        self.subtitle_font_size = 48
        self.subtitle_kr_font_family = "Malgun Gothic"
        self.subtitle_kr_font_size = 50
        self.subtitle_kr_bold = False
        self.subtitle_en_font_family = "Arial"
        self.subtitle_en_font_size = 42
        self.subtitle_en_bold = False
        self.subtitle_fade_in_ms = 250
        self.subtitle_fade_out_ms = 250
        self.subtitle_bg_color = "#000000"
        self.subtitle_bg_opacity_percent = 45
        self.subtitle_bg_pad_top = 16
        self.subtitle_bg_pad_bottom = 20
        self.subtitle_alpha_mul = 1.0

        self.black_alpha = 0.0

    def set_subtitles(
        self,
        cues,
        family: str,
        size: int,
        kr_family: str = "Malgun Gothic",
        kr_size: int = 50,
        kr_bold: bool = False,
        en_family: str = "Arial",
        en_size: int = 42,
        en_bold: bool = False,
        fade_in_ms: int = 250,
        fade_out_ms: int = 250,
        bg_color: str = "#000000",
        bg_opacity_percent: int = 45,
        bg_pad_top: int = 16,
        bg_pad_bottom: int = 20,
    ):
        self.subtitle_cues = cues or []
        self.subtitle_font_family = family or "Arial"
        self.subtitle_font_size = max(10, int(size))
        self.subtitle_kr_font_family = kr_family or self.subtitle_font_family
        self.subtitle_kr_font_size = max(10, int(kr_size))
        self.subtitle_kr_bold = bool(kr_bold)
        self.subtitle_en_font_family = en_family or self.subtitle_font_family
        self.subtitle_en_font_size = max(10, int(en_size))
        self.subtitle_en_bold = bool(en_bold)
        self.subtitle_fade_in_ms = max(0, int(fade_in_ms))
        self.subtitle_fade_out_ms = max(0, int(fade_out_ms))
        self.subtitle_bg_color = str(bg_color or "#000000")
        self.subtitle_bg_opacity_percent = max(0, min(100, int(bg_opacity_percent)))
        self.subtitle_bg_pad_top = max(0, int(bg_pad_top))
        self.subtitle_bg_pad_bottom = max(0, int(bg_pad_bottom))
        self.update()

    def set_subtitle_time_ms(self, t_ms: int):
        self.subtitle_time_ms = max(0, int(t_ms))
        self.update()

    def _subtitle_alpha_for_cue(self, cue) -> float:
        duration = max(1, int(cue.end_ms) - int(cue.start_ms))
        fade_in_ms = min(self.subtitle_fade_in_ms, duration // 2)
        fade_out_ms = min(self.subtitle_fade_out_ms, duration // 2)
        t = int(self.subtitle_time_ms)

        alpha = 1.0
        if fade_in_ms > 0 and t < cue.start_ms + fade_in_ms:
            alpha = min(alpha, max(0.0, (t - cue.start_ms) / float(fade_in_ms)))
        if fade_out_ms > 0 and t > cue.end_ms - fade_out_ms:
            alpha = min(alpha, max(0.0, (cue.end_ms - t) / float(fade_out_ms)))
        return max(0.0, min(1.0, alpha))

    def _draw_subtitle_background(self, painter: QPainter, bg_top: int, bg_bottom: int):
        base = QColor(self.subtitle_bg_color)
        if not base.isValid():
            base = QColor("#000000")

        bg_left = 0
        bg_width = self.width()
        bg_top = max(0, int(bg_top))
        bg_bottom = min(self.height(), int(bg_bottom))
        bg_height = max(0, bg_bottom - bg_top)
        if bg_height <= 0:
            return

        alpha = int(round(255 * (self.subtitle_bg_opacity_percent / 100.0)))
        color = QColor(base)
        color.setAlpha(max(0, min(255, alpha)))

        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawRect(QRect(bg_left, bg_top, bg_width, bg_height))

    def _line_uses_korean(self, text: str) -> bool:
        for ch in text:
            code = ord(ch)
            if 0xAC00 <= code <= 0xD7A3:
                return True
            if 0x1100 <= code <= 0x11FF:
                return True
            if 0x3130 <= code <= 0x318F:
                return True
        return False

    def _font_for_subtitle_line(self, text: str) -> QFont:
        if self._line_uses_korean(text):
            f = QFont(self.subtitle_kr_font_family, self.subtitle_kr_font_size)
            f.setBold(self.subtitle_kr_bold)
            return f
        f = QFont(self.subtitle_en_font_family, self.subtitle_en_font_size)
        f.setBold(self.subtitle_en_bold)
        return f

    def _draw_subtitle_overlay(self, painter: QPainter):
        if not self.subtitle_cues:
            return

        from core.subtitles import find_cue

        w, h = self.width(), self.height()
        text_area = QRect(int(w * 0.08), int(h * 0.68), int(w * 0.84), int(h * 0.28))

        painter.save()
        cue = find_cue(self.subtitle_cues, self.subtitle_time_ms)
        flags = Qt.AlignHCenter | Qt.AlignVCenter | Qt.TextWordWrap

        line_entries: list[tuple[str, QFont, int]] = []
        if cue is not None:
            raw_lines = [ln for ln in cue.text.splitlines() if ln.strip()]
            if not raw_lines:
                raw_lines = [cue.text]
            for line in raw_lines:
                font = self._font_for_subtitle_line(line)
                fm = QFontMetrics(font)
                bounds = fm.boundingRect(QRect(0, 0, text_area.width(), 10000), flags, line)
                line_h = max(fm.height(), bounds.height())
                line_entries.append((line, font, line_h))
        else:
            fallback_font = QFont(self.subtitle_font_family, self.subtitle_font_size)
            fm = QFontMetrics(fallback_font)
            line_entries.append(("A", fallback_font, fm.height()))

        line_spacing = 6
        total_h = sum(hh for _, _, hh in line_entries) + max(0, len(line_entries) - 1) * line_spacing
        center_y = text_area.center().y()
        text_top = center_y - (total_h // 2)
        text_bottom = text_top + total_h

        bg_top = text_top - self.subtitle_bg_pad_top
        bg_bottom = text_bottom + self.subtitle_bg_pad_bottom
        self._draw_subtitle_background(painter, bg_top, bg_bottom)

        if cue is not None:
            cue_alpha = self._subtitle_alpha_for_cue(cue) * self.subtitle_alpha_mul
            painter.setOpacity(0.95 * cue_alpha)
            y = text_top
            for line, font, line_h in line_entries:
                line_rect = QRect(text_area.left(), int(y), text_area.width(), line_h)
                painter.setFont(font)
                painter.setPen(QPen(Qt.black, 6))
                painter.drawText(line_rect, flags, line)
                painter.setPen(QPen(Qt.white, 1))
                painter.drawText(line_rect, flags, line)
                y += line_h + line_spacing
        painter.restore()

    def set_effects(self, transition_type: str, transition_ms: int, hold_ms: int, kenburns: str, ken_strength_percent: int):
        self.transition_type = transition_type
        self.transition_ms = max(0, int(transition_ms))
        self.hold_ms = max(1, int(hold_ms))
        self.kenburns = kenburns
        self.ken_strength = max(0, ken_strength_percent) / 100.0

    def set_timer_style(self, family: str, size: int):
        self.timer_font_family = family or "Arial"
        self.timer_font_size = max(10, int(size))
        self._timer_cache_text = ""
        self._timer_cache_pix = None
        self.update()

    def start_timer(self, total_seconds: int):
        total_seconds = max(0, int(total_seconds))
        if total_seconds <= 0:
            self.timer_active = False
            self._timer_cache_text = ""
            self._timer_cache_pix = None
            self.update()
            return
        self.timer_active = True
        self.timer_end_ts = time.monotonic() + float(total_seconds)
        self._timer_cache_text = ""
        self._timer_cache_pix = None
        self.update()

    def stop_timer(self):
        self.timer_active = False
        self._timer_cache_text = ""
        self._timer_cache_pix = None
        self.update()

    def timer_remaining_seconds(self) -> int:
        if not self.timer_active:
            return 0
        rem = int(round(self.timer_end_ts - time.monotonic()))
        rem = max(0, rem)
        return rem

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
        if self.kenburns == KenBurnsType.ALTERNATE:
            self._ken_dir_cur = +1
            self._ken_dir_next = -1

        self.progress = 1.0
        self._current_start = time.monotonic()
        self._refresh_cache()
        self.update()

    def start_transition(self, next_pix: QPixmap):
        if self.current_src is None:
            self.set_current(next_pix)
            return
        if self.kenburns == KenBurnsType.ALTERNATE:
            self._ken_dir_next = -self._ken_dir_cur
        else:
            self._ken_dir_next = self._ken_dir_cur

        self.next_src = next_pix
        self._next_start = time.monotonic()
        self.progress = 0.0
        self._refresh_cache()
        self.update()

    def set_progress(self, p: float):
        self.progress = max(0.0, min(1.0, p))
        if self.progress >= 1.0 and self.next_src is not None:
            self.current_src = self.next_src
            self.next_src = None
            self.progress = 1.0
            self._current_start = self._next_start
            self._ken_dir_cur = self._ken_dir_next
            self._next_start = time.monotonic()
            self._refresh_cache()
        self.update()

    def _ken_duration_ms(self) -> float:
        t = float(max(0, self.transition_ms))
        h = float(max(1, self.hold_ms))
        return h + 2.0 * t

    def _ken_scale(self, start_t: float, now: Optional[float] = None, direction: int = +1) -> float:
        if self.kenburns == KenBurnsType.NONE or self.ken_strength <= 0:
            return 1.0
        if now is None:
            now = time.monotonic()
        dur = self._ken_duration_ms()
        elapsed_ms = (now - start_t) * 1000.0
        tt = max(0.0, min(1.0, elapsed_ms / dur))
        if self.kenburns == KenBurnsType.ZOOM_IN or (self.kenburns == KenBurnsType.ALTERNATE and direction > 0):
            return 1.0 + self.ken_strength * tt
        if self.kenburns == KenBurnsType.ZOOM_OUT or (self.kenburns == KenBurnsType.ALTERNATE and direction < 0):
            return 1.0 + self.ken_strength * (1.0 - tt)
        return 1.0

    def _draw_cover(self, painter: QPainter, cover: QPixmap, offset: tuple[float, float], alpha: float, scale: float, clip_w: Optional[int] = None):
        if cover is None or cover.isNull():
            return
        w, h = self.width(), self.height()
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
        text = self._format_mmss(rem)
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return

        if (
            self._timer_cache_pix is None
            or self._timer_cache_pix.size() != self.size()
            or self._timer_cache_text != text
        ):
            pm = QPixmap(self.size())
            pm.fill(Qt.transparent)
            pp = QPainter(pm)
            font = QFont(self.timer_font_family, self.timer_font_size)
            font.setBold(True)
            pp.setFont(font)
            rect = QRect(0, 0, w, h)
            pp.setOpacity(0.6)
            pp.setPen(QPen(Qt.black, 8))
            pp.drawText(rect.translated(3, 3), Qt.AlignCenter, text)
            pp.setOpacity(1.0)
            pp.setPen(QPen(Qt.white, 1))
            pp.drawText(rect, Qt.AlignCenter, text)
            pp.end()

            self._timer_cache_text = text
            self._timer_cache_pix = pm

        painter.drawPixmap(0, 0, self._timer_cache_pix)

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.fillRect(self.rect(), Qt.black)

        if self.current_cover is None:
            self._draw_timer_overlay(painter)
            self._draw_subtitle_overlay(painter)
            if self.black_alpha > 0:
                painter.save()
                painter.setOpacity(self.black_alpha)
                painter.fillRect(self.rect(), Qt.black)
                painter.restore()
            painter.end()
            return

        now = time.monotonic()
        cur_scale = self._ken_scale(self._current_start, now=now, direction=self._ken_dir_cur)

        if self.next_cover is None:
            self._draw_cover(painter, self.current_cover, self.current_offset, 1.0, cur_scale)
            self._draw_timer_overlay(painter)
            self._draw_subtitle_overlay(painter)
            if self.black_alpha > 0:
                painter.save()
                painter.setOpacity(self.black_alpha)
                painter.fillRect(self.rect(), Qt.black)
                painter.restore()
            painter.end()
            return

        nxt_scale = self._ken_scale(self._next_start, now=now, direction=self._ken_dir_next)
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
        self._draw_subtitle_overlay(painter)

        if self.black_alpha > 0:
            painter.save()
            painter.setOpacity(self.black_alpha)
            painter.fillRect(self.rect(), Qt.black)
            painter.restore()

        painter.end()

    def resizeEvent(self, e):
        self._refresh_cache()
        self._timer_cache_text = ""
        self._timer_cache_pix = None
        super().resizeEvent(e)
