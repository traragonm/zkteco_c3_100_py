from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from ..models import AccessEvent
from . import theme
from .widgets import Card


class OpenDoorPrompt(tk.Toplevel):
    """
    Popup hỏi người vận hành có mở cửa hay không (khi chưa cấu hình Verify API hoặc API lỗi).
    Hết thời gian chờ thì tự động từ chối. Kết quả trả qua ``on_close(open, timed_out)``.
    """

    def __init__(self, master, e: AccessEvent, reason: str, timeout_seconds: int, waiting_count: int,
                 on_close: Callable[[bool, bool], None]):
        super().__init__(master, bg=theme.CARD)
        self._on_close = on_close
        self._remaining = timeout_seconds
        self._waiting = f" · còn {waiting_count} lượt quét đang chờ" if waiting_count > 0 else ""
        self._done = False

        self.title("Xác thực thủ công")
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.transient(master)

        body = ttk.Frame(self, style="Card.TFrame", padding=(22, 20, 22, 6))
        body.pack(fill="both", expand=True)
        tk.Label(body, text="Mở cửa cho lượt quét này?", bg=theme.CARD, fg=theme.TEXT,
                 font=("Segoe UI Semibold", 13)).pack(anchor="w")
        tk.Label(body, text=reason, bg=theme.CARD, fg=theme.MUTED, wraplength=400, justify="left").pack(
            anchor="w", pady=(2, 14))

        info = Card(body)
        info.pack(fill="x")
        rows = [
            ("Mã QR / Card", e.code, theme.MONO_BOLD, theme.TEXT),
            ("Cửa", f"{e.door} ({e.direction})", theme.UI, theme.TEXT),
            ("PIN", e.pin, theme.UI, theme.TEXT),
            ("Thời gian", f"{e.time:%Y-%m-%d %H:%M:%S}", theme.MONO, theme.TEXT),
            ("Controller", e.event_name, theme.UI, theme.SUCCESS_TEXT if e.granted else theme.DANGER_TEXT),
        ]
        for i, (caption, value, font, color) in enumerate(rows):
            tk.Label(info.body, text=caption, bg=theme.CARD, fg=theme.MUTED, font=theme.SMALL).grid(
                row=i, column=0, sticky="w", padx=(0, 16), pady=3)
            tk.Label(info.body, text=value, bg=theme.CARD, fg=color, font=font, wraplength=280, justify="left").grid(
                row=i, column=1, sticky="w", pady=3)

        self._countdown = tk.Label(body, bg=theme.CARD, fg=theme.MUTED, font=theme.SMALL)
        self._countdown.pack(anchor="w", pady=(12, 0))
        self._update_countdown()

        bar = ttk.Frame(self, style="Card.TFrame", padding=(22, 12, 22, 16))
        bar.pack(fill="x")
        ttk.Button(bar, text="Mở cửa  (Enter)", style="Primary.TButton", command=lambda: self._finish(True)).pack(side="right")
        ttk.Button(bar, text="Không mở  (Esc)", command=lambda: self._finish(False)).pack(side="right", padx=(0, 8))

        self.bind("<Return>", lambda _: self._finish(True))
        self.bind("<Escape>", lambda _: self._finish(False))
        self.protocol("WM_DELETE_WINDOW", lambda: self._finish(False))

        self.update_idletasks()
        x = master.winfo_rootx() + (master.winfo_width() - self.winfo_width()) // 2
        y = master.winfo_rooty() + (master.winfo_height() - self.winfo_height()) // 3
        self.geometry(f"+{max(0, x)}+{max(0, y)}")
        self.bell()
        self.focus_force()
        self.after(1000, self._tick)

    def _update_countdown(self) -> None:
        self._countdown.configure(text=f"Tự động từ chối sau {self._remaining} giây{self._waiting}")

    def _tick(self) -> None:
        if self._done:
            return
        self._remaining -= 1
        self._update_countdown()
        if self._remaining <= 0:
            self._finish(False, timed_out=True)
        else:
            self.after(1000, self._tick)

    def _finish(self, open_door: bool, timed_out: bool = False) -> None:
        if self._done:
            return
        self._done = True
        self.destroy()
        self._on_close(open_door, timed_out)
