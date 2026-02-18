import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from models.settings import AppSettings
from core.multi_display_slideshow import MultiDisplaySlideShow
from ui.main_window import MainWindow

from core.settings_store import load_settings, save_settings


def _default_slides_dir() -> Path:
    root = Path(__file__).resolve().parent
    candidates = [root / "slides", root.parent / "src" / "slides"]
    for path in candidates:
        if path.exists():
            return path.resolve()
    return candidates[0].resolve()


def main():
    app = QApplication(sys.argv)

    default_settings = AppSettings(image_folder=str(_default_slides_dir()))
    settings = load_settings(AppSettings, default_settings)

    slideshow = MultiDisplaySlideShow(settings)
    mainwin = MainWindow(settings, slideshow)
    mainwin.show()

    ret = app.exec()
    save_settings(mainwin.settings)
    sys.exit(ret)


if __name__ == "__main__":
    main()
