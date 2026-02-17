import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Dict, Type, TypeVar

T = TypeVar("T")


def _settings_path() -> Path:
    # core/settings_store.py -> 부모(1단계) = 프로젝트 루트(app.py 있는 곳)
    root = Path(__file__).resolve().parents[1]
    return root / "settings.json"


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
