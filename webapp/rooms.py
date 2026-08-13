"""방(room) 스코프 서비스 레이어.

seatshuffle의 순수 로직(model, shuffler, roster, history)은 전혀 수정하지 않고
그대로 불러 쓴다 — 여기서 하는 일은 그 함수들이 필요로 하는 데이터를
방 단위로 Postgres에서 읽고 쓰는 것뿐이다.
"""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from typing import Any

import psycopg

from seatshuffle import history as history_mod
from seatshuffle import roster as roster_mod
from seatshuffle.model import Layout, Seat, Student
from seatshuffle.shuffler import Forbidden

from . import config
from .db import immediate_transaction
from .files import tempfile_scope

_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # 0/O/1/I/L처럼 헷갈리는 글자 제외


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --- 방 ----------------------------------------------------------------


def generate_room_code(length: int = config.ROOM_CODE_LENGTH) -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(length))


def create_room(conn: psycopg.Connection) -> str:
    for _ in range(10):
        code = generate_room_code()
        now = _now()
        try:
            with immediate_transaction(conn):
                conn.execute(
                    "INSERT INTO rooms"
                    " (code, columns_json, lookback, active_round_id, created_at, updated_at)"
                    " VALUES (%s, %s, 1, NULL, %s, %s)",
                    (code, json.dumps(config.DEFAULT_LAYOUT), now, now),
                )
            return code
        except psycopg.errors.UniqueViolation:
            continue  # 코드 충돌 — 다시 뽑는다 (실제로는 거의 없음)
    raise RuntimeError("방 코드를 생성하지 못했습니다. 다시 시도해주세요.")


def get_room(conn: psycopg.Connection, code: str) -> dict[str, Any] | None:
    return conn.execute("SELECT * FROM rooms WHERE code = %s", (code,)).fetchone()


def get_layout(room_row: dict[str, Any]) -> Layout:
    return [int(n) for n in json.loads(room_row["columns_json"])]


def set_layout(conn: psycopg.Connection, room_id: int, counts: Layout) -> None:
    """`_parse_layout`과 동일한 범위 검증. 잘못되면 ValueError(사용자에게 보일 메시지)."""
    if not (config.MIN_COLS <= len(counts) <= config.MAX_COLS):
        raise ValueError(f"열 수는 {config.MIN_COLS}~{config.MAX_COLS} 사이로 입력해주세요.")
    for i, n in enumerate(counts, start=1):
        if not (config.MIN_ROWS <= n <= config.MAX_ROWS):
            raise ValueError(
                f"{i}열의 행 수는 {config.MIN_ROWS}~{config.MAX_ROWS} 사이로 입력해주세요."
            )
    now = _now()
    with immediate_transaction(conn, room_id):
        conn.execute(
            "UPDATE rooms SET columns_json = %s, active_round_id = NULL, updated_at = %s"
            " WHERE id = %s",
            (json.dumps(counts), now, room_id),
        )


def set_lookback(conn: psycopg.Connection, room_id: int, lookback: int) -> None:
    lookback = max(0, min(lookback, config.MAX_LOOKBACK))
    with immediate_transaction(conn, room_id):
        conn.execute(
            "UPDATE rooms SET lookback = %s, updated_at = %s WHERE id = %s",
            (lookback, _now(), room_id),
        )


# --- 명단 ----------------------------------------------------------------


def list_students(conn: psycopg.Connection, room_id: int) -> list[dict[str, Any]]:
    """id/name/number를 담은 행 목록 (화면에서 삭제 버튼에 id가 필요)."""
    return conn.execute(
        "SELECT id, name, number FROM students WHERE room_id = %s ORDER BY position",
        (room_id,),
    ).fetchall()


def as_students(rows: list[dict[str, Any]]) -> list[Student]:
    return [Student(row["name"], row["number"]) for row in rows]


def _touch_and_invalidate(conn: psycopg.Connection, room_id: int) -> None:
    """명단/교실이 바뀌면 현재 화면의 배정만 지운다 (이력은 그대로 남긴다)."""
    conn.execute(
        "UPDATE rooms SET active_round_id = NULL, updated_at = %s WHERE id = %s",
        (_now(), room_id),
    )


def add_students_from_lines(
    conn: psycopg.Connection, room_id: int, lines: list[str]
) -> tuple[int, list[str]]:
    """붙여넣은 줄들을 `roster.parse_name_line`으로 해석해 추가한다."""
    added = 0
    now = _now()
    with immediate_transaction(conn, room_id):
        row = conn.execute(
            "SELECT COALESCE(MAX(position), 0) AS maxpos FROM students WHERE room_id = %s",
            (room_id,),
        ).fetchone()
        next_pos = row["maxpos"] + 1
        for line in lines:
            student = roster_mod.parse_name_line(line)
            if student is None:
                continue
            conn.execute(
                "INSERT INTO students (room_id, name, number, position, created_at)"
                " VALUES (%s, %s, %s, %s, %s)",
                (room_id, student.name, student.number, next_pos, now),
            )
            next_pos += 1
            added += 1
        if added:
            _touch_and_invalidate(conn, room_id)

    warnings: list[str] = []
    if added:
        warnings = roster_mod.duplicate_warnings(as_students(list_students(conn, room_id)))
    return added, warnings


