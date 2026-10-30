"""
Dòng lệnh:  python -m zkc3 [lệnh] [tuỳ chọn]

  gui                 Mở giao diện (mặc định khi không có lệnh)
  info                In thông tin thiết bị
  open / close        Mở / đóng cửa
  sync-time           Đồng bộ giờ PC → thiết bị
  monitor             In sự kiện thời gian thực cho tới khi Ctrl+C
  table <tên>         In một bảng dữ liệu (user, userauthorize, transaction...)
"""

from __future__ import annotations

import argparse
import sys
import threading
from functools import partial

from .controller import C3Controller
from .logger import AppLogger
from .models import ConnectionSettings, LogLevel
from .rtlog import is_scan_event
from .sdk import PullSdk
from .settings import AppSettings, home_dir


def main(argv: list[str] | None = None) -> int:
    # Khi chuyển hướng ra file/pipe, Windows mặc định dùng cp1252 và không in được tiếng Việt.
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    saved = AppSettings.load()

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--ip", default=saved.ip, help=f"IP thiết bị (mặc định {saved.ip})")
    common.add_argument("--port", type=int, default=saved.port)
    common.add_argument("--timeout", type=int, default=saved.timeout_ms, help="Timeout kết nối (ms)")
    common.add_argument("--password", default="", help="Comm key, để trống nếu không đặt")
    common.add_argument("--sdk-dir", help="Thư mục chứa plcommpro.dll (mặc định ./sdk)")
    common.add_argument("--simulate", action="store_true", help="Dùng thiết bị giả lập, không cần DLL")
    common.add_argument("-v", "--verbose", action="store_true", help="In cả log DEBUG")

    p = argparse.ArgumentParser(prog="zkc3", description="ZKTeco C3-100 qua PullSDK", parents=[common])
    sub = p.add_subparsers(dest="command")
    sub.add_parser("gui", parents=[common], help="Mở giao diện")
    sub.add_parser("info", parents=[common], help="In thông tin thiết bị")
    op = sub.add_parser("open", parents=[common], help="Mở cửa")
    op.add_argument("--door", type=int, default=1)
    op.add_argument("--seconds", type=int, default=saved.open_seconds, help="1..254, 255 = mở thường trực")
    cl = sub.add_parser("close", parents=[common], help="Đóng cửa")
    cl.add_argument("--door", type=int, default=1)
    sub.add_parser("sync-time", parents=[common], help="Đồng bộ giờ PC → thiết bị")
    mon = sub.add_parser("monitor", parents=[common], help="In sự kiện thời gian thực")
    mon.add_argument("--poll", type=int, default=saved.poll_interval_ms, help="Chu kỳ đọc (ms)")
    tb = sub.add_parser("table", parents=[common], help="In một bảng dữ liệu")
    tb.add_argument("name", help="user, userauthorize, holiday, timezone, transaction, firstcard...")
    tb.add_argument("--fields", default="*")
    tb.add_argument("--filter", default="")

    args = p.parse_args(argv)

    if args.command in (None, "gui"):
        from .gui.main_window import run
        return run(simulate=args.simulate, sdk_dir=args.sdk_dir)

    log = AppLogger(home_dir() / "logs")
    min_level = LogLevel.DEBUG if args.verbose else LogLevel.INFO
    log.subscribe(lambda e: e.level >= min_level and print(f"{e.level.name:<5} {e.message}", file=sys.stderr))

    device = C3Controller(log, _sdk_factory(args))
    settings = ConnectionSettings(args.ip, args.port, args.timeout, args.password,
                                  getattr(args, "poll", saved.poll_interval_ms), auto_reconnect=True)

    with device:
        if args.command == "monitor":
            return _monitor(device, settings)

        if not device.connect(settings):
            return 1
        if args.command == "info":
            info = device.refresh_device_info()
            if info is None:
                return 1
            dt = f"{info.device_time:%Y-%m-%d %H:%M:%S}" if info.device_time else "?"
            print(f"Serial:   {info.serial}\nFirmware: {info.firmware}\nSố cửa:   {info.lock_count}\nGiờ:      {dt}")
            return 0
        if args.command == "open":
            return 0 if device.set_door(args.door, args.seconds) else 1
        if args.command == "close":
            return 0 if device.set_door(args.door, 0) else 1
        if args.command == "sync-time":
            return 0 if device.sync_time() else 1
        if args.command == "table":
            rows = device.get_table(args.name, args.fields, args.filter)
            if rows is None:
                return 1
            _print_table(rows)
            return 0
    return 0


def _sdk_factory(args):
    if args.simulate:
        from .simulator import FakePullSdk
        return FakePullSdk
    return partial(PullSdk, args.sdk_dir)


def _monitor(device: C3Controller, settings: ConnectionSettings) -> int:
    def on_events(events):
        for e in events:
            if is_scan_event(e):
                print(f"{e.time:%Y-%m-%d %H:%M:%S}  cửa {e.door} ({e.direction})  mã={e.code}  PIN={e.pin}  {e.event_name}",
                      flush=True)
            else:
                print(f"{e.time:%Y-%m-%d %H:%M:%S}  cửa {e.door}: {e.event_name}", flush=True)

    device.events_received.connect(on_events)
    if not device.connect(settings):
        return 1
    print("Đang theo dõi sự kiện, Ctrl+C để dừng...", file=sys.stderr)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    return 0


def _print_table(rows: list[dict[str, str]]) -> None:
    if not rows:
        print("(không có bản ghi)")
        return
    header = list(rows[0].keys())
    widths = [max(len(h), *(len(r.get(h, "")) for r in rows)) for h in header]
    print("  ".join(h.ljust(w) for h, w in zip(header, widths)))
    print("  ".join("-" * w for w in widths))
    for r in rows:
        print("  ".join(r.get(h, "").ljust(w) for h, w in zip(header, widths)))
    print(f"\n{len(rows)} bản ghi")
