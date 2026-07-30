"""배정 이력과 화면 설정을 `data\\` 폴더에 저장한다."""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from .model import Seat, Student, as_layout


def _project_root() -> Path:
    """이력·설정을 둘 곳.

    exe로 묶은 경우(PyInstaller)에는 코드가 임시 폴더에 풀리므로 `__file__` 기준으로
    잡으면 실행할 때마다 설정이 사라진다. 그래서 exe가 놓인 폴더를 기준으로 삼는다.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


PROJECT_ROOT = _project_root()
DATA_DIR = PROJECT_ROOT / "data"
HISTORY_PATH = DATA_DIR / "history.json"
SETTINGS_PATH = DATA_DIR / "settings.json"


def ensure_data_dir() -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR


# --- 배정 이력 ---------------------------------------------------------------


def load_history() -> dict[str, Any]:
    """이력을 읽는다. 파일이 없거나 깨졌으면 빈 이력을 돌려준다."""
    data = _read_json(HISTORY_PATH)
    if not isinstance(data, dict) or not isinstance(data.get("rounds"), list):
        return {"rounds": []}
    return data


def save_round(
    seating: dict[Student, Seat],
    layout: Sequence[int] | int,
    rows: int | None = None,
    history: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """이번 배정을 한 회차로 이력에 추가하고 저장한다.

    `layout`은 열별 행 수 목록([3, 4, 3, 3, 3]) 또는 균일 교실의 (열 수, 행 수).
    """
    counts = as_layout(layout, rows)
    history = history if history is not None else load_history()
    history.setdefault("rounds", []).append(
        {
            "at": datetime.now().isoformat(timespec="seconds"),
            "cols": len(counts),
            "columns": counts,
            "seats": {s.name: [seat.row, seat.col] for s, seat in seating.items()},
        }
    )
    _write_json(HISTORY_PATH, history)
    return history


def forbidden_seats(
    history: dict[str, Any], lookback: int = 1
) -> dict[str, set[tuple[int, int]]]:
    """최근 `lookback` 회차에서 각 학생이 앉았던 좌석을 금지 집합으로 모은다.

    이력에 없는 학생(새로 들어온 학생)은 키가 없으므로 어디든 앉을 수 있다.
    교실 크기가 바뀌었어도 좌표는 그대로 비교한다.
    """
    result: dict[str, set[tuple[int, int]]] = {}
    if lookback <= 0:
        return result

    for entry in history.get("rounds", [])[-lookback:]:
        seats = entry.get("seats") or {}
        if not isinstance(seats, dict):
            continue
        for name, pos in seats.items():
            if isinstance(pos, (list, tuple)) and len(pos) == 2:
                try:
                    result.setdefault(str(name), set()).add((int(pos[0]), int(pos[1])))
                except (TypeError, ValueError):
                    continue
    return result


def round_count(history: dict[str, Any]) -> int:
    rounds = history.get("rounds", [])
    return len(rounds) if isinstance(rounds, list) else 0


def clear_history() -> None:
    if HISTORY_PATH.exists():
        HISTORY_PATH.unlink()


# --- 화면 설정 ---------------------------------------------------------------


def load_settings() -> dict[str, Any]:
    data = _read_json(SETTINGS_PATH)
    return data if isinstance(data, dict) else {}


def save_settings(settings: dict[str, Any]) -> None:
    _write_json(SETTINGS_PATH, settings)


# --- 파일 입출력 -------------------------------------------------------------


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None


def _write_json(path: Path, data: Any) -> None:
    ensure_data_dir()
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