def delete_student(conn: psycopg.Connection, room_id: int, student_id: int) -> None:
    with immediate_transaction(conn, room_id):
        conn.execute(
            "DELETE FROM students WHERE id = %s AND room_id = %s", (student_id, room_id)
        )
        _touch_and_invalidate(conn, room_id)


def clear_students(conn: psycopg.Connection, room_id: int) -> None:
    with immediate_transaction(conn, room_id):
        conn.execute("DELETE FROM students WHERE room_id = %s", (room_id,))
        _touch_and_invalidate(conn, room_id)


def import_csv(conn: psycopg.Connection, room_id: int, file_storage) -> list[str]:
    """CSV를 불러와 명단을 통째로 교체한다 (append 아님 — `_on_load_csv`와 동일)."""
    with tempfile_scope(".csv") as tmp_path:
        file_storage.save(tmp_path)
        students, warnings = roster_mod.load_roster(tmp_path)

    now = _now()
    with immediate_transaction(conn, room_id):
        conn.execute("DELETE FROM students WHERE room_id = %s", (room_id,))
        for position, student in enumerate(students, start=1):
            conn.execute(
                "INSERT INTO students (room_id, name, number, position, created_at)"
                " VALUES (%s, %s, %s, %s, %s)",
                (room_id, student.name, student.number, position, now),
            )
        _touch_and_invalidate(conn, room_id)
    return warnings


# --- 이력 / 배정 -----------------------------------------------------------


def load_room_history_dict(conn: psycopg.Connection, room_id: int) -> dict:
    """`history.load_history()`가 돌려주는 것과 동일한 모양으로 재구성한다."""
    rows = conn.execute(
        "SELECT created_at AS at, columns_json, seats_json"
        " FROM rounds WHERE room_id = %s ORDER BY round_no",
        (room_id,),
    ).fetchall()
    rounds = []
    for row in rows:
        columns = json.loads(row["columns_json"])
        rounds.append(
            {
                "at": row["at"],
                "cols": len(columns),
                "columns": columns,
                "seats": json.loads(row["seats_json"]),
            }
        )
    return {"rounds": rounds}


def forbidden_seats_for_room(
    conn: psycopg.Connection, room_id: int, lookback: int
) -> Forbidden:
    return history_mod.forbidden_seats(load_room_history_dict(conn, room_id), lookback)


def save_round(
    conn: psycopg.Connection,
    room_id: int,
    seating: dict[Student, Seat],
    counts: Layout,
) -> int:
    now = _now()
    with immediate_transaction(conn, room_id):
        row = conn.execute(
            "SELECT COALESCE(MAX(round_no), 0) AS maxno FROM rounds WHERE room_id = %s",
            (room_id,),
        ).fetchone()
        round_no = row["maxno"] + 1
        seats_json = json.dumps(
            {student.name: [seat.row, seat.col] for student, seat in seating.items()}
        )
        cursor = conn.execute(
            "INSERT INTO rounds (room_id, round_no, columns_json, seats_json, created_at)"
            " VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (room_id, round_no, json.dumps(counts), seats_json, now),
        )
        new_round_id = cursor.fetchone()["id"]
        conn.execute(
            "UPDATE rooms SET active_round_id = %s, updated_at = %s WHERE id = %s",
            (new_round_id, now, room_id),
        )
    return round_no


def round_count(conn: psycopg.Connection, room_id: int) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM rounds WHERE room_id = %s", (room_id,)
    ).fetchone()
    return row["n"]


def clear_history(conn: psycopg.Connection, room_id: int) -> None:
    with immediate_transaction(conn, room_id):
        conn.execute("DELETE FROM rounds WHERE room_id = %s", (room_id,))
        _touch_and_invalidate(conn, room_id)


def active_seating(
    conn: psycopg.Connection, room_id: int
) -> tuple[dict[Student, Seat], Layout] | None:
    """현재 화면에 보여줄 배정. 명단/교실을 바꾸면 None이 된다 (이력은 안 지워짐)."""
    room_row = conn.execute(
        "SELECT active_round_id FROM rooms WHERE id = %s", (room_id,)
    ).fetchone()
    if room_row is None or room_row["active_round_id"] is None:
        return None

    round_row = conn.execute(
        "SELECT columns_json, seats_json FROM rounds WHERE id = %s",
        (room_row["active_round_id"],),
    ).fetchone()
    if round_row is None:
        return None

    counts = [int(n) for n in json.loads(round_row["columns_json"])]
    seats = json.loads(round_row["seats_json"])
    seating = {
        Student(name): Seat(int(pos[0]), int(pos[1])) for name, pos in seats.items()
    }
    return seating, counts
