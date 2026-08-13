"""로컬 개발 서버 진입점.

실행: `python -m webapp.app` (저장소 루트에서)
"""

from __future__ import annotations

from . import create_app

if __name__ == "__main__":
    app = create_app()
    app.run(host="127.0.0.1", port=5000, debug=True, threaded=True)
