"""
Cửa sổ chính. Tkinter chỉ được chạm từ thread chính: callback từ thread polling /
thread xác thực được đẩy vào hàng đợi và chạy trong vòng ``_drain_ui_queue``.
"""

from __future__ import annotations

import ipaddress
import os
import queue
import sys
import threading
import time
import tkinter as tk
from datetime import datetime
from functools import partial
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from .. import rtlog, verify_api
from ..controller import C3Controller, ConnectionState
from ..csv_writer import EventCsvWriter
from ..logger import AppLogger
from ..models import AccessEvent, ConnectionSettings, DeviceInfo, DoorStatus, LogEntry, LogLevel
from ..sdk import PullSdk
from ..settings import AppSettings, home_dir
from . import theme
from .prompt_dialog import OpenDoorPrompt
from .qr_dialog import QrDetailDialog
from .verify_settings import VerifySettingsDialog
from .widgets import Card, Pill, StatCard, field_row, int_of

MAX_GRID_ROWS = 5000
MAX_LOG_LINES = 3000

_ROW_TAGS = {"pending": "#FFFBEB", "ok": "#F0FDF4", "deny": "#FEF2F2"}
_LOG_COLORS = {LogLevel.DEBUG: theme.LOG_DEBUG, LogLevel.INFO: theme.LOG_INFO,
               LogLevel.WARN: theme.LOG_WARN, LogLevel.ERROR: theme.LOG_ERROR}


