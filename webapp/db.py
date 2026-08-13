"""방(room)별 데이터를 담는 Postgres 연결 관리 (Vercel Postgres/Neon).

서버리스 함수는 요청마다(또는 인스턴스마다) 새로 뜰 수 있으므로 로컬 디스크에
의존할 수 없다 — 그래서 SQLite 대신 클라우드 Postgres에 붙는다. 커넥션 수
폭증을 피하려면 반드시 풀링된 연결 문자열(`POSTGRES_URL`)을 써야 한다.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import psycopg
from flask import Flask, current_app, g
from psycopg.rows import dict_row

_SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def get_db() -> psycopg.Connection:
    """요청 단위로 재사용되는 연결. `flask.g`에 캐싱한다."""
    if "db" not in g:
        g.db = psycopg.connect(
            current_app.config["DATABASE_URL"], row_factory=dict_row
        )
    return g.db


def close_db(_exc: BaseException | None = None) -> None:
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_db(database_url: str) -> None:
    """스키마를 (없으면) 적용한다. 여러 번 불러도 안전하다."""
    statements = [
        stmt.strip()
        for stmt in _SCHEMA_PATH.read_text(encoding="utf-8").split(";")
        if stmt.strip()
    ]
    with psycopg.connect(database_url, autocommit=True) as conn:
        for statement in statements:
            conn.execute(statement)


def init_app(app: Flask) -> None:
    app.teardown_appcontext(close_db)
    init_db(app.config["DATABASE_URL"])


@contextmanager
def immediate_transaction(
    conn: psycopg.Connection, room_id: int | None = None
) -> Iterator[None]:
    """읽고-고쳐-쓰는 구간을 방(room) 단위 잠금으로 감싼다.

    두 요청이 동시에 같은 방에서 "다음 회차 번호" 같은 값을 읽고 둘 다 같은
    값으로 저장을 시도하면 UNIQUE 제약(rounds.room_id, round_no)이 깨져
    500 에러가 난다. `room_id`가 주어지면 트랜잭션 맨 앞에서 그 방의 행을
    `FOR UPDATE`로 잠가, 같은 방을 건드리는 동시 쓰기를 직렬화한다.
    (SQLite판의 `BEGIN IMMEDIATE`와 같은 목적.)
    """
    try:
        if room_id is not None:
            conn.execute("SELECT id FROM rooms WHERE id = %s FOR UPDATE", (room_id,))
        yield
    except BaseException:
        conn.rollback()
        raise
    else:
        conn.commit()
