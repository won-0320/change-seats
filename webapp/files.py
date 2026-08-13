"""경로 기반 seatshuffle 함수(render_png, export_seating, load_roster)와
웹 요청(업로드/다운로드) 사이를 잇는 임시 파일 어댑터."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def tempfile_scope(suffix: str) -> Iterator[Path]:
    """임시 파일 경로 하나를 내주고, 블록이 끝나면 지운다."""
    fd, raw_path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    path = Path(raw_path)
    try:
        yield path
    finally:
        path.unlink(missing_ok=True)
