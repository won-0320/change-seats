"""자리바꾸기 웹 앱 — 반별로 독립된 방(room)을 여러 개 동시에 지원한다."""

from __future__ import annotations

import os

from flask import Flask

from . import db


def create_app(database_url: str | None = None) -> Flask:
    app = Flask(__name__)
    app.config["DATABASE_URL"] = database_url or os.environ["POSTGRES_URL"]
    # 서버리스 인스턴스마다 새 무작위 키를 쓰면 flash 메시지가 담긴 세션
    # 쿠키 서명이 콜드 스타트 때마다 어긋난다 — 반드시 고정된 값을 쓴다.
    app.secret_key = os.environ["FLASK_SECRET_KEY"]

    db.init_app(app)

    from .routes.main import bp as main_bp
    from .routes.room import bp as room_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(room_bp)

    return app
