import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from models.settings import AppSettings
from core.multi_display_slideshow import MultiDisplaySlideShow
from ui.main_window import MainWindow

from core.settings_store import load_settings, save_settings  # 추가

def main():
    app = QApplication(sys.argv)

    root = Path(__file__).resolve().parent
    slides = (root / "slides").resolve()

    default_settings = AppSettings(image_folder=str(slides))
    settings = load_settings(AppSettings, default_settings)


    slideshow = MultiDisplaySlideShow(settings)
    mainwin = MainWindow(settings, slideshow)
    mainwin.show()

    ret = app.exec()
    save_settings(mainwin.settings)  # 또는 settings
    sys.exit(ret)

if __name__ == "__main__":
    main()
