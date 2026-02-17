from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class Cue:
    start_ms: int
    end_ms: int
    text: str


def _parse_time_ms(t: str) -> int:
    # "00:00:05,123"
    hh, mm, rest = t.split(":")
    ss, ms = rest.split(",")
    return (int(hh) * 3600 + int(mm) * 60 + int(ss)) * 1000 + int(ms)


def load_srt(path: str) -> List[Cue]:
    p = Path(path)
    if not path or not p.exists():
        return []

    content = p.read_text(encoding="utf-8", errors="ignore")
    blocks = [b.strip() for b in content.split("\n\n") if b.strip()]
    cues: List[Cue] = []

    for b in blocks:
        lines = [l.rstrip("\r") for l in b.splitlines()]
        if len(lines) < 2:
            continue

        # 첫 줄이 index일 수도 있고 아닐 수도 있음
        time_line = lines[1] if "-->" in lines[1] else lines[0]
        if "-->" not in time_line:
            continue

        left, right = [x.strip() for x in time_line.split("-->")]
        try:
            s = _parse_time_ms(left)
            e = _parse_time_ms(right.split()[0])
        except Exception:
            continue

        # 텍스트는 time_line 다음 줄부터
        if "-->" in lines[0]:
            text_lines = lines[1:]
        else:
            text_lines = lines[2:]

        text = "\n".join(text_lines).strip()
        if text:
            cues.append(Cue(s, e, text))

    cues.sort(key=lambda c: c.start_ms)
    return cues


def find_cue(cues: List[Cue], t_ms: int) -> Optional[Cue]:
    # 단순 선형 탐색(길어지면 이진탐색으로 바꾸면 됨)
    for c in cues:
        if c.start_ms <= t_ms <= c.end_ms:
            return c
    return None