class MainWindow:
    def __init__(self, root: tk.Tk, simulate: bool = False, sdk_dir: str | None = None):
        self.root = root
        self.simulate = simulate
        self.log_dir = home_dir() / "logs"
        self.settings = AppSettings.load()
        self.logger = AppLogger(self.log_dir)
        self.event_writer = EventCsvWriter(self.log_dir)

        if simulate:
            from ..simulator import FakePullSdk
            sdk_factory = FakePullSdk
        else:
            sdk_factory = partial(PullSdk, sdk_dir)
        self.device = C3Controller(self.logger, sdk_factory)

        self._ui_queue: queue.SimpleQueue = queue.SimpleQueue()
        self._events: list[AccessEvent] = []          # mới nhất ở đầu
        self._iid_of: dict[int, str] = {}             # id(event) -> iid trong Treeview
        self._event_of: dict[str, AccessEvent] = {}
        self._log_history: list[LogEntry] = []
        self._last_scan: dict[str, float] = {}
        self._prompt_gate = threading.Lock()
        self._waiting_lock = threading.Lock()
        self._prompt_waiting = 0
        self._device_serial = ""
        self._granted = self._denied = 0
        self._closing = False
        self._destroyed = False

        theme.apply_style(root)
        root.title("ZKTeco C3-100 Manager" + (" — GIẢ LẬP" if simulate else ""))
        root.configure(bg=theme.BG)
        root.geometry("1320x900")
        root.minsize(1120, 880)
        self._build_layout()

        self.logger.subscribe(lambda e: self.ui(self._append_log, e))
        self.device.state_changed.connect(lambda s: self.ui(self._apply_state, s))
        self.device.events_received.connect(lambda lst: self.ui(self._on_events, lst))
        self.device.status_received.connect(lambda st: self.ui(self._on_door_status, st))
        self.device.device_info_received.connect(lambda info: self.ui(self._show_device_info, info))

        root.bind("<F5>", lambda _: self._connect())
        root.bind("<Shift-F5>", lambda _: self._disconnect())
        root.bind("<Control-s>", lambda _: self._export_csv())
        root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._load_settings()
        self._apply_state(ConnectionState.DISCONNECTED)
        self._update_counters()
        self._update_verify_info()
        self.st_files.configure(text=f"Log: {self.logger.current_file}   ·   Events: {self.event_writer.current_file}")

        arch = "x64" if sys.maxsize > 2**32 else "x86"
        self.logger.info(f"Khởi động ứng dụng (Python {sys.version.split()[0]} {arch}"
                         f"{', giả lập' if simulate else ''}), thư mục log: {self.log_dir}")
        root.after(50, self._drain_ui_queue)

    # ---------------------------------------------------------------- dựng giao diện

    def _build_layout(self) -> None:
        r = self.root

        header = tk.Frame(r, bg=theme.NAVY, height=56)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="ZKTeco C3-100 Manager", bg=theme.NAVY, fg="white", font=theme.APP_TITLE).pack(
            side="left", padx=(18, 8))
        tk.Label(header, text="PullSDK · Python" + (" · GIẢ LẬP" if self.simulate else ""), bg=theme.NAVY,
                 fg=theme.NAVY_MUTED, font=theme.SMALL).pack(side="left", pady=(4, 0))
        ttk.Button(header, text="Giới thiệu", style="Header.TButton", command=self._about).pack(side="right", padx=(0, 14))
        ttk.Button(header, text="Thư mục log", style="Header.TButton", command=self._open_log_dir).pack(side="right", padx=4)
        ttk.Button(header, text="Cài đặt xác thực", style="Header.TButton", command=self._open_verify_settings).pack(
            side="right", padx=4)
        self.pill_conn = Pill(header, colors=theme.PILL_OFFLINE)
        self.pill_conn.pack(side="right", padx=12)

        status = tk.Frame(r, bg=theme.CARD, highlightthickness=1, highlightbackground=theme.BORDER)
        status.pack(fill="x", side="bottom")
        self.st_conn = tk.Label(status, bg=theme.CARD, fg=theme.TEXT_SOFT, font=theme.SMALL)
        self.st_conn.pack(side="left", padx=(12, 16), pady=4)
        self.st_poll = tk.Label(status, bg=theme.CARD, fg=theme.MUTED, font=theme.SMALL)
        self.st_poll.pack(side="left", padx=(0, 16))
        self.st_files = tk.Label(status, bg=theme.CARD, fg=theme.FAINT, font=theme.SMALL)
        self.st_files.pack(side="right", padx=12)

        body = ttk.Frame(r, padding=14)
        body.pack(fill="both", expand=True)
        left = ttk.Frame(body, width=330)
        left.pack(side="left", fill="y", padx=(0, 14))
        left.pack_propagate(False)
        right = ttk.Frame(body)
        right.pack(side="left", fill="both", expand=True)

        self._build_connection_card(left)
        self._build_device_card(left)
        self._build_door_card(left)
        self._build_verify_card(left)
        self._build_right(right)

    def _build_connection_card(self, parent) -> None:
        card = Card(parent, "Kết nối")
        card.pack(fill="x")
        g = card.body
        g.columnconfigure(0, weight=3)
        g.columnconfigure(1, weight=2)
        self.v_ip, self.v_port = tk.StringVar(), tk.StringVar()
        self.v_timeout, self.v_password = tk.StringVar(), tk.StringVar()
        self.v_poll, self.v_auto = tk.StringVar(), tk.BooleanVar()

        self.txt_ip = ttk.Entry(g, textvariable=self.v_ip, font=theme.MONO)
        self.num_port = ttk.Spinbox(g, textvariable=self.v_port, from_=1, to=65535, width=7)
        self.num_timeout = ttk.Spinbox(g, textvariable=self.v_timeout, from_=1000, to=30000, increment=500, width=7)
        self.txt_password = ttk.Entry(g, textvariable=self.v_password, show="•")
        self.num_poll = ttk.Spinbox(g, textvariable=self.v_poll, from_=100, to=10000, increment=100, width=7)
        field_row(g, 0, "Địa chỉ IP", self.txt_ip)
        field_row(g, 0, "Cổng", self.num_port, column=1)
        field_row(g, 1, "Mật khẩu (comm key)", self.txt_password)
        field_row(g, 1, "Timeout (ms)", self.num_timeout, column=1)
        field_row(g, 2, "Chu kỳ đọc (ms)", self.num_poll)
        self.chk_auto = ttk.Checkbutton(g, text="Tự kết nối lại", variable=self.v_auto, style="Card.TCheckbutton")
        self.chk_auto.grid(row=5, column=1, sticky="w", pady=(0, 6))
        self.btn_connect = ttk.Button(g, text="Kết nối", style="Primary.TButton", command=self._toggle_connect)
        self.btn_connect.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        self._conn_inputs = [self.txt_ip, self.num_port, self.num_timeout, self.txt_password, self.num_poll, self.chk_auto]

    def _build_device_card(self, parent) -> None:
        card = Card(parent, "Thiết bị")
        card.pack(fill="x", pady=(10, 0))
        g = card.body
        g.columnconfigure(1, weight=1)
        self.lbl_serial, self.lbl_firmware, self.lbl_doors, self.lbl_devtime = (
            ttk.Label(g, text="—", style="Value.Card.TLabel") for _ in range(4))
        for i, (caption, lbl) in enumerate([("Serial", self.lbl_serial), ("Firmware", self.lbl_firmware),
                                            ("Số cửa", self.lbl_doors), ("Giờ thiết bị", self.lbl_devtime)]):
            ttk.Label(g, text=caption, style="Muted.Card.TLabel").grid(row=i, column=0, sticky="w", padx=(0, 12), pady=2)
            lbl.grid(row=i, column=1, sticky="w", pady=1)
        self.btn_sync = ttk.Button(g, text="Đồng bộ giờ PC → thiết bị",
                                   command=lambda: self._run_guarded(self.btn_sync, self.device.sync_time))
        self.btn_sync.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(8, 0))

    def _build_door_card(self, parent) -> None:
        card = Card(parent, "Điều khiển cửa")
        card.pack(fill="x", pady=(10, 0))
        g = card.body
        g.columnconfigure((0, 1), weight=1)
        self.v_door = tk.StringVar(value="1")
        self.v_open_seconds = tk.StringVar()
        self.cbo_door = ttk.Combobox(g, textvariable=self.v_door, values=["1"], state="readonly", width=6)
        field_row(g, 0, "Cửa", self.cbo_door)
        field_row(g, 0, "Mở (giây)", ttk.Spinbox(g, textvariable=self.v_open_seconds, from_=1, to=254, width=7),
                  column=1)
        self.btn_open = ttk.Button(g, text="Mở cửa", style="Primary.TButton", command=lambda: self._run_guarded(
            self.btn_open, lambda: self.device.set_door(self._selected_door(), int_of(self.v_open_seconds, 1, 254, 5))))
        self.btn_open.grid(row=2, column=0, sticky="ew", padx=(0, 4))
        self.btn_close = ttk.Button(g, text="Đóng cửa", command=lambda: self._run_guarded(
            self.btn_close, lambda: self.device.set_door(self._selected_door(), 0)))
        self.btn_close.grid(row=2, column=1, sticky="ew", padx=(4, 0))

    def _build_verify_card(self, parent) -> None:
        card = Card(parent, "Xác thực QR / Card")
        card.pack(fill="x", pady=(10, 0))
        g = card.body
        g.columnconfigure(0, weight=1)
        self.pill_verify = Pill(g)
        self.pill_verify.grid(row=0, column=0, sticky="w")
        ttk.Button(g, text="Cài đặt...", command=self._open_verify_settings).grid(row=0, column=1, sticky="e")
        self.lbl_verify_url = ttk.Label(g, style="Muted.Card.TLabel", wraplength=290)
        self.lbl_verify_url.grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))

    def _build_right(self, parent) -> None:
        stats = ttk.Frame(parent)
        stats.pack(fill="x")
        self.stat_status = StatCard(stats, "Trạng thái")
        self.stat_scans = StatCard(stats, "Tổng lượt quét")
        self.stat_ok_deny = StatCard(stats, "Hợp lệ / Từ chối")
        self.stat_door = StatCard(stats, "Cửa 1")
        for i, s in enumerate([self.stat_status, self.stat_scans, self.stat_ok_deny, self.stat_door]):
            stats.columnconfigure(i, weight=1, uniform="stat")
            s.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 6, 0 if i == 3 else 6))
        self.stat_scans.set_dot(theme.PRIMARY)
        self.stat_ok_deny.set_dot(theme.SUCCESS)

        toolbar = ttk.Frame(parent)
        toolbar.pack(fill="x", pady=(14, 6))
        ttk.Button(toolbar, text="Xoá", command=self._clear_current_tab).pack(side="right")
        ttk.Button(toolbar, text="Xuất CSV  (Ctrl+S)", command=self._export_csv).pack(side="right", padx=(0, 8))
        self.v_debug = tk.BooleanVar(value=False)
        self.chk_debug = ttk.Checkbutton(toolbar, text="Hiện DEBUG", variable=self.v_debug, command=self._redraw_log)
        self.chk_debug.pack(side="right", padx=(0, 12))

        self.tabs = ttk.Notebook(parent)
        self.tabs.pack(fill="both", expand=True)
        self.tabs.bind("<<NotebookTabChanged>>", lambda _: self._on_tab_changed())

        events_tab = tk.Frame(self.tabs, bg=theme.CARD)
        columns = [("time", "Thời gian", 140), ("door", "Cửa", 64), ("code", "Mã QR / Card", 170), ("pin", "PIN", 50),
                   ("event", "Sự kiện controller", 160), ("verify", "Xác thực", 190), ("result", "Kết quả", 110)]
        self.grid_events = ttk.Treeview(events_tab, columns=[c[0] for c in columns], show="headings", selectmode="browse")
        for key, caption, width in columns:
            self.grid_events.heading(key, text=caption, anchor="w")
            self.grid_events.column(key, width=width, minwidth=50, anchor="w", stretch=key in ("code", "verify"))
        for tag, bg in _ROW_TAGS.items():
            self.grid_events.tag_configure(tag, background=bg)
        sb = ttk.Scrollbar(events_tab, orient="vertical", command=self.grid_events.yview)
        self.grid_events.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.grid_events.pack(fill="both", expand=True)
        self.grid_events.bind("<Double-1>", lambda e: self._show_qr_detail(self.grid_events.identify_row(e.y)))
        self.grid_events.bind("<Return>", lambda _: self._show_qr_detail(self.grid_events.focus()))
        self.tabs.add(events_tab, text="Sự kiện quét QR")

        log_tab = tk.Frame(self.tabs, bg=theme.CONSOLE_BG)
        self.txt_log = tk.Text(log_tab, bg=theme.CONSOLE_BG, fg=theme.CONSOLE_TEXT, font=theme.MONO, relief="flat",
                               bd=0, padx=12, pady=10, wrap="word", insertbackground=theme.CONSOLE_TEXT)
        self.txt_log.tag_configure("time", foreground=theme.CONSOLE_TIME)
        for level, color in _LOG_COLORS.items():
            self.txt_log.tag_configure(level.name, foreground=color)
        lsb = ttk.Scrollbar(log_tab, orient="vertical", command=self.txt_log.yview)
        self.txt_log.configure(yscrollcommand=lsb.set, state="disabled")
        lsb.pack(side="right", fill="y")
        self.txt_log.pack(fill="both", expand=True)
        self.tabs.add(log_tab, text="Log kết nối")
        self._on_tab_changed()

    # ---------------------------------------------------------------- luồng UI

    def ui(self, fn: Callable, *args) -> None:
        """Gọi ``fn(*args)`` trên thread chính (an toàn khi gọi từ bất kỳ thread nào)."""
        self._ui_queue.put((fn, args))

    def _drain_ui_queue(self) -> None:
        try:
            while True:
                fn, args = self._ui_queue.get_nowait()
                try:
                    fn(*args)
                except tk.TclError:
                    pass  # widget đã bị huỷ
        except queue.Empty:
            pass
        if not self._destroyed:
            self.root.after(50, self._drain_ui_queue)

    def _run_bg(self, work: Callable, done: Callable | None = None) -> None:
        def runner():
            result = work()
            if done:
                self.ui(done, result)
        threading.Thread(target=runner, daemon=True).start()

    def _run_guarded(self, button: ttk.Button, action: Callable[[], bool]) -> None:
        button.state(["disabled"])
        self._run_bg(action, lambda _: self.device.is_connected and button.state(["!disabled"]))

    def _selected_door(self) -> int:
        try:
            return int(self.v_door.get())
        except ValueError:
            return 1

    # ---------------------------------------------------------------- kết nối

    def _toggle_connect(self) -> None:
        if self.device.state == ConnectionState.DISCONNECTED:
            self._connect()
        else:
            self._disconnect()

    def _connect(self) -> None:
        if self.device.state != ConnectionState.DISCONNECTED:
            return
        ip = self.v_ip.get().strip()
        try:
            ipaddress.ip_address(ip)
        except ValueError:
            messagebox.showwarning("Kết nối", "Địa chỉ IP không hợp lệ.", parent=self.root)
            self.txt_ip.focus_set()
            return

        self._save_settings()
        s = self.settings
        conn = ConnectionSettings(ip, s.port, s.timeout_ms, self.v_password.get(), s.poll_interval_ms, s.auto_reconnect)

        def done(ok: bool) -> None:
            if not ok:
                self.tabs.select(1)
                messagebox.showerror("Kết nối", 'Không kết nối được tới thiết bị. Xem tab "Log kết nối" để biết chi tiết.',
                                     parent=self.root)

        self._run_bg(lambda: self.device.connect(conn), done)

    def _disconnect(self) -> None:
        if self.device.state != ConnectionState.DISCONNECTED:
            self.btn_connect.state(["disabled"])
            self._run_bg(self.device.disconnect)

    def _apply_state(self, s: ConnectionState) -> None:
        connected = s == ConnectionState.CONNECTED
        idle = s == ConnectionState.DISCONNECTED

        for b in (self.btn_sync, self.btn_open, self.btn_close):
            b.state(["!disabled"] if connected else ["disabled"])
        for w in self._conn_inputs:
            w.state(["!disabled"] if idle else ["disabled"])

        text, style, enabled = {
            ConnectionState.CONNECTED: ("Ngắt kết nối  (Shift+F5)", "Danger.TButton", True),
            ConnectionState.CONNECTING: ("Đang kết nối...", "Primary.TButton", False),
            ConnectionState.RECONNECTING: ("Dừng kết nối lại", "Danger.TButton", True),
        }.get(s, ("Kết nối  (F5)", "Primary.TButton", True))
        self.btn_connect.configure(text=text, style=style)
        self.btn_connect.state(["!disabled"] if enabled else ["disabled"])

        cs = self.device.settings
        target = f"{cs.ip}:{cs.port}" if cs else ""
        pill = {
            ConnectionState.CONNECTED: (f"Đã kết nối · {target}", theme.PILL_ONLINE),
            ConnectionState.CONNECTING: (f"Đang kết nối · {target}", theme.PILL_BUSY),
            ConnectionState.RECONNECTING: ("Mất kết nối · đang thử lại", theme.PILL_BUSY),
        }.get(s, ("Chưa kết nối", theme.PILL_OFFLINE))
        self.pill_conn.set(*pill)

        stat_text, stat_color = {
            ConnectionState.CONNECTED: ("Online", theme.SUCCESS),
            ConnectionState.CONNECTING: ("Đang kết nối", theme.WARNING),
            ConnectionState.RECONNECTING: ("Kết nối lại", theme.WARNING),
        }.get(s, ("Offline", theme.DANGER))
        self.stat_status.set_dot(stat_color)
        self.stat_status.set_value(stat_text, stat_color)

        self.st_conn.configure(text={
            ConnectionState.CONNECTED: f"Đã kết nối {target}",
            ConnectionState.CONNECTING: f"Đang kết nối {target}...",
            ConnectionState.RECONNECTING: f"Mất kết nối {target}, đang thử lại...",
        }.get(s, "Chưa kết nối"))
        self.st_poll.configure(text=f"Polling: {self.settings.poll_interval_ms} ms" if connected else "Polling: dừng")

        if idle:
            for lbl in (self.lbl_serial, self.lbl_firmware, self.lbl_doors, self.lbl_devtime):
                lbl.configure(text="—")
            self.stat_door.set_dot(theme.WARNING)
            self.stat_door.set_value("—")

    def _show_device_info(self, info: DeviceInfo) -> None:
        self._device_serial = info.serial
        self.lbl_serial.configure(text=info.serial)
        self.lbl_firmware.configure(text=info.firmware)
        self.lbl_doors.configure(text=str(info.lock_count))
        self.lbl_devtime.configure(text=f"{info.device_time:%Y-%m-%d %H:%M:%S}" if info.device_time else "?")
        doors = [str(i) for i in range(1, max(1, info.lock_count) + 1)]
        self.cbo_door.configure(values=doors)
        if self.v_door.get() not in doors:
            self.v_door.set("1")

    # ---------------------------------------------------------------- sự kiện

    def _on_events(self, events: list[AccessEvent]) -> None:
        for e in events:
            if not rtlog.is_scan_event(e):
                # Sự kiện cửa (mở/đóng, nút exit...) không phải lượt quét: chỉ ghi vào log.
                self.logger.info(f"Cửa {e.door}: {e.event_name}")
                continue

            self.logger.info(f"Quét QR cửa {e.door} ({e.direction}): {e.code}, PIN={e.pin}, controller: {e.event_name}")
            v = self.settings.verify
            if e.granted and v.skip_granted:
                e.door_opened = True
                e.verify_note = "Controller"
                self._insert_row(e)
                self._complete(e)
            elif self._is_duplicate(e, v.duplicate_window_seconds):
                e.door_opened = e.granted
                e.verify_note = "Bỏ qua (quét trùng)"
                self._insert_row(e)
                self._complete(e)
            else:
                e.pending = True
                e.verify_note = "Đang xác thực..."
                self._insert_row(e)
                threading.Thread(target=self._verify_and_decide, args=(e,), daemon=True).start()

        while len(self._events) > MAX_GRID_ROWS:
            old = self._events.pop()
            iid = self._iid_of.pop(id(old), None)
            if iid:
                self._event_of.pop(iid, None)
                self.grid_events.delete(iid)
        self._update_counters()

    # ---------------------------------------------------------------- xác thực QR / Card

    def _verify_and_decide(self, e: AccessEvent) -> None:
        """
        (Chạy trên thread phụ.) Có Verify API thì gọi API, chưa cấu hình (hoặc API lỗi và chọn hỏi)
        thì hiện popup cho người vận hành. Cho phép → ControlDevice mở cửa.
        """
        v = self.settings.verify.clone()
        seconds = v.open_seconds
        open_door = False
        note = ""
        try:
            if v.is_configured:
                r = verify_api.verify(v, e, self._device_serial)
                if r.success:
                    open_door = r.allow
                    if r.open_seconds is not None and 0 < r.open_seconds < 255:
                        seconds = r.open_seconds
                    msg = f" — {r.message}" if r.message else ""
                    note = f"API: {v.result_field}={'true' if r.allow else 'false'}{msg}"
                    self.logger.info(f"Verify API {e.code}: HTTP {r.status_code}, allow={r.allow}, {r.elapsed_ms} ms{msg}")
                else:
                    self.logger.warn(f"Verify API lỗi cho {e.code}: {r.error} ({r.elapsed_ms} ms)")
                    if v.prompt_on_error:
                        open_door, note = self._ask_operator(e, f"Verify API lỗi: {r.error}", v.prompt_timeout_seconds)
                        note = "API lỗi → " + note
                    else:
                        note = "API lỗi → từ chối"
            else:
                open_door, note = self._ask_operator(e, "Chưa cấu hình API xác thực.", v.prompt_timeout_seconds)

            e.door_opened = e.granted
            if open_door and not e.granted:
                if not self.device.is_connected:
                    note += " (mất kết nối, không mở được)"
                elif self.device.set_door(e.door if e.door > 0 else 1, seconds):
                    e.door_opened = True
                else:
                    note += " (lệnh mở cửa lỗi)"
            elif not open_door and e.granted:
                note += " (controller đã mở)"
        except Exception as ex:  # noqa: BLE001 - lỗi bất ngờ không được làm treo lượt quét ở trạng thái chờ
            self.logger.error(f"Lỗi xác thực {e.code}: {ex}")
            note = f"Lỗi: {ex}"
        finally:
            self.ui(self._finish_verify, e, note)

    def _finish_verify(self, e: AccessEvent, note: str) -> None:
        e.pending = False
        e.verify_note = note
        self._complete(e)
        self.logger.info(f"Kết quả {e.code}: {e.result} ({note})")
        self._update_counters()

    def _ask_operator(self, e: AccessEvent, reason: str, timeout_seconds: int) -> tuple[bool, str]:
        """(Thread phụ.) Hỏi người vận hành, mỗi lần một popup; các lượt quét khác xếp hàng chờ."""
        queued_at = time.monotonic()
        with self._waiting_lock:
            self._prompt_waiting += 1
        with self._prompt_gate:
            with self._waiting_lock:
                self._prompt_waiting -= 1
            if self._closing:
                return False, "Thủ công: huỷ"
            # Lượt quét đã chờ quá lâu trong hàng đợi thì không còn ý nghĩa mở cửa nữa.
            if time.monotonic() - queued_at > timeout_seconds:
                return False, "Thủ công: hết hạn chờ"

            answered = threading.Event()
            answer = {"open": False, "timed_out": False}

            def on_close(open_door: bool, timed_out: bool) -> None:
                answer.update(open=open_door, timed_out=timed_out)
                answered.set()

            self.ui(lambda: OpenDoorPrompt(self.root, e, reason, timeout_seconds, self._prompt_waiting, on_close))
            while not answered.wait(0.5):
                if self._closing:
                    return False, "Thủ công: huỷ"

            if answer["timed_out"]:
                self.logger.warn(f"Popup xác thực {e.code} hết giờ → từ chối")
                return False, "Thủ công: hết giờ → từ chối"
            open_door = answer["open"]
            self.logger.info(f"Người vận hành {'MỞ' if open_door else 'KHÔNG mở'} cửa {e.door} cho {e.code}")
            return open_door, "Thủ công: mở" if open_door else "Thủ công: không mở"

    def _is_duplicate(self, e: AccessEvent, window_seconds: int) -> bool:
        if window_seconds <= 0:
            return False
        key = f"{e.door}|{e.code}"
        now = time.monotonic()
        last = self._last_scan.get(key)
        if last is not None and now - last < window_seconds:
            return True
        if len(self._last_scan) > 1000:
            self._last_scan = {k: t for k, t in self._last_scan.items() if now - t <= 60}
        self._last_scan[key] = now
        return False

    def _complete(self, e: AccessEvent) -> None:
        """Chốt kết quả cuối của lượt quét: cập nhật lưới, bộ đếm và ghi CSV."""
        if e.door_opened:
            self._granted += 1
        else:
            self._denied += 1
        self._refresh_row(e)
        try:
            self.event_writer.append(e)
        except OSError as ex:
            self.logger.error(f"Không ghi được file sự kiện: {ex}")

    def _insert_row(self, e: AccessEvent) -> None:
        self._events.insert(0, e)
        iid = self.grid_events.insert("", 0, values=self._row_values(e), tags=(self._row_tag(e),))
        self._iid_of[id(e)] = iid
        self._event_of[iid] = e

    def _refresh_row(self, e: AccessEvent) -> None:
        iid = self._iid_of.get(id(e))
        if iid and self.grid_events.exists(iid):
            self.grid_events.item(iid, values=self._row_values(e), tags=(self._row_tag(e),))

    @staticmethod
    def _row_values(e: AccessEvent) -> tuple:
        mark = "◷" if e.pending else "●"
        return (f"{e.time:%Y-%m-%d %H:%M:%S}", e.door_text, e.code, e.pin, e.event_name, e.verify_note,
                f"{mark} {e.result}")

    @staticmethod
    def _row_tag(e: AccessEvent) -> str:
        return "pending" if e.pending else "ok" if e.door_opened else "deny"

    def _on_door_status(self, st: DoorStatus) -> None:
        text, color = {1: ("Đóng", theme.SUCCESS), 2: ("Đang mở", theme.WARNING)}.get(
            st.door1_sensor, ("Không sensor", theme.FAINT))
        self.stat_door.set_dot(color)
        self.stat_door.set_value(text, theme.MUTED if st.door1_sensor not in (1, 2) else theme.TEXT)

    def _update_counters(self) -> None:
        self.stat_scans.set_value(str(self._granted + self._denied))
        self.stat_ok_deny.set_parts((str(self._granted), theme.SUCCESS), (" / ", theme.FAINT),
                                    (str(self._denied), theme.DANGER))
        n = len(self._events)
        self.tabs.tab(0, text=f"Sự kiện quét QR ({n})" if n else "Sự kiện quét QR")

    def _show_qr_detail(self, iid: str) -> None:
        e = self._event_of.get(iid)
        if e is None:
            return
        try:
            QrDetailDialog(self.root, e)
        except ValueError as ex:
            # Nội dung quá dài so với dung lượng tối đa của QR.
            self.logger.warn(f"Không tạo được mã QR cho {e.code}: {ex}")
            messagebox.showwarning("Mã QR", f"Không tạo được mã QR cho nội dung này.\n{ex}", parent=self.root)

    # ---------------------------------------------------------------- cài đặt xác thực

    def _open_verify_settings(self) -> None:
        dlg = VerifySettingsDialog(self.root, self.settings.verify, lambda: self._device_serial)
        self.root.wait_window(dlg)
        if dlg.result is None:
            return
        self.settings.verify = dlg.result
        self.settings.save()
        self._update_verify_info()
        v = self.settings.verify
        self.logger.info(f"Đã lưu cấu hình Verify API: {v.method} {v.url}" if v.is_configured
                         else "Đã lưu cấu hình xác thực: hỏi thủ công (popup)")

    def _update_verify_info(self) -> None:
        v = self.settings.verify
        if v.is_configured:
            self.pill_verify.set("Verify API", (theme.PRIMARY_TINT, theme.PRIMARY_TEXT))
            self.lbl_verify_url.configure(text=f"{v.method} {v.url}")
        else:
            self.pill_verify.set("Hỏi thủ công", (theme.WARNING_TINT, theme.WARNING_TEXT))
            self.lbl_verify_url.configure(text="URL chưa hợp lệ" if v.enabled else "Popup hỏi mở cửa")

    # ---------------------------------------------------------------- tab, CSV, log

    def _on_tab_changed(self) -> None:
        if self.tabs.index("current") == 1:
            self.chk_debug.pack(side="right", padx=(0, 12))
            self.txt_log.see("end")
        else:
            self.chk_debug.pack_forget()

    def _export_csv(self) -> None:
        if not self._events:
            messagebox.showinfo("Xuất CSV", "Chưa có sự kiện nào.", parent=self.root)
            return
        path = filedialog.asksaveasfilename(parent=self.root, defaultextension=".csv", filetypes=[("CSV", "*.csv")],
                                            initialfile=f"qr_events_{datetime.now():%Y%m%d_%H%M%S}.csv")
        if not path:
            return
        try:
            EventCsvWriter.export(path, reversed(self._events))
            self.logger.info(f"Đã xuất {len(self._events)} sự kiện ra {path}")
        except OSError as ex:
            messagebox.showerror("Xuất CSV", str(ex), parent=self.root)

    def _clear_current_tab(self) -> None:
        if self.tabs.index("current") == 0:
            self._events.clear()
            self._iid_of.clear()
            self._event_of.clear()
            self.grid_events.delete(*self.grid_events.get_children())
            self._granted = self._denied = 0
            self._update_counters()
        else:
            self._log_history.clear()
            self._redraw_log()

    def _append_log(self, e: LogEntry) -> None:
        self._log_history.append(e)
        if len(self._log_history) > MAX_LOG_LINES:
            del self._log_history[:len(self._log_history) - MAX_LOG_LINES]
            self._redraw_log()
            return
        self.txt_log.configure(state="normal")
        self._write_log_line(e)
        self.txt_log.configure(state="disabled")
        self.txt_log.see("end")

    def _redraw_log(self) -> None:
        self.txt_log.configure(state="normal")
        self.txt_log.delete("1.0", "end")
        for e in self._log_history:
            self._write_log_line(e)
        self.txt_log.configure(state="disabled")
        self.txt_log.see("end")

    def _write_log_line(self, e: LogEntry) -> None:
        if e.level == LogLevel.DEBUG and not self.v_debug.get():
            return
        self.txt_log.insert("end", f"{e.time:%H:%M:%S}.{e.time.microsecond // 1000:03d}  ", "time")
        self.txt_log.insert("end", e.level.name.ljust(7), e.level.name)
        self.txt_log.insert("end", e.message + "\n")

    # ---------------------------------------------------------------- tiện ích

    def _open_log_dir(self) -> None:
        if hasattr(os, "startfile"):
            os.startfile(self.log_dir)
        else:
            messagebox.showinfo("Thư mục log", str(self.log_dir), parent=self.root)

    def _about(self) -> None:
        messagebox.showinfo("Giới thiệu", (
            "ZKTeco C3-100 Manager (Python)\n"
            "Kết nối qua PullSDK (plcommpro.dll), ghi sự kiện quét QR và log kết nối.\n\n"
            "Phím tắt: F5 kết nối · Shift+F5 ngắt kết nối · Ctrl+S xuất CSV"), parent=self.root)

    def _load_settings(self) -> None:
        s = self.settings
        self.v_ip.set(s.ip)
        self.v_port.set(str(max(1, min(65535, s.port))))
        self.v_timeout.set(str(max(1000, min(30000, s.timeout_ms))))
        self.v_poll.set(str(max(100, min(10000, s.poll_interval_ms))))
        self.v_open_seconds.set(str(max(1, min(254, s.open_seconds))))
        self.v_auto.set(s.auto_reconnect)

    def _save_settings(self) -> None:
        s = self.settings
        s.ip = self.v_ip.get().strip()
        s.port = int_of(self.v_port, 1, 65535, 4370)
        s.timeout_ms = int_of(self.v_timeout, 1000, 30000, 4000)
        s.poll_interval_ms = int_of(self.v_poll, 100, 10000, 500)
        s.open_seconds = int_of(self.v_open_seconds, 1, 254, 5)
        s.auto_reconnect = self.v_auto.get()
        s.save()

    def _on_close(self) -> None:
        if self._closing:
            return
        self._closing = True
        self._save_settings()
        if self.device.state == ConnectionState.DISCONNECTED:
            self._destroy()
            return
        # Ngắt kết nối gọn gàng trước khi đóng cửa sổ.
        self.root.title(self.root.title() + " — đang ngắt kết nối...")
        self._run_bg(self.device.disconnect, lambda _: self._destroy())

    def _destroy(self) -> None:
        self.device.close()
        self._destroyed = True
        self.root.destroy()


def run(simulate: bool = False, sdk_dir: str | None = None) -> int:
    root = tk.Tk()
    MainWindow(root, simulate=simulate, sdk_dir=sdk_dir)
    root.mainloop()
    return 0
