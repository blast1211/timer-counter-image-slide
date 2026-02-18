import json
import os
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Dict, Type, TypeVar

T = TypeVar("T")
APP_DIR_NAME = "video-making"


def _config_root() -> Path:
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata)
        return Path.home() / "AppData" / "Roaming"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"

    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg)
    return Path.home() / ".config"


def _settings_path() -> Path:
    settings_dir = _config_root() / APP_DIR_NAME
    settings_dir.mkdir(parents=True, exist_ok=True)
    return settings_dir / "settings.json"


def save_settings(obj: Any) -> None:
    p = _settings_path()
    if is_dataclass(obj):
        data = asdict(obj)
    else:
        data = dict(obj.__dict__)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_settings(cls: Type[T], default_obj: T) -> T:
    p = _settings_path()
    if not p.exists():
        return default_obj

    try:
        data: Dict[str, Any] = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default_obj

    out = default_obj
    for k, v in data.items():
        if hasattr(out, k):
            setattr(out, k, v)
    return out
