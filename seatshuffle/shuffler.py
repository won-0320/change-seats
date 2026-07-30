"""자리 배정 알고리즘.

기본은 순수 무작위 셔플이고, "지난 회차와 같은 좌석"만 금지 조건으로 걸린다.
GUI 없이 단독으로 테스트할 수 있게 tkinter에 의존하지 않는다.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from .model import Seat, Student

DEFAULT_MAX_ATTEMPTS = 300
MAX_BACKTRACK_NODES = 20_000

# {학생 이름: {(행, 열), ...}} — 그 학생이 앉을 수 없는 좌석
Forbidden = dict[str, set[tuple[int, int]]]

_NO_SEATS: frozenset[tuple[int, int]] = frozenset()


@dataclass
class AssignResult:
    """배정 결과와 어떻게 찾았는지에 대한 정보."""

    seating: dict[Student, Seat] | None
    attempts: int = 0
    method: str = ""  # "shuffle" | "backtrack" | "" (실패)

    @property
    def ok(self) -> bool:
        return self.seating is not None

    def describe(self) -> str:
        if not self.ok:
            return "배정 실패"
        if self.method == "backtrack":
            return f"셔플 {self.attempts}회 실패 후 순서 조합으로 배정"
        return f"시도 {self.attempts}회"


def assign_detailed(
    students: list[Student],
    seats: list[Seat],
    forbidden: Forbidden | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    rng: random.Random | None = None,
) -> AssignResult:
    """학생을 좌석에 무작위 배정한다. 금지 좌석을 모두 피한 결과만 돌려준다."""
    if len(students) != len(seats):
        raise ValueError(
            f"학생 수({len(students)})와 좌석 수({len(seats)})가 다릅니다."
        )

    rng = rng or random.Random()
    forbidden = forbidden or {}

    # 1단계: 순수 셔플 후 검증. 금지 좌석이 적은 정상적인 경우 거의 즉시 통과한다.
    order = list(students)
    for attempt in range(1, max_attempts + 1):
        rng.shuffle(order)
        if _is_valid(order, seats, forbidden):
            return AssignResult(dict(zip(order, seats)), attempt, "shuffle")

    # 2단계: 셔플로 못 찾았을 때만. 해가 있으면 찾아낸다.
    seating = _backtracking_assign(students, seats, forbidden, rng)
    if seating is not None:
        return AssignResult(seating, max_attempts, "backtrack")

    return AssignResult(None, max_attempts, "")


def assign(
    students: list[Student],
    seats: list[Seat],
    forbidden: Forbidden | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    rng: random.Random | None = None,
) -> dict[Student, Seat] | None:
    """`assign_detailed()`의 얇은 래퍼. 성공하면 {학생: 좌석}, 실패하면 None."""
    return assign_detailed(students, seats, forbidden, max_attempts, rng).seating


def _is_valid(
    order: list[Student], seats: list[Seat], forbidden: Forbidden
) -> bool:
    for student, seat in zip(order, seats):
        if seat.as_tuple() in forbidden.get(student.name, _NO_SEATS):
            return False
    return True


def _backtracking_assign(
    students: list[Student],
    seats: list[Seat],
    forbidden: Forbidden,
    rng: random.Random,
) -> dict[Student, Seat] | None:
    """좌석마다 후보가 가장 적은 곳부터 채우는 백트래킹.

    무작위성을 잃지 않으려고 좌석 순서와 후보 순서를 모두 섞어서 탐색한다.
    """
    pool = list(students)
    rng.shuffle(pool)
    seat_order = list(seats)
    rng.shuffle(seat_order)

    placed: dict[Seat, Student] = {}
    nodes = 0

    def allowed(student: Student, seat: Seat) -> bool:
        return seat.as_tuple() not in forbidden.get(student.name, _NO_SEATS)

    def solve(open_seats: list[Seat]) -> bool:
        nonlocal nodes
        if not open_seats:
            return True

        # 후보가 가장 적은 좌석을 먼저 정한다 (막다른 길을 빨리 발견).
        target_idx = 0
        candidates: list[Student] | None = None
        for i, seat in enumerate(open_seats):
            seat_candidates = [s for s in pool if allowed(s, seat)]
            if not seat_candidates:
                return False
            if candidates is None or len(seat_candidates) < len(candidates):
                target_idx, candidates = i, seat_candidates
                if len(seat_candidates) == 1:
                    break

        seat = open_seats[target_idx]
        rest = open_seats[:target_idx] + open_seats[target_idx + 1 :]
        assert candidates is not None
        rng.shuffle(candidates)

        for student in candidates:
            nodes += 1
            if nodes > MAX_BACKTRACK_NODES:
                return False
            placed[seat] = student
            pool.remove(student)
            if solve(rest):
                return True
            pool.append(student)
            del placed[seat]
        return False

    if solve(seat_order):
        return {student: seat for seat, student in placed.items()}
    return None
