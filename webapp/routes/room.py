"""방 하나(반 하나)의 명단·교실·배정 화면.

`before_request`에서 코드로 방을 찾아 `g.room`에 담는다 — 이 지점이 방 간
격리 경계이며, 아래 모든 핸들러는 오직 `g.room["id"]`로만 데이터에 접근한다.
"""

from __future__ import annotations

import random
from datetime import date
from urllib.parse import quote

from flask import (
    Blueprint,
    Response,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
)

from seatshuffle import render as render_mod
from seatshuffle import roster as roster_mod
from seatshuffle.model import build_seats, describe_layout, seat_exists, seating_grid
from seatshuffle.shuffler import assign_detailed

from .. import config, rooms
from ..db import get_db
from ..files import tempfile_scope

bp = Blueprint("room", __name__, url_prefix="/r/<code>")


@bp.url_value_preprocessor
def _pull_code(_endpoint, values):
    g.room_code = values.pop("code")


@bp.before_request
def _load_room():
    conn = get_db()
    room = rooms.get_room(conn, g.room_code)
    if room is None:
        abort(404)
    g.room = room


def _redirect_to_room():
    return redirect(url_for("room.show", code=g.room_code))


def _content_disposition(filename: str, ascii_fallback: str) -> str:
    """한글 파일명은 HTTP 헤더에 그대로 못 넣으므로 RFC 5987 형식을 함께 준다."""
    return (
        f'attachment; filename="{ascii_fallback}"; '
        f"filename*=UTF-8''{quote(filename)}"
    )


def _seatcount_message(counts: list[int], student_count: int) -> tuple[str, bool]:
    total = sum(counts)
    pattern = "·".join(str(n) for n in counts)
    base = f"{pattern} = {total}칸 · 명단 {student_count}명"
    if total == student_count:
        return base + " (딱 맞음)", True
    gap = abs(total - student_count)
    tail = f"{gap}칸이 남음" if total > student_count else f"{gap}명이 남음"
    return f"{base} ({tail})", False


# --- 화면 ------------------------------------------------------------------


@bp.get("")
def show():
    conn = get_db()
    room = g.room
    student_rows = rooms.list_students(conn, room["id"])
    counts = rooms.get_layout(room)
    seatcount_msg, seatcount_ok = _seatcount_message(counts, len(student_rows))

    active = rooms.active_seating(conn, room["id"])
    grid = None
    if active is not None:
        seating, active_counts = active
        grid = seating_grid(seating, active_counts)

    return render_template(
        "room.html",
        room=room,
        code=g.room_code,
        students=student_rows,
        counts=counts,
        seatcount_msg=seatcount_msg,
        seatcount_ok=seatcount_ok,
        grid=grid,
        grid_counts=active[1] if active is not None else None,
        round_count=rooms.round_count(conn, room["id"]),
        seat_exists=seat_exists,
        describe_layout=describe_layout,
        min_cols=config.MIN_COLS,
        max_cols=config.MAX_COLS,
        min_rows=config.MIN_ROWS,
        max_rows=config.MAX_ROWS,
        max_lookback=config.MAX_LOOKBACK,
    )


# --- 명단 --------------------------------------------------------------


@bp.post("/students")
def add_student():
    conn = get_db()
    name = request.form.get("name", "").strip()
    number = request.form.get("number", "").strip()
    if not name:
        flash("이름을 입력해주세요.")
        return _redirect_to_room()

    line = f"{number}. {name}" if number else name
    added, warnings = rooms.add_students_from_lines(conn, g.room["id"], [line])
    if added:
        flash(f"{added}명 추가")
    for warning in warnings:
        flash(warning)
    return _redirect_to_room()


@bp.post("/students/bulk")
def add_students_bulk():
    conn = get_db()
    text = request.form.get("lines", "")
    added, warnings = rooms.add_students_from_lines(conn, g.room["id"], text.splitlines())
    flash(f"{added}명 추가" if added else "추가된 학생이 없어요.")
    for warning in warnings:
        flash(warning)
    return _redirect_to_room()


@bp.post("/students/<int:student_id>/delete")
def delete_student(student_id: int):
    conn = get_db()
    rooms.delete_student(conn, g.room["id"], student_id)
    flash("삭제했어요.")
    return _redirect_to_room()


@bp.post("/students/clear")
def clear_students():
    conn = get_db()
    rooms.clear_students(conn, g.room["id"])
    flash("명단을 비웠습니다.")
    return _redirect_to_room()


@bp.post("/students/import")
def import_students():
    conn = get_db()
    file = request.files.get("file")
    if file is None or not file.filename:
        flash("CSV 파일을 선택해주세요.")
        return _redirect_to_room()
    try:
        warnings = rooms.import_csv(conn, g.room["id"], file)
    except (OSError, UnicodeDecodeError) as exc:
        flash(f"파일을 읽을 수 없어요: {exc}")
        return _redirect_to_room()

    flash(f"{file.filename} 에서 명단을 불러왔어요.")
    for warning in warnings:
        flash(warning)
    return _redirect_to_room()


