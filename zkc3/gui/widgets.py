from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from . import theme


class Card(tk.Frame):
    """Khung trắng có viền và tiêu đề; đặt control con vào ``self.body``."""

    def __init__(self, master, title: str = "", **kw):
        super().__init__(master, bg=theme.CARD, highlightthickness=1, highlightbackground=theme.BORDER, **kw)
        if title:
            tk.Label(self, text=title, bg=theme.CARD, fg=theme.TEXT, font=theme.CARD_TITLE, anchor="w").pack(
                fill="x", padx=14, pady=(9, 0))
            tk.Frame(self, bg=theme.DIVIDER, height=1).pack(fill="x", pady=(7, 0))
        self.body = ttk.Frame(self, style="Card.TFrame", padding=(14, 9, 14, 12))
        self.body.pack(fill="both", expand=True)


class Pill(tk.Label):
    """Nhãn bo tròn đơn giản (nền màu)."""

    def __init__(self, master, text: str = "", colors: tuple[str, str] = (theme.DIVIDER, theme.MUTED), **kw):
        super().__init__(master, text=text, font=theme.SMALL_BOLD, padx=10, pady=2, **kw)
        self.set(text, colors)

    def set(self, text: str, colors: tuple[str, str]) -> None:
        bg, fg = colors
        self.configure(text=text, bg=bg, fg=fg)


class StatCard(tk.Frame):
    def __init__(self, master, caption: str, **kw):
        super().__init__(master, bg=theme.CARD, highlightthickness=1, highlightbackground=theme.BORDER, **kw)
        self._dot = tk.Label(self, text="●", bg=theme.CARD, fg=theme.FAINT, font=("Segoe UI", 16))
        self._dot.grid(row=0, column=0, rowspan=2, padx=(14, 10), pady=12)
        tk.Label(self, text=caption, bg=theme.CARD, fg=theme.MUTED, font=theme.SMALL, anchor="w").grid(
            row=0, column=1, sticky="sw", padx=(0, 14), pady=(12, 0))
        self._value = tk.Frame(self, bg=theme.CARD)
        self._value.grid(row=1, column=1, sticky="nw", padx=(0, 14), pady=(0, 12))
        self.columnconfigure(1, weight=1)
        self.set_value("—")

    def set_dot(self, color: str) -> None:
        self._dot.configure(fg=color)

    def set_value(self, text: str, color: str = theme.TEXT) -> None:
        self.set_parts((text, color))

    def set_parts(self, *parts: tuple[str, str]) -> None:
        for w in self._value.winfo_children():
            w.destroy()
        for text, color in parts:
            tk.Label(self._value, text=text, bg=theme.CARD, fg=color, font=theme.STAT, padx=0, bd=0).pack(side="left")


def field_row(parent, row: int, caption: str, widget: tk.Widget, column: int = 0, pady=(0, 6)) -> None:
    """Một hàng nhãn trên / ô nhập dưới trong lưới 2 cột."""
    ttk.Label(parent, text=caption, style="Muted.Card.TLabel").grid(row=row * 2, column=column, sticky="w", padx=(0, 8))
    widget.grid(row=row * 2 + 1, column=column, sticky="ew", padx=(0, 8), pady=pady)


def int_of(var: tk.Variable, lo: int, hi: int, default: int) -> int:
    """Đọc số nguyên từ Spinbox/Entry và kẹp vào [lo, hi]."""
    try:
        v = int(str(var.get()).strip())
    except (ValueError, tk.TclError):
        v = default
    return max(lo, min(hi, v))
