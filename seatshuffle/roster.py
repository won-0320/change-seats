"""명단 CSV 불러오기 / 배정표 CSV 내보내기.

학교에서 쓰는 CSV는 형식이 제각각이라 인코딩과 열 위치를 최대한 유연하게 잡는다.
"""

from __future__ import annotations

import csv
import re
from collections.abc import Sequence
from pathlib import Path

from .model import Seat, Student, as_layout, seating_grid

NAME_HEADERS = {"이름", "성명", "학생", "학생명", "name"}
NUMBER_HEADERS = {"번호", "출석번호", "학번", "no", "no.", "number"}

ENCODINGS = ("utf-8-sig", "cp949")

# "1. 김민준", "1 김민준", "1,김민준" 처럼 번호가 앞에 붙은 한 줄
_NUMBERED_LINE = re.compile(r"^(\d{1,3})\s*[.,)\s]\s*(.+)$")


def load_roster(path: str | Path) -> tuple[list[Student], list[str]]:
    """CSV에서 명단을 읽는다.

    반환: (학생 목록, 사용자에게 보여줄 경고 메시지 목록)
    """
    text = _read_text(Path(path))
    rows = [row for row in csv.reader(text.splitlines()) if any(c.strip() for c in row)]
    if not rows:
        return [], ["파일에서 읽을 내용을 찾지 못했어요."]

    name_idx, number_idx, has_header = _pick_columns(rows)
    body = rows[1:] if has_header else rows

    students: list[Student] = []
    warnings: list[str] = []
    skipped = 0

    for row in body:
        name = row[name_idx].strip() if name_idx < len(row) else ""
        if not name:
            skipped += 1
            continue
        number = None
        if number_idx is not None and number_idx < len(row):
            raw = row[number_idx].strip()
            if raw.isdigit():
                number = int(raw)
        students.append(Student(name, number))

    if skipped:
        warnings.append(f"이름이 비어 있는 줄 {skipped}개를 건너뛰었어요.")
    warnings.extend(duplicate_warnings(students))
    return students, warnings


def duplicate_warnings(students: list[Student]) -> list[str]:
    """동명이인 경고. 이력이 이름 기준이므로 이름이 겹치면 구분이 필요하다."""
    seen: dict[str, int] = {}
    for s in students:
        seen[s.name] = seen.get(s.name, 0) + 1
    dupes = [name for name, count in seen.items() if count > 1]
    if not dupes:
        return []
    return [
        "이름이 겹치는 학생이 있어요: "
        + ", ".join(dupes)
        + "\n지난 자리 회피는 이름을 기준으로 하니 '김민준2'처럼 구분해주세요."
    ]


def parse_name_line(line: str) -> Student | None:
    """붙여넣은 한 줄을 학생 한 명으로 해석한다. 빈 줄이면 None."""
    line = line.strip()
    if not line:
        return None
    match = _NUMBERED_LINE.match(line)
    if match:
        return Student(match.group(2).strip(), int(match.group(1)))
    return Student(line)


def export_seating(
    path: str | Path,
    seating: dict[Student, Seat],
    layout: Sequence[int] | int,
    rows: int | None = None,
) -> None:
    """배정표를 엑셀에서 바로 열리는 CSV로 저장한다.

    열마다 행 수가 다르면 짧은 열의 뒷자리는 빈칸으로 둔다.
    """
    counts = as_layout(layout, rows)
    grid = seating_grid(seating, counts)
    with Path(path).open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["행"] + [f"{c}열" for c in range(1, len(counts) + 1)])
        for row_no, line in enumerate(grid, start=1):
            writer.writerow([f"{row_no}행"] + [s.name if s else "" for s in line])


def _read_text(path: Path) -> str:
    last_error: Exception | None = None
    for encoding in ENCODINGS:
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
    raise UnicodeDecodeError(
        "csv", b"", 0, 1, f"UTF-8 또는 CP949로 읽을 수 없는 파일입니다: {path.name}"
    ) from last_error


def _pick_columns(rows: list[list[str]]) -> tuple[int, int | None, bool]:
    """(이름 열, 번호 열 또는 None, 첫 줄이 헤더인지)를 판정한다."""
    header = [cell.strip().lower() for cell in rows[0]]

    name_idx: int | None = None
    number_idx: int | None = None
    for i, cell in enumerate(header):
        if name_idx is None and cell in NAME_HEADERS:
            name_idx = i
        if number_idx is None and cell in NUMBER_HEADERS:
            number_idx = i

    if name_idx is not None or number_idx is not None:
        if name_idx is None:
            # 번호 열만 알아봤다면 그 외의 첫 열을 이름으로 본다.
            name_idx = next(
                (i for i in range(len(header)) if i != number_idx), 0
            )
        return name_idx, number_idx, True

    # 헤더가 없는 파일. 첫 열이 전부 숫자면 번호 열로 본다.
    first_cells = [row[0].strip() for row in rows if row and row[0].strip()]
    if len(header) >= 2 and first_cells and all(c.isdigit() for c in first_cells):
        return 1, 0, False
    return 0, None, False
