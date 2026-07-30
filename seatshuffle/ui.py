"""tkinter 화면.

교실은 "열마다 행 수가 다를 수 있다"고 보고, 열 수와 각 열의 행 수를
모두 키보드로 직접 입력한다. 예: 5열 / 3·4·3·3·3행 = 16칸
"""

from __future__ import annotations

import random
import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import filedialog, font as tkfont, messagebox, ttk

from . import history as history_mod
from . import render, roster
from .model import (
    Layout,
    Seat,
    Student,
    build_seats,
    describe_layout,
    seating_grid,
)
from .shuffler import assign_detailed

MIN_COLS, MAX_COLS = 1, 15
MIN_ROWS, MAX_ROWS = 1, 15
MAX_LOOKBACK = 10

# 기본 교실: 5열이고 2열만 4행 깊이, 나머지는 3행 (총 16칸)
DEFAULT_LAYOUT: Layout = [3, 4, 3, 3, 3]

CANVAS_BG = "#f7f8fa"
BOARD_FILL = "#343c4a"
BOARD_TEXT = "#f5f6f8"
CARD_FILL = "#ffffff"
CARD_EDGE = "#c4cbd6"
EMPTY_FILL = "#eef0f4"
OK_FG = "#1c6b3f"
BAD_FG = "#a3352b"
MUTED_FG = "#6e7684"


class SeatShuffleApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.students: list[Student] = []
        self.seating: dict[Student, Seat] | None = None
        self.seating_layout: Layout | None = None
        self.round_no = history_mod.round_count(history_mod.load_history())
        self.rng = random.Random()
        self.last_png: Path | None = None
        self._ready = False  # 위젯 준비 전에는 다시 그리지 않는다

        self.col_count_var = tk.StringVar(value=str(len(DEFAULT_LAYOUT)))
        self.row_vars: list[tk.StringVar] = []
        self.lookback_var = tk.StringVar(value="1")
        self.name_var = tk.StringVar()
        self.seatcount_var = tk.StringVar()
        self.status_var = tk.StringVar(
            value="명단을 준비하고 열·행을 입력한 뒤 [자리 배정]을 누르세요."
        )

        self._restore_settings()
        if not self.row_vars:
            self._set_layout(DEFAULT_LAYOUT)

        self._build_ui()
        self._render_col_inputs()
        self._refresh_roster_view()

        self.col_count_var.trace_add("write", self._on_col_count_change)
        for var in self.row_vars:
            var.trace_add("write", self._on_dim_change)

        self._ready = True
        self._update_seatcount()
        self._redraw()

        root.protocol("WM_DELETE_WINDOW", self._on_close)

    # --- 화면 구성 -----------------------------------------------------------

    def _build_ui(self) -> None:
        root = self.root
        root.title("자리바꾸기")
        root.geometry("1080x720")
        root.minsize(880, 600)

        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont"):
            try:
                tkfont.nametofont(name).configure(family="맑은 고딕", size=10)
            except tk.TclError:
                pass

        self._build_menu()

        outer = ttk.Frame(root, padding=12)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(0, weight=1)

        self._build_left_panel(outer)
        self._build_result_panel(outer)
        self._build_action_bar(outer)

    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="명단 CSV 불러오기...", command=self._on_load_csv)
        file_menu.add_command(label="배정표 CSV로 내보내기...", command=self._on_export_csv)
        file_menu.add_separator()
        file_menu.add_command(label="배치도 PNG로 저장...", command=self._on_save_png)
        file_menu.add_command(label="배치도 인쇄", command=self._on_print)
        file_menu.add_separator()
        file_menu.add_command(label="종료", command=self._on_close)
        menubar.add_cascade(label="파일", menu=file_menu)

        tools_menu = tk.Menu(menubar, tearoff=0)
        tools_menu.add_command(label="모든 열을 같은 행 수로...", command=self._on_make_uniform)
        tools_menu.add_command(label="배정 이력 초기화...", command=self._on_clear_history)
        menubar.add_cascade(label="도구", menu=tools_menu)

        self.root.config(menu=menubar)

    def _build_left_panel(self, parent: ttk.Frame) -> None:
        left = ttk.Frame(parent)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        left.rowconfigure(0, weight=1)

        self._build_roster_box(left)
        self._build_classroom_box(left)
        self._build_avoid_box(left)

    def _build_roster_box(self, parent: ttk.Frame) -> None:
        box = ttk.LabelFrame(parent, text="명단", padding=8)
        box.grid(row=0, column=0, sticky="nsew")
        box.rowconfigure(0, weight=1)
        box.columnconfigure(0, weight=1)
        self.roster_box = box

        list_wrap = ttk.Frame(box)
        list_wrap.grid(row=0, column=0, columnspan=2, sticky="nsew")
        list_wrap.rowconfigure(0, weight=1)
        list_wrap.columnconfigure(0, weight=1)

        self.roster_list = tk.Listbox(
            list_wrap, selectmode=tk.EXTENDED, width=24, height=10, activestyle="none"
        )
        self.roster_list.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(list_wrap, orient="vertical", command=self.roster_list.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.roster_list.config(yscrollcommand=scroll.set)

        entry = ttk.Entry(box, textvariable=self.name_var)
        entry.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        entry.bind("<Return>", lambda _e: self._on_add_name())
        ttk.Button(box, text="추가", width=6, command=self._on_add_name).grid(
            row=1, column=1, sticky="ew", padx=(6, 0), pady=(8, 0)
        )

        btns = ttk.Frame(box)
        btns.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        for i in range(3):
            btns.columnconfigure(i, weight=1)
        ttk.Button(btns, text="붙여넣기", command=self._on_bulk_add).grid(
            row=0, column=0, sticky="ew", padx=(0, 4)
        )
        ttk.Button(btns, text="삭제", command=self._on_delete_selected).grid(
            row=0, column=1, sticky="ew", padx=2
        )
        ttk.Button(btns, text="비우기", command=self._on_clear_roster).grid(
            row=0, column=2, sticky="ew", padx=(4, 0)
        )
        ttk.Button(box, text="CSV 불러오기", command=self._on_load_csv).grid(
            row=3, column=0, columnspan=2, sticky="ew", pady=(6, 0)
        )

    def _build_classroom_box(self, parent: ttk.Frame) -> None:
        box = ttk.LabelFrame(parent, text="교실", padding=8)
        box.grid(row=1, column=0, sticky="ew", pady=(12, 0))

        head = ttk.Frame(box)
        head.grid(row=0, column=0, sticky="w")
        ttk.Label(head, text="열 수").pack(side="left")
        ttk.Entry(
            head,
            textvariable=self.col_count_var,
            width=4,
            justify="center",
            validate="key",
            validatecommand=(self.root.register(self._validate_digits), "%P"),
        ).pack(side="left", padx=(4, 6))
        ttk.Label(head, text=f"({MIN_COLS}~{MAX_COLS})", foreground=MUTED_FG).pack(side="left")

        ttk.Label(box, text="열마다 행 수를 직접 입력").grid(
            row=1, column=0, sticky="w", pady=(8, 4)
        )

        self.cols_frame = ttk.Frame(box)
        self.cols_frame.grid(row=2, column=0, sticky="w")

        self.seatcount_label = ttk.Label(box, textvariable=self.seatcount_var)
        self.seatcount_label.grid(row=3, column=0, sticky="w", pady=(8, 0))

        ttk.Label(
            box,
            text="1열 = 가장 왼쪽 줄 · 1행 = 칠판 쪽\n짧은 열은 뒷자리가 빕니다",
            foreground=MUTED_FG,
            justify="left",
        ).grid(row=4, column=0, sticky="w", pady=(6, 0))

    def _build_avoid_box(self, parent: ttk.Frame) -> None:
        box = ttk.LabelFrame(parent, text="지난 자리 회피", padding=8)
        box.grid(row=2, column=0, sticky="ew", pady=(12, 0))

        line = ttk.Frame(box)
        line.grid(row=0, column=0, sticky="w")
        ttk.Label(line, text="최근").pack(side="left")
        ttk.Spinbox(
            line,
            from_=0,
            to=MAX_LOOKBACK,
            width=4,
            justify="center",
            textvariable=self.lookback_var,
        ).pack(side="left", padx=4)
        ttk.Label(line, text="회차 회피").pack(side="left")
        ttk.Label(box, text="0이면 회피 없이 순수 무작위", foreground=MUTED_FG).grid(
            row=1, column=0, sticky="w", pady=(6, 0)
        )

    def _build_result_panel(self, parent: ttk.Frame) -> None:
        box = ttk.LabelFrame(parent, text="배치 결과", padding=6)
        box.grid(row=0, column=1, sticky="nsew")
        box.rowconfigure(0, weight=1)
        box.columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(box, background=CANVAS_BG, highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.canvas.bind("<Configure>", lambda _e: self._redraw())

    def _build_action_bar(self, parent: ttk.Frame) -> None:
        bar = ttk.Frame(parent)
        bar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(12, 0))

        ttk.Button(bar, text="자리 배정", command=self._on_assign).pack(side="left")
        ttk.Button(bar, text="PNG 저장", command=self._on_save_png).pack(
            side="left", padx=(8, 0)
        )
        ttk.Button(bar, text="인쇄", command=self._on_print).pack(side="left", padx=(6, 0))
        ttk.Button(bar, text="CSV 내보내기", command=self._on_export_csv).pack(
            side="left", padx=(6, 0)
        )
        ttk.Label(bar, textvariable=self.status_var, foreground=MUTED_FG).pack(
            side="left", padx=(16, 0)
        )

    # --- 열별 행 수 입력 -----------------------------------------------------

    @staticmethod
    def _validate_digits(proposed: str) -> bool:
        """입력창에는 숫자만, 최대 2자리까지 받는다."""
        return proposed == "" or (proposed.isdigit() and len(proposed) <= 2)

    def _set_layout(self, counts: Layout) -> None:
        """행 수 변수 목록을 주어진 배치로 갈아끼운다 (위젯 갱신은 별도)."""
        self.row_vars = [tk.StringVar(value=str(n)) for n in counts]
        self.col_count_var.set(str(len(counts)))

    def _render_col_inputs(self) -> None:
        """열 수에 맞춰 '1열 [3] 행' 입력창들을 다시 그린다."""
        for child in self.cols_frame.winfo_children():
            child.destroy()

        digits_ok = (self.root.register(self._validate_digits), "%P")
        for i, var in enumerate(self.row_vars):
            row, column = divmod(i, 2)
            cell = ttk.Frame(self.cols_frame)
            cell.grid(row=row, column=column, sticky="w", padx=(0, 12), pady=1)
            ttk.Label(cell, text=f"{i + 1}열", width=3).pack(side="left")
            ttk.Entry(
                cell,
                textvariable=var,
                width=3,
                justify="center",
                validate="key",
                validatecommand=digits_ok,
            ).pack(side="left", padx=(2, 2))
            ttk.Label(cell, text="행").pack(side="left")

    def _on_col_count_change(self, *_args: object) -> None:
        """열 수를 고치면 입력창 개수를 맞춘다. 기존 값은 최대한 유지."""
        text = self.col_count_var.get().strip()
        if not text.isdigit() or not MIN_COLS <= int(text) <= MAX_COLS:
            self._update_seatcount()
            self._redraw()
            return

        target = int(text)
        if target == len(self.row_vars):
            return

        fallback = self.row_vars[-1].get() if self.row_vars else "3"
        while len(self.row_vars) < target:
            var = tk.StringVar(value=fallback if fallback.isdigit() else "3")
            var.trace_add("write", self._on_dim_change)
            self.row_vars.append(var)
        del self.row_vars[target:]

        self._render_col_inputs()
        self._on_dim_change()

    def _on_dim_change(self, *_args: object) -> None:
        # 교실 모양이 바뀌면 이전 배정은 더 이상 맞지 않으므로 미리보기를 비운다.
        if not self._ready:
            return
        if self.seating is not None:
            self.seating = None
            self.seating_layout = None
        self._update_seatcount()
        self._redraw()

    def _on_make_uniform(self) -> None:
        """모든 열을 같은 행 수로 맞추는 편의 기능."""
        counts = self._read_layout()
        current = str(counts[0]) if counts else "3"
        answer = _ask_number(
            self.root,
            "모든 열을 같은 행 수로",
            f"모든 열의 행 수를 얼마로 맞출까요? ({MIN_ROWS}~{MAX_ROWS})",
            current,
        )
        if answer is None:
            return
        if not MIN_ROWS <= answer <= MAX_ROWS:
            messagebox.showwarning(
                "값을 확인해주세요", f"행 수는 {MIN_ROWS}~{MAX_ROWS} 사이여야 합니다."
            )
            return
        for var in self.row_vars:
            var.set(str(answer))

    def _read_layout(self) -> Layout | None:
        """유효할 때만 열별 행 수 목록. 잘못된 입력이면 None (팝업 없음)."""
        try:
            return self._parse_layout()
        except ValueError:
            return None

    def _read_layout_strict(self) -> Layout | None:
        """배정 직전 검증. 잘못된 입력이면 안내 후 None."""
        try:
            return self._parse_layout()
        except ValueError as exc:
            messagebox.showwarning("열·행을 확인해주세요", str(exc))
            return None

    def _parse_layout(self) -> Layout:
        text = self.col_count_var.get().strip()
        if not text.isdigit():
            raise ValueError("열 수를 숫자로 입력해주세요.")
        cols = int(text)
        if not MIN_COLS <= cols <= MAX_COLS:
            raise ValueError(f"열 수는 {MIN_COLS}~{MAX_COLS} 사이로 입력해주세요.")
        if cols != len(self.row_vars):
            raise ValueError("열 수와 입력창 개수가 아직 맞지 않습니다. 잠시 후 다시 시도해주세요.")

        counts: Layout = []
        for i, var in enumerate(self.row_vars, start=1):
            value = var.get().strip()
            if not value.isdigit():
                raise ValueError(f"{i}열의 행 수를 숫자로 입력해주세요.")
            number = int(value)
            if not MIN_ROWS <= number <= MAX_ROWS:
                raise ValueError(
                    f"{i}열의 행 수는 {MIN_ROWS}~{MAX_ROWS} 사이로 입력해주세요."
                )
            counts.append(number)
        return counts

    def _read_lookback(self) -> int:
        text = self.lookback_var.get().strip()
        if not text.isdigit():
            return 0
        return min(int(text), MAX_LOOKBACK)

    def _update_seatcount(self) -> None:
        counts = self._read_layout()
        if counts is None:
            self.seatcount_var.set("열 수와 각 열의 행 수를 숫자로 입력해주세요")
            self.seatcount_label.configure(foreground=BAD_FG)
            return

        total = sum(counts)
        people = len(self.students)
        pattern = "·".join(str(n) for n in counts)
        base = f"{pattern} = {total}칸  ·  명단 {people}명"

        if total == people:
            self.seatcount_var.set(f"{base} (딱 맞음)")
            self.seatcount_label.configure(foreground=OK_FG)
        else:
            gap = abs(total - people)
            tail = f"{gap}칸이 남음" if total > people else f"{gap}명이 남음"
            self.seatcount_var.set(f"{base} ({tail})")
            self.seatcount_label.configure(foreground=BAD_FG)

    # --- 명단 편집 -----------------------------------------------------------

    def _refresh_roster_view(self) -> None:
        self.roster_list.delete(0, tk.END)
        for i, student in enumerate(self.students, start=1):
            label = student.name
            if student.number is not None:
                label = f"{student.number}. {student.name}"
            self.roster_list.insert(tk.END, f"{i:>2}  {label}")
        self.roster_box.configure(text=f"명단 ({len(self.students)}명)")
        self._update_seatcount()

    def _on_add_name(self) -> None:
        added = self._add_lines(self.name_var.get().replace(",", "\n").splitlines())
        if added:
            self.name_var.set("")
            self._invalidate_seating(f"{added}명 추가")

    def _on_bulk_add(self) -> None:
        win = tk.Toplevel(self.root)
        win.title("명단 붙여넣기")
        win.transient(self.root)
        win.grab_set()
        win.geometry("320x420")

        ttk.Label(
            win,
            text="한 줄에 한 명씩 붙여넣으세요.\n'1. 김민준' 처럼 번호가 붙어 있어도 됩니다.",
            padding=(10, 10, 10, 6),
            justify="left",
        ).pack(anchor="w")

        text = tk.Text(win, wrap="none")
        text.pack(fill="both", expand=True, padx=10)
        text.focus_set()

        bar = ttk.Frame(win, padding=10)
        bar.pack(fill="x")

        def apply() -> None:
            added = self._add_lines(text.get("1.0", "end").splitlines())
            win.destroy()
            if added:
                self._invalidate_seating(f"{added}명 추가")

        ttk.Button(bar, text="추가", command=apply).pack(side="right")
        ttk.Button(bar, text="취소", command=win.destroy).pack(side="right", padx=(0, 6))

    def _add_lines(self, lines: list[str]) -> int:
        added = 0
        for line in lines:
            student = roster.parse_name_line(line)
            if student is not None:
                self.students.append(student)
                added += 1
        if added:
            self._refresh_roster_view()
            for message in roster.duplicate_warnings(self.students):
                messagebox.showwarning("이름 중복", message)
        return added

    def _on_delete_selected(self) -> None:
        selected = sorted(self.roster_list.curselection(), reverse=True)
        if not selected:
            self.status_var.set("삭제할 학생을 목록에서 선택해주세요.")
            return
        for index in selected:
            del self.students[index]
        self._refresh_roster_view()
        self._invalidate_seating(f"{len(selected)}명 삭제")

    def _on_clear_roster(self) -> None:
        if not self.students:
            return
        if not messagebox.askyesno("명단 비우기", "명단을 전부 지울까요?"):
            return
        self.students.clear()
        self._refresh_roster_view()
        self._invalidate_seating("명단을 비웠습니다")

    def _on_load_csv(self) -> None:
        path = filedialog.askopenfilename(
            title="명단 CSV 선택",
            filetypes=[("CSV 파일", "*.csv"), ("모든 파일", "*.*")],
            initialdir=str(history_mod.PROJECT_ROOT),
        )
        if not path:
            return
        try:
            students, warnings = roster.load_roster(path)
        except (OSError, UnicodeDecodeError) as exc:
            messagebox.showerror("파일을 읽을 수 없어요", str(exc))
            return

        if not students:
            messagebox.showwarning(
                "명단이 비어 있어요", "\n".join(warnings) or "읽을 이름이 없습니다."
            )
            return

        self.students = students
        self._refresh_roster_view()
        self._invalidate_seating(f"{Path(path).name} 에서 {len(students)}명 불러옴")
        for message in warnings:
            messagebox.showwarning("확인해주세요", message)

    # --- 배정 ---------------------------------------------------------------

    def _on_assign(self) -> None:
        counts = self._read_layout_strict()
        if counts is None:
            return

        total = sum(counts)
        if len(self.students) != total:
            messagebox.showwarning(
                "인원과 좌석 수가 달라요",
                f"학생은 {len(self.students)}명인데 좌석은 {total}칸입니다.\n"
                f"({describe_layout(counts)})\n"
                "열별 행 수를 조정하거나 명단을 확인해주세요.",
            )
            return

        lookback = self._read_lookback()
        history = history_mod.load_history()
        forbidden = history_mod.forbidden_seats(history, lookback)
        result = assign_detailed(
            self.students, build_seats(counts), forbidden, rng=self.rng
        )

        if not result.ok:
            messagebox.showinfo(
                "배정을 찾지 못했어요",
                "지난 자리를 모두 피하는 배정을 찾지 못했어요.\n"
                "'회피할 회차 수'를 줄이거나 교실 크기를 늘려보세요.",
            )
            self.status_var.set("배정 실패 — 회피 조건이 너무 빡빡합니다.")
            return

        self.seating = result.seating
        self.seating_layout = list(counts)
        history_mod.save_round(self.seating, counts, history=history)
        self.round_no = history_mod.round_count(history)
        self.last_png = None
        self._redraw()

        avoid_note = "회피 없음" if lookback == 0 else f"최근 {lookback}회차 회피"
        self.status_var.set(
            f"배정 완료 · {result.describe()} · {self.round_no}회차 ({avoid_note})"
        )

    def _invalidate_seating(self, note: str) -> None:
        self.seating = None
        self.seating_layout = None
        self.last_png = None
        self.status_var.set(note)
        self._redraw()

    # --- 결과 출력 ----------------------------------------------------------

    def _require_seating(self) -> tuple[dict[Student, Seat], Layout] | None:
        if self.seating is None or self.seating_layout is None:
            messagebox.showinfo(
                "먼저 배정해주세요", "[자리 배정]을 눌러 결과를 만든 뒤 사용하세요."
            )
            return None
        return self.seating, self.seating_layout

    def _on_save_png(self) -> None:
        data = self._require_seating()
        if data is None:
            return
        seating, counts = data
        path = filedialog.asksaveasfilename(
            title="배치도 PNG 저장",
            defaultextension=".png",
            initialfile=f"자리배치_{date.today().isoformat()}.png",
            initialdir=str(history_mod.ensure_data_dir()),
            filetypes=[("PNG 이미지", "*.png")],
        )
        if not path:
            return
        try:
            saved = render.render_png(seating, counts, path=path, round_no=self.round_no)
        except OSError as exc:
            messagebox.showerror("저장 실패", str(exc))
            return
        self.last_png = saved
        self.status_var.set(f"PNG 저장: {saved}")

    def _on_print(self) -> None:
        data = self._require_seating()
        if data is None:
            return
        seating, counts = data
        target = history_mod.ensure_data_dir() / f"자리배치_{date.today().isoformat()}.png"
        try:
            saved = render.render_png(seating, counts, path=target, round_no=self.round_no)
        except OSError as exc:
            messagebox.showerror("인쇄 준비 실패", str(exc))
            return

        self.last_png = saved
        if render.print_image(saved):
            self.status_var.set(f"인쇄 요청: {saved.name}")
        else:
            messagebox.showinfo(
                "인쇄 대화를 열지 못했어요",
                f"배치도를 아래 경로에 저장했어요. 폴더를 열어드렸으니 직접 인쇄해주세요.\n\n{saved}",
            )
            self.status_var.set(f"PNG만 저장됨: {saved}")

    def _on_export_csv(self) -> None:
        data = self._require_seating()
        if data is None:
            return
        seating, counts = data
        path = filedialog.asksaveasfilename(
            title="배정표 CSV 저장",
            defaultextension=".csv",
            initialfile=f"자리배정_{date.today().isoformat()}.csv",
            initialdir=str(history_mod.ensure_data_dir()),
            filetypes=[("CSV 파일", "*.csv")],
        )
        if not path:
            return
        try:
            roster.export_seating(path, seating, counts)
        except OSError as exc:
            messagebox.showerror("저장 실패", str(exc))
            return
        self.status_var.set(f"CSV 저장: {path}")

    def _on_clear_history(self) -> None:
        if self.round_no == 0:
            messagebox.showinfo("이력 없음", "저장된 배정 이력이 없습니다.")
            return
        if not messagebox.askyesno(
            "배정 이력 초기화",
            f"{self.round_no}회차 기록을 모두 지울까요?\n지난 자리 회피 기준이 사라집니다.",
        ):
            return
        history_mod.clear_history()
        self.round_no = 0
        self._redraw()
        self.status_var.set("배정 이력을 초기화했습니다.")

    # --- 격자 그리기 ---------------------------------------------------------

    def _redraw(self) -> None:
        canvas = self.canvas
        canvas.delete("all")
        width = canvas.winfo_width()
        height = canvas.winfo_height()
        if width < 20 or height < 20:  # 아직 배치 전
            return

        counts = self._read_layout()
        if counts is None:
            canvas.create_text(
                width / 2,
                height / 2,
                text="열 수와 각 열의 행 수를 숫자로 입력해주세요",
                fill=MUTED_FG,
            )
            return

        grid = (
            seating_grid(self.seating, counts)
            if self.seating is not None
            else [[None] * len(counts) for _ in range(max(counts))]
        )

        cols = len(counts)
        depth = max(counts)
        pad = 16
        gap = 6
        board_h = 28
        board_gap = 14
        footer_h = 24

        avail_w = width - pad * 2 - gap * (cols - 1)
        avail_h = height - pad * 2 - board_h - board_gap - footer_h - gap * (depth - 1)
        cell_w = max(26.0, min(150.0, avail_w / cols))
        cell_h = max(20.0, min(90.0, avail_h / depth))

        grid_w = cell_w * cols + gap * (cols - 1)
        x_start = max(pad, (width - grid_w) / 2)

        canvas.create_rectangle(
            x_start, pad, x_start + grid_w, pad + board_h, fill=BOARD_FILL, outline=""
        )
        canvas.create_text(
            x_start + grid_w / 2,
            pad + board_h / 2,
            text="칠  판",
            fill=BOARD_TEXT,
            font=("맑은 고딕", 10, "bold"),
        )

        grid_top = pad + board_h + board_gap
        name_size = int(max(8, min(14, cell_h * 0.26)))
        num_size = int(max(7, min(10, cell_h * 0.16)))

        for c, depth_of_col in enumerate(counts):
            # 각 열은 앞줄(칠판 쪽)부터 채운다. 짧은 열은 뒤에 카드가 없다.
            for r in range(depth_of_col):
                x0 = x_start + c * (cell_w + gap)
                y0 = grid_top + r * (cell_h + gap)
                student = grid[r][c]
                canvas.create_rectangle(
                    x0,
                    y0,
                    x0 + cell_w,
                    y0 + cell_h,
                    fill=CARD_FILL if student else EMPTY_FILL,
                    outline=CARD_EDGE,
                )
                if student is None:
                    continue
                cx = x0 + cell_w / 2
                if student.number is not None and cell_h >= 42:
                    canvas.create_text(
                        cx,
                        y0 + cell_h * 0.28,
                        text=f"{student.number}번",
                        fill=MUTED_FG,
                        font=("맑은 고딕", num_size),
                    )
                    name_y = y0 + cell_h * 0.62
                else:
                    name_y = y0 + cell_h / 2
                canvas.create_text(
                    cx,
                    name_y,
                    text=student.name,
                    width=cell_w - 6,
                    font=("맑은 고딕", name_size, "bold"),
                )

        footer = date.today().isoformat()
        if self.seating is not None:
            footer += f"  ·  {self.round_no}회차 배정  ·  {describe_layout(counts)}"
        else:
            footer += f"  ·  {describe_layout(counts)}  ·  {self.round_no}회차까지 기록됨"
        canvas.create_text(
            width / 2, height - footer_h / 2 - 4, text=footer, fill=MUTED_FG
        )

    # --- 설정 저장/복원 ------------------------------------------------------

    def _restore_settings(self) -> None:
        settings = history_mod.load_settings()

        counts = settings.get("columns")
        if (
            isinstance(counts, list)
            and counts
            and len(counts) <= MAX_COLS
            and all(isinstance(n, int) and MIN_ROWS <= n <= MAX_ROWS for n in counts)
        ):
            self._set_layout(counts)

        lookback = settings.get("lookback")
        if isinstance(lookback, int) and 0 <= lookback <= MAX_LOOKBACK:
            self.lookback_var.set(str(lookback))

        saved_students = settings.get("students")
        if isinstance(saved_students, list):
            restored: list[Student] = []
            for item in saved_students:
                if isinstance(item, dict) and str(item.get("name", "")).strip():
                    number = item.get("number")
                    restored.append(
                        Student(
                            str(item["name"]).strip(),
                            number if isinstance(number, int) else None,
                        )
                    )
            self.students = restored

    def _on_close(self) -> None:
        settings = {
            "columns": self._read_layout(),
            "lookback": self._read_lookback(),
            "students": [{"name": s.name, "number": s.number} for s in self.students],
        }
        try:
            history_mod.save_settings(settings)
        except OSError:
            pass  # 설정 저장 실패로 종료를 막지는 않는다
        self.root.destroy()


def _ask_number(
    parent: tk.Misc, title: str, prompt: str, initial: str
) -> int | None:
    """숫자 하나를 물어보는 작은 대화창. 취소하거나 숫자가 아니면 None."""
    win = tk.Toplevel(parent)
    win.title(title)
    win.transient(parent)
    win.grab_set()
    win.resizable(False, False)

    var = tk.StringVar(value=initial)
    answer: dict[str, int | None] = {"value": None}

    ttk.Label(win, text=prompt, padding=(12, 12, 12, 6)).pack(anchor="w")
    entry = ttk.Entry(win, textvariable=var, width=6, justify="center")
    entry.pack(padx=12, anchor="w")
    entry.focus_set()
    entry.select_range(0, tk.END)

    def confirm() -> None:
        text = var.get().strip()
        answer["value"] = int(text) if text.isdigit() else None
        win.destroy()

    bar = ttk.Frame(win, padding=12)
    bar.pack(fill="x")
    ttk.Button(bar, text="확인", command=confirm).pack(side="right")
    ttk.Button(bar, text="취소", command=win.destroy).pack(side="right", padx=(0, 6))
    entry.bind("<Return>", lambda _e: confirm())

    parent.wait_window(win)
    return answer["value"]


def main() -> None:
    root = tk.Tk()
    SeatShuffleApp(root)
    root.mainloop()
