"""Bảng màu, font và style ttk dùng chung (cùng bảng màu với bản WinForms)."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

NAVY = "#0F1B2D"
NAVY_HOVER = "#1E2A3D"
NAVY_TEXT = "#CBD5E1"
NAVY_MUTED = "#94A3B8"

BG = "#F4F6FA"
CARD = "#FFFFFF"
BORDER = "#E3E8EF"
DIVIDER = "#F1F5F9"
INPUT_BG = "#F8FAFC"

TEXT = "#0F172A"
TEXT_SOFT = "#334155"
MUTED = "#64748B"
FAINT = "#94A3B8"

PRIMARY = "#2563EB"
PRIMARY_HOVER = "#1D4ED8"
PRIMARY_TINT = "#DBEAFE"
PRIMARY_TEXT = "#1D4ED8"
SELECTION = "#EFF6FF"

SUCCESS = "#16A34A"
SUCCESS_TINT = "#DCFCE7"
SUCCESS_TEXT = "#15803D"

DANGER = "#DC2626"
DANGER_TINT = "#FEE2E2"
DANGER_TEXT = "#B91C1C"

WARNING = "#D97706"
WARNING_TINT = "#FEF3C7"
WARNING_TEXT = "#B45309"

CONSOLE_BG = "#0B1220"
CONSOLE_TEXT = "#CBD5E1"
CONSOLE_TIME = "#64748B"
LOG_INFO = "#38BDF8"
LOG_WARN = "#FBBF24"
LOG_ERROR = "#F87171"
LOG_DEBUG = "#64748B"

# Pill trạng thái trên header navy.
PILL_ONLINE = ("#123635", "#4ADE80")
PILL_OFFLINE = ("#342938", "#F87171")
PILL_BUSY = ("#35352C", "#FBBF24")

UI = ("Segoe UI", 10)
UI_BOLD = ("Segoe UI Semibold", 10)
SMALL = ("Segoe UI", 9)
SMALL_BOLD = ("Segoe UI Semibold", 9)
CARD_TITLE = ("Segoe UI Semibold", 10)
APP_TITLE = ("Segoe UI Semibold", 12)
STAT = ("Segoe UI", 15, "bold")
MONO = ("Consolas", 10)
MONO_BOLD = ("Consolas", 11, "bold")


def apply_style(root: tk.Misc) -> ttk.Style:
    style = ttk.Style(root)
    style.theme_use("clam")
    root.option_add("*Font", UI)

    style.configure(".", background=BG, foreground=TEXT, font=UI, bordercolor=BORDER,
                    lightcolor=BORDER, darkcolor=BORDER, troughcolor=DIVIDER, focuscolor=PRIMARY)
    style.configure("Card.TFrame", background=CARD)
    style.configure("Card.TLabel", background=CARD, foreground=TEXT)
    style.configure("Muted.Card.TLabel", background=CARD, foreground=MUTED, font=SMALL)
    style.configure("Value.Card.TLabel", background=CARD, foreground=TEXT, font=MONO)
    style.configure("Card.TCheckbutton", background=CARD, foreground=TEXT)
    style.map("Card.TCheckbutton", background=[("active", CARD)])

    style.configure("TEntry", fieldbackground=INPUT_BG, padding=4)
    style.configure("TSpinbox", fieldbackground=INPUT_BG, padding=3, arrowsize=12)
    style.configure("TCombobox", fieldbackground=INPUT_BG, padding=3)
    style.map("TCombobox", fieldbackground=[("readonly", INPUT_BG)], foreground=[("disabled", FAINT)])

    style.configure("TButton", background=DIVIDER, foreground=TEXT, bordercolor=BORDER, padding=(12, 6), relief="flat")
    style.map("TButton", background=[("disabled", INPUT_BG), ("pressed", BORDER), ("active", "#E8EDF3")],
              foreground=[("disabled", FAINT)])
    style.configure("Primary.TButton", background=PRIMARY, foreground="white", bordercolor=PRIMARY,
                    font=UI_BOLD, padding=(14, 7))
    style.map("Primary.TButton", background=[("disabled", "#93C5FD"), ("pressed", PRIMARY_HOVER), ("active", PRIMARY_HOVER)],
              foreground=[("disabled", "white")])
    style.configure("Danger.TButton", background="#FEF2F2", foreground=DANGER_TEXT, bordercolor="#FCA5A5",
                    font=UI_BOLD, padding=(14, 7))
    style.map("Danger.TButton", background=[("pressed", DANGER_TINT), ("active", DANGER_TINT)])
    style.configure("Header.TButton", background=NAVY, foreground=NAVY_TEXT, bordercolor=NAVY, padding=(10, 5))
    style.map("Header.TButton", background=[("pressed", NAVY_HOVER), ("active", NAVY_HOVER)],
              foreground=[("active", "white")])

    style.configure("Treeview", background=CARD, fieldbackground=CARD, foreground=TEXT, rowheight=30, borderwidth=0)
    style.configure("Treeview.Heading", background=INPUT_BG, foreground=MUTED, font=SMALL_BOLD, relief="flat",
                    padding=(6, 6))
    style.map("Treeview", background=[("selected", SELECTION)], foreground=[("selected", TEXT)])
    style.map("Treeview.Heading", background=[("active", DIVIDER)])

    style.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(0, 0, 0, 0))
    style.configure("TNotebook.Tab", background=BG, foreground=MUTED, padding=(16, 7), font=UI_BOLD, borderwidth=0)
    style.map("TNotebook.Tab", background=[("selected", CARD)], foreground=[("selected", TEXT)])
    return style