# --- 교실 설정 ----------------------------------------------------------


@bp.post("/settings")
def update_settings():
    conn = get_db()

    cols_text = request.form.get("cols", "").strip()
    if not cols_text.isdigit():
        flash("열 수를 숫자로 입력해주세요.")
        return _redirect_to_room()
    cols = int(cols_text)
    if not (config.MIN_COLS <= cols <= config.MAX_COLS):
        flash(f"열 수는 {config.MIN_COLS}~{config.MAX_COLS} 사이로 입력해주세요.")
        return _redirect_to_room()

    counts: list[int] = []
    for i in range(1, cols + 1):
        value = request.form.get(f"row_{i}", "").strip()
        if not value.isdigit():
            flash(f"{i}열의 행 수를 숫자로 입력해주세요.")
            return _redirect_to_room()
        counts.append(int(value))

    try:
        rooms.set_layout(conn, g.room["id"], counts)
    except ValueError as exc:
        flash(str(exc))
        return _redirect_to_room()

    lookback_text = request.form.get("lookback", "0").strip()
    lookback = int(lookback_text) if lookback_text.isdigit() else 0
    rooms.set_lookback(conn, g.room["id"], lookback)

    flash("교실 설정을 저장했어요.")
    return _redirect_to_room()


# --- 배정 ----------------------------------------------------------------


@bp.post("/shuffle")
def shuffle():
    conn = get_db()
    room = g.room
    counts = rooms.get_layout(room)
    students = rooms.as_students(rooms.list_students(conn, room["id"]))
    total = sum(counts)

    if len(students) != total:
        flash(
            f"학생은 {len(students)}명인데 좌석은 {total}칸입니다. "
            f"({describe_layout(counts)}) 열별 행 수를 조정하거나 명단을 확인해주세요."
        )
        return _redirect_to_room()

    lookback = room["lookback"]
    forbidden = rooms.forbidden_seats_for_room(conn, room["id"], lookback)
    result = assign_detailed(students, build_seats(counts), forbidden, rng=random.Random())

    if not result.ok:
        flash(
            "지난 자리를 모두 피하는 배정을 찾지 못했어요. "
            "'회피할 회차 수'를 줄이거나 교실 크기를 늘려보세요."
        )
        return _redirect_to_room()

    round_no = rooms.save_round(conn, room["id"], result.seating, counts)
    avoid_note = "회피 없음" if lookback == 0 else f"최근 {lookback}회차 회피"
    flash(f"배정 완료 · {result.describe()} · {round_no}회차 ({avoid_note})")
    return _redirect_to_room()


@bp.post("/history/clear")
def clear_history():
    conn = get_db()
    rooms.clear_history(conn, g.room["id"])
    flash("배정 이력을 초기화했습니다.")
    return _redirect_to_room()


# --- 내보내기 / 인쇄 -------------------------------------------------------


@bp.get("/export.csv")
def export_csv():
    conn = get_db()
    active = rooms.active_seating(conn, g.room["id"])
    if active is None:
        flash("먼저 배정해주세요.")
        return _redirect_to_room()
    seating, counts = active
    with tempfile_scope(".csv") as tmp_path:
        roster_mod.export_seating(tmp_path, seating, counts)
        data = tmp_path.read_bytes()
    filename = f"자리배정_{date.today().isoformat()}.csv"
    return Response(
        data,
        mimetype="text/csv",
        headers={"Content-Disposition": _content_disposition(filename, "seating.csv")},
    )


def _render_active_png() -> bytes | None:
    conn = get_db()
    active = rooms.active_seating(conn, g.room["id"])
    if active is None:
        return None
    seating, counts = active
    round_no = rooms.round_count(conn, g.room["id"])
    with tempfile_scope(".png") as tmp_path:
        render_mod.render_png(seating, counts, path=tmp_path, round_no=round_no)
        return tmp_path.read_bytes()


@bp.get("/export.png")
def export_png():
    data = _render_active_png()
    if data is None:
        flash("먼저 배정해주세요.")
        return _redirect_to_room()
    filename = f"자리배치_{date.today().isoformat()}.png"
    return Response(
        data,
        mimetype="image/png",
        headers={"Content-Disposition": _content_disposition(filename, "seating.png")},
    )


@bp.get("/print.png")
def print_png():
    data = _render_active_png()
    if data is None:
        abort(404)
    return Response(data, mimetype="image/png")


@bp.get("/print")
def print_page():
    conn = get_db()
    if rooms.active_seating(conn, g.room["id"]) is None:
        flash("먼저 배정해주세요.")
        return _redirect_to_room()
    return render_template("print.html", code=g.room_code)
