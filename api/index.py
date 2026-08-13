"""Vercel 진입점. `@vercel/python`이 이 모듈의 `app`(WSGI 콜러블)을 서빙한다."""

from webapp import create_app

app = create_app()
