from dataclasses import dataclass, field

class TransitionType:
    FADE = "Fade (Opacity)"
    SWEEP = "Sweep (Wipe L→R)"

class KenBurnsType:
    NONE = "None"
    ZOOM_IN = "Zoom In"
    ZOOM_OUT = "Zoom Out"
    ALTERNATE = "Alternate (In/Out)"   # ✅ 추가

class OrderType:
    RANDOM = "Random"
    NAME = "Name (A→Z)"

@dataclass
class AppSettings:
    image_folder: str
    display_index: int = 1
    display_indices: list[int] = field(default_factory=list)

    transition_type: str = TransitionType.FADE
    transition_ms: int = 600
    hold_ms: int = 3000

    kenburns: str = KenBurnsType.NONE
    kenburns_strength_percent: int = 10

    order: str = OrderType.RANDOM

    stay_on_top: bool = True
    hide_cursor: bool = True

    # Timer
    timer_start_seconds: int = 5 * 60
    timer_font_family: str = "Arial"
    timer_font_size: int = 140
    timer_fadeout_trigger_seconds: int = 1


    # Media / Subtitle
    music_files: list[str] = field(default_factory=list)
    music_volume: int = 80

    subtitle_file: str = ""
    subtitle_font_family: str = "Arial"
    subtitle_font_size: int = 48
    subtitle_kr_font_family: str = "Malgun Gothic"
    subtitle_kr_font_size: int = 50
    subtitle_kr_bold: bool = False
    subtitle_en_font_family: str = "Arial"
    subtitle_en_font_size: int = 42
    subtitle_en_bold: bool = False
    subtitle_fade_in_ms: int = 250
    subtitle_fade_out_ms: int = 250
    subtitle_bg_color: str = "#000000"
    subtitle_bg_opacity_percent: int = 45
    subtitle_bg_pad_top: int = 16
    subtitle_bg_pad_bottom: int = 20
