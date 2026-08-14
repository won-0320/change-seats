"""좌석과 학생을 표현하는 데이터 모델.

교실은 "열별 행 수 목록"(layout)으로 표현한다. 예: [3, 4, 3, 3, 3] = 5열 16칸.
1열은 3행 깊이, 2열만 4행 깊이(뒤에 한 자리 더), 3~5열은 3행 깊이라는 뜻이다.
열마다 줄 길이가 다른 교실을 그대로 담을 수 있고, 균일한 교실도 특별한 경우로 포함된다.

좌석 좌표는 `Seat(row, col)`:
  row = 칠판에서 몇 번째 줄인지 (1 = 가장 앞)
  col = 왼쪽에서 몇 번째 줄인지 (1 = 가장 왼쪽)
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

# 열별 행 수. 예: [3, 4, 3, 3, 3] → 2열만 4행 깊이
Layout = list[int]


@dataclass(frozen=True)
class Seat:
    """교실의 한 좌석.

    row: 1부터. 1 = 칠판에서 가장 가까운 줄
    col: 1부터. 1 = 가장 왼쪽 줄
    """

    row: int
    col: int

    def as_tuple(self) -> tuple[int, int]:
        return (self.row, self.col)

    def label(self) -> str:
        return f"{self.col}열 {self.row}행"


@dataclass(frozen=True)
class Student:
    """학생 한 명. 이력 비교의 기준은 이름이다."""

    name: str
    number: int | None = None

    def display(self) -> str:
        if self.number is None:
            return self.name
        return f"{self.number}. {self.name}"


def as_layout(layout: Sequence[int] | int, rows: int | None = None) -> Layout:
    """열별 행 수 목록으로 정규화한다.

    as_layout([3, 4, 3, 3, 3])  → 열마다 행 수가 다른 교실 (5열 16칸)
    as_layout(5, 4)             → 5열 × 4행 균일 교실
    """
    if isinstance(layout, int):
        if rows is None:
            raise ValueError("균일한 교실은 (열 수, 행 수) 두 값으로 지정하세요.")
        counts = [rows] * layout
    else:
        counts = [int(n) for n in layout]

    if not counts:
        raise ValueError("열이 최소 하나는 있어야 합니다.")
    if any(n < 1 for n in counts):
        raise ValueError("각 열의 행 수는 1 이상이어야 합니다.")
    return counts


def build_seats(layout: Sequence[int] | int, rows: int | None = None) -> list[Seat]:
    """열 왼쪽부터, 각 열은 앞줄부터 순서로 좌석 목록을 만든다."""
    counts = as_layout(layout, rows)
    return [
        Seat(row, col)
        for col, depth in enumerate(counts, start=1)
        for row in range(1, depth + 1)
    ]


def seat_total(layout: Sequence[int] | int, rows: int | None = None) -> int:
    """교실의 총 좌석 수."""
    return sum(as_layout(layout, rows))


def layout_depth(layout: Sequence[int] | int, rows: int | None = None) -> int:
    """가장 깊은 열의 행 수 (= 교실 전체 행 수)."""
    return max(as_layout(layout, rows))


def seat_exists(layout: Sequence[int] | int, row: int, col: int) -> bool:
    """그 자리에 책상이 있는지. 짧은 열의 뒤쪽은 자리가 없다."""
    counts = as_layout(layout)
    return 1 <= col <= len(counts) and 1 <= row <= counts[col - 1]


def seating_grid(
    seating: dict[Student, Seat],
    layout: Sequence[int] | int,
    rows: int | None = None,
) -> list[list[Student | None]]:
    """{학생: 좌석} 배정을 [행][열] 직사각형 격자로 뒤집는다.

    책상이 없는 자리와 비어 있는 자리 모두 None이다.
    구분이 필요하면 `seat_exists()`를 함께 쓴다.
    """
    counts = as_layout(layout, rows)
    depth = max(counts)
    grid: list[list[Student | None]] = [[None] * len(counts) for _ in range(depth)]
    for student, seat in seating.items():
        if seat_exists(counts, seat.row, seat.col):
            grid[seat.row - 1][seat.col - 1] = student
    return grid


def describe_layout(layout: Sequence[int] | int, rows: int | None = None) -> str:
    """'5열 · 3·4·3·3·3행 · 16칸' 처럼 사람이 읽는 문장."""
    counts = as_layout(layout, rows)
    pattern = "·".join(str(n) for n in counts)
    return f"{len(counts)}열 · {pattern}행 · {sum(counts)}칸"


# --- 그룹(열) 단위 레이아웃 --------------------------------------------------
#
# 위의 Layout/Seat/build_seats/seat_exists/seating_grid는 "물리 좌석 열" 단위로만
# 동작한다 (셔플·이력 로직이 이 좌표를 그대로 쓰므로 건드리지 않는다).
# 짝꿍(한 열에 좌석 2개가 간격 없이 붙는 것) 기능은 그 위에 얇게 얹는다:
# 그룹 레이아웃(ColumnSpec 목록, 사용자가 보는 "열")을 물리 Layout으로
# 펼친(expand) 뒤에야 기존 함수들에 넘긴다.


@dataclass(frozen=True)
class ColumnSpec:
    """한 '열'(그룹). depth = 행 수, width = 1(홑자리) 또는 2(짝꿍, 붙어 앉음)."""

    depth: int
    width: int = 1


GroupedLayout = list[ColumnSpec]


def as_grouped_layout(
    raw: "Sequence[object] | int", rows: int | None = None
) -> GroupedLayout:
    """그룹 레이아웃으로 정규화한다.

    각 원소는 다음 중 하나일 수 있다:
      int              → 홑자리 열 (width=1) — 옛 columns_json([3,4,3,3,3]) 호환
      [depth, width]   → 짝꿍 여부를 담은 열
      ColumnSpec       → 그대로 사용
    as_grouped_layout(5, 4)는 as_layout(5, 4)처럼 5열 × 4행 균일 교실(전부 홑자리).
    """
    if isinstance(raw, int):
        if rows is None:
            raise ValueError("균일한 교실은 (열 수, 행 수) 두 값으로 지정하세요.")
        grouped = [ColumnSpec(depth=rows, width=1) for _ in range(raw)]
    else:
        grouped = []
        for item in raw:
            if isinstance(item, ColumnSpec):
                grouped.append(item)
            elif isinstance(item, (list, tuple)):
                if len(item) != 2:
                    raise ValueError("열 설정은 [행 수, 너비] 형태여야 합니다.")
                depth, width = item
                grouped.append(ColumnSpec(depth=int(depth), width=int(width)))
            else:
                grouped.append(ColumnSpec(depth=int(item), width=1))

    if not grouped:
        raise ValueError("열이 최소 하나는 있어야 합니다.")
    for spec in grouped:
        if spec.depth < 1:
            raise ValueError("각 열의 행 수는 1 이상이어야 합니다.")
        if spec.width not in (1, 2):
            raise ValueError("각 열의 너비는 1(홑자리) 또는 2(짝꿍)여야 합니다.")
    return grouped


def expand_columns(grouped: GroupedLayout) -> Layout:
    """그룹 레이아웃을 물리 열 단위 Layout으로 펼친다.

    build_seats/seat_exists/seating_grid 등 기존 물리 좌석 로직으로 들어가는
    유일한 통로 — 폭 2인 열은 같은 depth를 가진 물리 열 2개로 펼쳐진다.
    """
    return [spec.depth for spec in grouped for _ in range(spec.width)]


def group_spans(grouped: GroupedLayout) -> list[tuple[int, int]]:
    """그룹별 물리 열 범위 (start, end), 1부터 시작, 양끝 포함.

    예: widths [1, 2, 1] → [(1, 1), (2, 3), (4, 4)]
    """
    spans = []
    col = 1
    for spec in grouped:
        spans.append((col, col + spec.width - 1))
        col += spec.width
    return spans


def describe_grouped_layout(grouped: GroupedLayout) -> str:
    """'5열 · 3·4·3·3·3행 · 18칸' 처럼 사람이 읽는 문장 (짝꿍 열은 좌석 2배로 집계)."""
    pattern = "·".join(str(spec.depth) for spec in grouped)
    total = sum(spec.depth * spec.width for spec in grouped)
    return f"{len(grouped)}열 · {pattern}행 · {total}칸"
