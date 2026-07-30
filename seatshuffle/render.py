"""배치도 PNG 렌더링과 인쇄.

tkinter Canvas 캡처는 화면 상태에 의존해 불안정하므로 Pillow로 처음부터 다시 그린다.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .model import Seat, Student, as_layout, seating_grid

REGULAR_FONTS = (r"C:\Windows\Fonts\malgun.ttf", r"C:\Windows\Fonts\gulim.ttc")
BOLD_FONTS = (r"C:\Windows\Fonts\malgunbd.ttf", *REGULAR_FONTS)

CELL_W, CELL_H = 150, 96
GAP = 14
MARGIN = 44
HEADER_H = 96
BOARD_H = 46
BOARD_GAP = 26

BG = (247, 248, 250)
CARD = (255, 255, 255)
CARD_EDGE = (196, 203, 214)
EMPTY_CARD = (238, 240, 244)
TEXT = (28, 32, 40)
SUBTEXT = (110, 118, 132)
BOARD_BG = (52, 60, 74)
BOARD_TEXT = (245, 246, 248)


def render_png(
    seating: dict[Student, Seat],
    layout: Sequence[int] | int,
    rows: int | None = None,
    path: str | Path = "자리배치도.png",
    title: str = "자리 배치도",
    round_no: int | None = None,
) -> Path:
    """좌석 카드를 그려 PNG로 저장하고 저장 경로를 돌려준다.

    `layout`은 열별 행 수 목록([3, 4, 3, 3, 3]) 또는 균일 교실의 (열 수, 행 수).
    열마다 행 수가 다르면 짧은 열은 앞줄(칠판 쪽)부터 채우고 뒤를 비운다.
    """
    counts = as_layout(layout, rows)
    grid = seating_grid(seating, counts)
    cols = len(counts)
    depth = max(counts)

    width = MARGIN * 2 + cols * CELL_W + (cols - 1) * GAP
    height = (
        MARGIN * 2
        + HEADER_H
        + BOARD_H
        + BOARD_GAP
        + depth * CELL_H
        + (depth - 1) * GAP
    )

    image = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(image)

    title_font = _load_font(34, bold=True)
    sub_font = _load_font(18)

    draw.text((MARGIN, MARGIN), title, font=title_font, fill=TEXT)
    subtitle = date.today().isoformat()
    if round_no:
        subtitle += f"  ·  {round_no}회차"
    draw.text((MARGIN, MARGIN + 48), subtitle, font=sub_font, fill=SUBTEXT)

    # 칠판 띠 — 어느 쪽이 앞인지 한눈에 보이게
    board_top = MARGIN + HEADER_H
    draw.rectangle(
        [MARGIN, board_top, width - MARGIN, board_top + BOARD_H],
        fill=BOARD_BG,
    )
    _draw_centered(
        draw,
        ((MARGIN + width - MARGIN) / 2, board_top + BOARD_H / 2),
        "칠  판",
        _load_font(20, bold=True),
        BOARD_TEXT,
    )

    grid_top = board_top + BOARD_H + BOARD_GAP
    number_font = _load_font(14)

    for c, depth_of_col in enumerate(counts):
        # 각 열은 앞줄(칠판 쪽)부터 채운다. 짧은 열은 뒤가 비어 카드도 그리지 않는다.
        for r in range(depth_of_col):
            x0 = MARGIN + c * (CELL_W + GAP)
            y0 = grid_top + r * (CELL_H + GAP)
            x1, y1 = x0 + CELL_W, y0 + CELL_H
            student = grid[r][c]

            draw.rounded_rectangle(
                [x0, y0, x1, y1],
                radius=10,
                fill=CARD if student else EMPTY_CARD,
                outline=CARD_EDGE,
                width=2,
            )
            if student is None:
                continue

            center_x = (x0 + x1) / 2
            if student.number is not None:
                _draw_centered(
                    draw, (center_x, y0 + 26), f"{student.number}번", number_font, SUBTEXT
                )
                name_y = y0 + CELL_H * 0.62
            else:
                name_y = (y0 + y1) / 2

            name_font = _fit_font(student.name, CELL_W - 20, 28)
            _draw_centered(draw, (center_x, name_y), student.name, name_font, TEXT)

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return path


def print_image(path: str | Path) -> bool:
    """Windows 인쇄 대화 상자를 띄운다.

    실패하면 저장 폴더를 열어주고 False를 돌려준다 (호출한 쪽에서 안내).
    """
    target = Path(path)
    try:
        os.startfile(str(target), "print")
        return True
    except OSError:
        try:
            os.startfile(str(target.parent))
        except OSError:
            pass
        return False


def _load_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    for candidate in BOLD_FONTS if bold else REGULAR_FONTS:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _fit_font(text: str, max_width: int, start_size: int) -> ImageFont.ImageFont:
    """긴 이름이 카드를 넘지 않도록 글자 크기를 줄여 맞춘다."""
    size = start_size
    while size > 11:
        font = _load_font(size)
        if _text_width(font, text) <= max_width:
            return font
        size -= 2
    return _load_font(11)


def _text_width(font: ImageFont.ImageFont, text: str) -> float:
    left, _, right, _ = font.getbbox(text)
    return right - left


def _draw_centered(
    draw: ImageDraw.ImageDraw,
    center: tuple[float, float],
    text: str,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int],
) -> None:
    """anchor 지원 여부에 상관없이 텍스트를 중앙에 그린다."""
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    x = center[0] - (right - left) / 2 - left
    y = center[1] - (bottom - top) / 2 - top
    draw.text((x, y), text, font=font, fill=fill)
