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
