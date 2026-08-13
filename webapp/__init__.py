"""자리바꾸기 웹 앱 — 반별로 독립된 방(room)을 여러 개 동시에 지원한다."""

from __future__ import annotations

import os

from flask import Flask

from . import db

# Vercel의 Postgres 연동 방식에 따라 주입되는 환경변수 이름이 다를 수 있다
# (기본 Vercel Postgres는 POSTGRES_URL, Neon 마켓플레이스 연동은 DATABASE_URL을
# 쓰는 식) — 순서대로 찾아본다.
_DATABASE_URL_ENV_VARS = ("POSTGRES_URL", "DATABASE_URL", "POSTGRES_PRISMA_URL")


def _find_database_url() -> str:
    for name in _DATABASE_URL_ENV_VARS:
        value = os.environ.get(name)
        if value:
            return value
    raise RuntimeError(
        "Postgres 연결 문자열을 환경변수에서 찾지 못했습니다. "
        f"다음 중 하나를 설정해주세요: {', '.join(_DATABASE_URL_ENV_VARS)} "
        "(Vercel 프로젝트의 Storage에서 Postgres를 연결하면 자동으로 주입됩니다)."
    )


def create_app(database_url: str | None = None) -> Flask:
    app = Flask(__name__)
    app.config["DATABASE_URL"] = database_url or _find_database_url()

    # 서버리스 인스턴스마다 새 무작위 키를 쓰면 flash 메시지가 담긴 세션
    # 쿠키 서명이 콜드 스타트 때마다 어긋난다 — 반드시 고정된 값을 쓴다.
    secret_key = os.environ.get("FLASK_SECRET_KEY")
    if not secret_key:
        raise RuntimeError(
            "FLASK_SECRET_KEY 환경변수가 설정되지 않았습니다. "
            "Vercel 프로젝트 Settings → Environment Variables에서 추가해주세요."
        )
    app.secret_key = secret_key

    db.init_app(app)

    from .routes.main import bp as main_bp
    from .routes.room import bp as room_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(room_bp)

    return app
