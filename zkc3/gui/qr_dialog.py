"""
Popup xem lại một lượt quét: vẽ lại mã QR từ nội dung đã ghi, kèm chi tiết sự kiện,
sao chép mã và lưu ảnh PNG. Cần ``pip install qrcode[pil]`` để hiện ảnh QR.
"""

from __future__ import annotations

import re
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ..models import AccessEvent
from . import theme
from .widgets import Card, Pill

QR_BOX = 300

try:
    import qrcode
    from PIL import ImageTk
except ImportError:  # thư viện tuỳ chọn
    qrcode = None


def render_qr(text: str, max_size: int):
    """Ảnh PIL mã QR vừa khít ``max_size`` px, mỗi module là số nguyên pixel để ảnh sắc nét."""
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=4, box_size=1)
    qr.add_data(text)
    qr.make(fit=True)
    modules = qr.modules_count + 2 * qr.border
    qr.box_size = max(1, max_size // modules)
    return qr.make_image(fill_color="black", back_color="white").get_image()


class QrDetailDialog(tk.Toplevel):
    def __init__(self, master, e: AccessEvent):
        super().__init__(master, bg=theme.BG)
        self._event = e
        self.title(f"Mã QR — {e.code}")
        self.resizable(False, False)
        self.transient(master)

        body = ttk.Frame(self, padding=16)
        body.pack(fill="both", expand=True)

        qr_card = Card(body)
        qr_card.pack(side="left", fill="y", padx=(0, 16))
        self._photo = None
        if qrcode is None:
            tk.Label(qr_card.body, text="Cài thư viện để xem ảnh QR:\n\npip install qrcode[pil]", bg=theme.CARD,
                     fg=theme.MUTED, width=34, height=14).pack()
        else:
            self._photo = ImageTk.PhotoImage(render_qr(e.code, QR_BOX))
            tk.Label(qr_card.body, image=self._photo, bg="white", width=QR_BOX, height=QR_BOX).pack()

        detail = Card(body, "Chi tiết lượt quét")
        detail.pack(side="left", fill="both")
        d = detail.body
        tk.Label(d, text="NỘI DUNG MÃ", bg=theme.CARD, fg=theme.MUTED, font=theme.SMALL_BOLD).pack(anchor="w")
        code = tk.Text(d, height=2, width=30, font=("Consolas", 12, "bold"), bg=theme.INPUT_BG, relief="solid", bd=1,
                       wrap="char")
        code.insert("1.0", e.code)
        code.configure(state="disabled")
        code.pack(anchor="w", pady=(6, 12))

        colors = ((theme.WARNING_TINT, theme.WARNING_TEXT) if e.pending
                  else (theme.SUCCESS_TINT, theme.SUCCESS_TEXT) if e.door_opened
                  else (theme.DANGER_TINT, theme.DANGER_TEXT))
        Pill(d, e.result, colors).pack(anchor="w", pady=(0, 12))

        info = tk.Frame(d, bg=theme.CARD)
        info.pack(anchor="w")
        for i, (caption, value) in enumerate([
            ("Thời gian", f"{e.time:%Y-%m-%d %H:%M:%S}"), ("Cửa", f"{e.door} ({e.direction})"), ("PIN", e.pin),
            ("Controller", e.event_name), ("Xác thực", e.verify_note or "—"),
        ]):
            tk.Label(info, text=caption, bg=theme.CARD, fg=theme.MUTED, font=theme.SMALL).grid(
                row=i, column=0, sticky="nw", padx=(0, 16), pady=3)
            tk.Label(info, text=value, bg=theme.CARD, fg=theme.TEXT, wraplength=220, justify="left").grid(
                row=i, column=1, sticky="w", pady=3)

        tk.Label(d, bg=theme.CARD, fg=theme.FAINT, font=theme.SMALL, wraplength=320, justify="left", text=(
            "Ảnh QR được tạo lại từ nội dung mã đã ghi nhận, nên có thể khác hình dáng mã gốc nhưng chứa cùng nội dung."
        )).pack(anchor="w", pady=(10, 0))

        bar = tk.Frame(self, bg=theme.CARD, highlightthickness=1, highlightbackground=theme.BORDER)
        bar.pack(fill="x")
        ttk.Button(bar, text="Sao chép mã", command=self._copy).pack(side="left", padx=(16, 8), pady=12)
        save = ttk.Button(bar, text="Lưu ảnh PNG", command=self._save)
        save.pack(side="left")
        if qrcode is None:
            save.state(["disabled"])
        self._status = tk.Label(bar, bg=theme.CARD, fg=theme.SUCCESS_TEXT, font=theme.SMALL)
        self._status.pack(side="left", padx=12)
        close = ttk.Button(bar, text="Đóng", style="Primary.TButton", command=self.destroy)
        close.pack(side="right", padx=16)

        self.bind("<Escape>", lambda _: self.destroy())
        self.bind("<Control-c>", lambda _: self._copy())
        self.grab_set()
        close.focus_set()

    def _copy(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(self._event.code)
        self._status.configure(text="Đã sao chép mã")

    def _save(self) -> None:
        e = self._event
        safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", e.code)
        path = filedialog.asksaveasfilename(parent=self, defaultextension=".png", filetypes=[("Ảnh PNG", "*.png")],
                                            initialfile=f"qr_{safe}_{e.time:%Y%m%d_%H%M%S}.png")
        if not path:
            return
        try:
            render_qr(e.code, 800).save(path, "PNG")
            self._status.configure(text="Đã lưu ảnh")
        except OSError as ex:
            messagebox.showerror("Lưu ảnh", str(ex), parent=self)
