from __future__ import annotations

import threading
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk
from typing import Callable
from urllib.parse import urlparse

from .. import verify_api
from ..models import AccessEvent, VerifyApiSettings
from ..rtlog import event_name
from . import theme
from .widgets import Card, int_of

_ON_ERROR = ["Hỏi người vận hành (popup)", "Từ chối"]


class VerifySettingsDialog(tk.Toplevel):
    """Cài đặt Verify API QR/Card: URL, Headers, Body data và quy tắc áp dụng. Kết quả ở ``self.result``."""

    def __init__(self, master, settings: VerifyApiSettings, device_serial: Callable[[], str]):
        super().__init__(master, bg=theme.BG)
        self.result: VerifyApiSettings | None = None
        self._device_serial = device_serial
        s = settings

        self.title("Cài đặt xác thực QR / Card")
        self.transient(master)
        self.resizable(False, True)

        self.v_enabled = tk.BooleanVar(value=s.enabled)
        self.v_method = tk.StringVar(value=s.method.upper() if s.method.upper() in ("POST", "PUT", "GET") else "POST")
        self.v_url = tk.StringVar(value=s.url)
        self.v_timeout = tk.StringVar(value=str(s.timeout_ms))
        self.v_field = tk.StringVar(value=s.result_field)
        self.v_on_error = tk.StringVar(value=_ON_ERROR[0 if s.prompt_on_error else 1])
        self.v_skip = tk.BooleanVar(value=s.skip_granted)
        self.v_open = tk.StringVar(value=str(s.open_seconds))
        self.v_dup = tk.StringVar(value=str(s.duplicate_window_seconds))
        self.v_prompt = tk.StringVar(value=str(s.prompt_timeout_seconds))

        # Thanh nút pack trước để luôn hiện kể cả khi màn hình thấp.
        bar = tk.Frame(self, bg=theme.CARD, highlightthickness=1, highlightbackground=theme.BORDER)
        bar.pack(fill="x", side="bottom")
        content = ttk.Frame(self, padding=(16, 12, 16, 12))
        content.pack(fill="both", expand=True)

        api = Card(content, "Verify API")
        api.pack(fill="x")
        g = api.body
        g.columnconfigure(1, weight=1)
        ttk.Checkbutton(g, text="Bật xác thực qua API (tắt hoặc để trống URL → hỏi người vận hành bằng popup)",
                        variable=self.v_enabled, style="Card.TCheckbutton", command=self._toggle).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

        self._api_widgets: list[tk.Widget] = []
        r = 1
        r = self._row(g, r, "URL", ttk.Entry(g, textvariable=self.v_url, width=70))
        r = self._row(g, r, "Phương thức", ttk.Combobox(g, textvariable=self.v_method, values=["POST", "PUT", "GET"],
                                                        state="readonly", width=10), sticky="w")
        self.txt_headers = tk.Text(g, height=3, width=70, font=theme.MONO, bg=theme.INPUT_BG, relief="solid", bd=1,
                                   wrap="none", undo=True)
        self.txt_headers.insert("1.0", s.headers)
        r = self._row(g, r, "Headers\n(mỗi dòng Tên: Giá trị)", self.txt_headers)
        self.txt_body = tk.Text(g, height=9, width=70, font=theme.MONO, bg=theme.INPUT_BG, relief="solid", bd=1,
                                wrap="none", undo=True)
        self.txt_body.insert("1.0", s.body)
        r = self._row(g, r, "Body data\n(bỏ trống nếu GET)", self.txt_body)
        ttk.Label(g, style="Muted.Card.TLabel", wraplength=520, text=(
            "Biến dùng được trong URL, Headers, Body: {code} {pin} {door} {direction} {eventType} {eventName} "
            "{time} {deviceSerial}")).grid(row=r, column=1, sticky="w", pady=(0, 8))
        r += 1
        r = self._row(g, r, "Timeout (ms)", ttk.Spinbox(g, textvariable=self.v_timeout, from_=500, to=60000,
                                                        increment=500, width=10), sticky="w")
        r = self._row(g, r, "Trường kết quả JSON", ttk.Entry(g, textvariable=self.v_field, width=20, font=theme.MONO),
                      sticky="w")
        r = self._row(g, r, "Khi API lỗi", ttk.Combobox(g, textvariable=self.v_on_error, values=_ON_ERROR,
                                                        state="readonly", width=28), sticky="w")
        ttk.Label(g, style="Muted.Card.TLabel", wraplength=520, text=(
            'Response mong đợi: { "allow": true, "message": "...", "openSeconds": 5 } — '
            "trường kết quả hỗ trợ dạng lồng như data.allow")).grid(row=r, column=1, sticky="w")

        apply = Card(content, "Áp dụng")
        apply.pack(fill="x", pady=(10, 0))
        a = apply.body
        ttk.Checkbutton(a, text="Bỏ qua lượt quét controller đã cho phép (chỉ xác thực thẻ/QR bị từ chối)",
                        variable=self.v_skip, style="Card.TCheckbutton").grid(row=0, column=0, columnspan=2,
                                                                                sticky="w", pady=(0, 10))
        for i, (caption, var, lo, hi) in enumerate([("Mở cửa (giây)", self.v_open, 1, 254),
                                                     ("Bỏ quét trùng (giây)", self.v_dup, 0, 60),
                                                     ("Popup tự đóng (giây)", self.v_prompt, 5, 300)], start=1):
            ttk.Label(a, text=caption, style="Muted.Card.TLabel").grid(row=i, column=0, sticky="w", padx=(0, 12), pady=3)
            ttk.Spinbox(a, textvariable=var, from_=lo, to=hi, width=10).grid(row=i, column=1, sticky="w", pady=3)

        self.btn_test = ttk.Button(bar, text="Kiểm tra API", command=self._test)
        self.btn_test.pack(side="left", padx=(16, 0), pady=12)
        self.lbl_test = tk.Label(bar, bg=theme.CARD, fg=theme.MUTED, font=theme.SMALL, wraplength=360, justify="left")
        self.lbl_test.pack(side="left", padx=10)
        ttk.Button(bar, text="Huỷ", command=self.destroy).pack(side="right", padx=(0, 16), pady=12)
        ttk.Button(bar, text="Lưu", style="Primary.TButton", command=self._save).pack(side="right", padx=(0, 8))

        self.bind("<Escape>", lambda _: self.destroy())
        self._toggle()
        self.grab_set()
        self.focus_set()

    def _row(self, g, r: int, caption: str, widget: tk.Widget, sticky: str = "ew") -> int:
        ttk.Label(g, text=caption, style="Muted.Card.TLabel", justify="left").grid(
            row=r, column=0, sticky="nw", padx=(0, 12), pady=(4, 8))
        widget.grid(row=r, column=1, sticky=sticky, pady=(0, 8))
        self._api_widgets.append(widget)
        return r + 1

    def _toggle(self) -> None:
        enabled = self.v_enabled.get()
        for w in self._api_widgets:
            if isinstance(w, tk.Text):
                w.configure(state="normal" if enabled else "disabled", fg=theme.TEXT if enabled else theme.FAINT)
            elif isinstance(w, ttk.Combobox):
                w.configure(state="readonly" if enabled else "disabled")
            else:
                w.configure(state="normal" if enabled else "disabled")

    def _read(self) -> VerifyApiSettings:
        return VerifyApiSettings(
            enabled=self.v_enabled.get(),
            method=self.v_method.get() or "POST",
            url=self.v_url.get().strip(),
            headers=self.txt_headers.get("1.0", "end-1c"),
            body=self.txt_body.get("1.0", "end-1c"),
            timeout_ms=int_of(self.v_timeout, 500, 60000, 3000),
            result_field=self.v_field.get().strip() or "allow",
            prompt_on_error=self.v_on_error.get() == _ON_ERROR[0],
            skip_granted=self.v_skip.get(),
            open_seconds=int_of(self.v_open, 1, 254, 5),
            duplicate_window_seconds=int_of(self.v_dup, 0, 60, 3),
            prompt_timeout_seconds=int_of(self.v_prompt, 5, 300, 20),
        )

    def _save(self) -> None:
        s = self._read()
        if s.enabled and not s.is_configured:
            messagebox.showwarning(self.title(), "URL không hợp lệ (cần http:// hoặc https://).", parent=self)
            return
        self.result = s
        self.destroy()

    def _test(self) -> None:
        s = self._read()
        u = urlparse(s.url)
        if u.scheme not in ("http", "https") or not u.netloc:
            self._show_test(False, "Nhập URL hợp lệ trước.")
            return

        sample = AccessEvent(time=datetime.now(), door=1, direction="Vào", code="TEST-QR-0001", pin="0",
                             event_type=27, event_name=event_name(27))
        serial = self._device_serial()
        self.btn_test.state(["disabled"])
        self._show_test(None, "Đang gọi API...")

        def work():
            r = verify_api.verify(s, sample, serial)
            text = (f"✓ {r.status_code} OK · {s.result_field}={str(r.allow).lower()} · {r.elapsed_ms} ms"
                    + (f" · {r.message}" if r.message else "")) if r.success else f"✗ {r.error} ({r.elapsed_ms} ms)"
            self.after(0, lambda: self._test_done(r.success, text))

        threading.Thread(target=work, daemon=True).start()

    def _test_done(self, ok: bool, text: str) -> None:
        if not self.winfo_exists():
            return
        self.btn_test.state(["!disabled"])
        self._show_test(ok, text)

    def _show_test(self, ok: bool | None, text: str) -> None:
        color = theme.SUCCESS_TEXT if ok else theme.DANGER_TEXT if ok is False else theme.MUTED
        self.lbl_test.configure(text=text, fg=color)
