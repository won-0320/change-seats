"""랜딩 페이지: 방 만들기 / 코드로 들어가기."""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from .. import rooms
from ..db import get_db

bp = Blueprint("main", __name__)


@bp.get("/")
def index():
    return render_template("index.html")


@bp.post("/rooms")
def create_room():
    conn = get_db()
    code = rooms.create_room(conn)
    return redirect(url_for("room.show", code=code))


@bp.get("/goto")
def goto():
    code = request.args.get("code", "").strip().upper()
    conn = get_db()
    if code and rooms.get_room(conn, code) is not None:
        return redirect(url_for("room.show", code=code))
    flash("코드를 찾을 수 없어요. 다시 확인해주세요.")
    return redirect(url_for("main.index"))
