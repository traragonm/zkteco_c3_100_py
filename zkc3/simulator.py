"""
Thiết bị C3-100 giả lập, cùng giao diện với :class:`zkc3.sdk.PullSdk`.
Dùng để chạy thử GUI/CLI và viết test khi không có thiết bị hoặc không có DLL.
"""

from __future__ import annotations

import ctypes
import random
import threading
import time
from datetime import datetime, timedelta

from .controller import parse_key_values
from .device_time import decode_device_time, encode_device_time

_SAMPLE_CODES = ["QR-8F21A0C4", "QR-1B77E903", "12345678", "GUEST-2026-0042", "QR-C0FFEE01"]


class FakePullSdk:
    def __init__(self, scan_interval: float = 4.0, seed: int | None = None):
        self.scan_interval = scan_interval
        self._rnd = random.Random(seed)
        self._lock = threading.Lock()
        self._next_handle = 0x1000
        self._handles: set[int] = set()
        self._clock_offset = timedelta()
        self._next_scan = time.monotonic() + 1.0
        self._door_open_until = 0.0
        self._pending: list[str] = []
        self._last_error = 0
        self.users = [
            {"CardNo": "12345678", "Pin": "1", "Password": "", "Group": "0", "StartTime": "0", "EndTime": "0", "Name": "Nguyen Van A"},
        ]

    # ------------------------------------------------------------ kết nối

    def connect(self, parameters: str) -> int:
        values = parse_key_values(parameters)
        if not values.get("ipaddress"):
            self._last_error = -307
            return 0
        with self._lock:
            self._next_handle += 1
            self._handles.add(self._next_handle)
            return self._next_handle

    def disconnect(self, handle: int) -> None:
        self._handles.discard(handle)

    def pull_last_error(self) -> int:
        return self._last_error

    # ------------------------------------------------------------ tham số / điều khiển

    def get_device_param(self, handle: int, items: str, buffer_size: int = 4096) -> tuple[int, str]:
        if handle not in self._handles:
            return -1, ""
        now = datetime.now() + self._clock_offset
        values = {
            "~SerialNumber": "SIM-C3100-0001",
            "FirmVer": "AC Ver 4.7.8 (giả lập)",
            "LockCount": "1",
            "DateTime": str(encode_device_time(now)),
        }
        wanted = [i.strip() for i in items.split(",") if i.strip()]
        return 0, ",".join(f"{k}={values.get(k, '')}" for k in wanted)

    def set_device_param(self, handle: int, item_values: str) -> int:
        if handle not in self._handles:
            return -1
        value = parse_key_values(item_values).get("datetime")
        if value and (t := decode_device_time(int(value))):
            self._clock_offset = t - datetime.now()
        return 0

    def control_device(self, handle: int, operation_id: int, param1: int, param2: int, param3: int,
                       param4: int = 0, options: str = "") -> int:
        if handle not in self._handles:
            return -1
        if operation_id == 1 and param2 == 1:
            stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._door_open_until = 0 if param3 == 0 else time.monotonic() + (10**9 if param3 == 255 else param3)
            self._pending.append(f"{stamp},0,0,{param1},{9 if param3 == 0 else 8},2,200")
        return 0

    # ------------------------------------------------------------ sự kiện

    def get_rt_log(self, handle: int, buffer: ctypes.Array) -> tuple[int, str]:
        if handle not in self._handles:
            return -1, ""
        now = time.monotonic()
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines, self._pending = self._pending, []

        if now >= self._next_scan:
            self._next_scan = now + self.scan_interval * self._rnd.uniform(0.6, 1.4)
            code = self._rnd.choice(_SAMPLE_CODES)
            registered = any(u["CardNo"] == code for u in self.users)
            pin = next((u["Pin"] for u in self.users if u["CardNo"] == code), "0")
            lines.append(f"{stamp},{pin},{code},1,{0 if registered else 27},{self._rnd.choice([0, 0, 1])},4")
            if registered:
                self._door_open_until = now + 3

        sensor = 2 if now < self._door_open_until else 1
        lines.append(f"{stamp},{sensor},0,0,255,0,0")
        return len(lines), "\r\n".join(lines)

    # ------------------------------------------------------------ bảng dữ liệu

    def get_device_data(self, handle: int, table: str, fields: str = "*", filter: str = "",
                        options: str = "", buffer_size: int = 0) -> tuple[int, str]:
        if handle not in self._handles:
            return -1, ""
        if table.lower() != "user":
            return 0, ""
        header = list(self.users[0].keys()) if self.users else ["CardNo", "Pin", "Name"]
        rows = [",".join(u.get(k, "") for k in header) for u in self.users]
        return len(rows), "\r\n".join([",".join(header), *rows])

    def set_device_data(self, handle: int, table: str, data: str, options: str = "") -> int:
        if handle not in self._handles:
            return -1
        if table.lower() == "user":
            for line in data.split("\r\n"):
                row = dict(p.split("=", 1) for p in line.split("\t") if "=" in p)
                self.users = [u for u in self.users if u.get("Pin") != row.get("Pin")] + [row]
        return 0

    def delete_device_data(self, handle: int, table: str, data: str, options: str = "") -> int:
        if handle not in self._handles:
            return -1
        if table.lower() == "user":
            for line in data.split("\r\n"):
                cond = dict(p.split("=", 1) for p in line.split("\t") if "=" in p)
                self.users = [u for u in self.users if any(u.get(k) != v for k, v in cond.items())]
        return 0

    def get_device_data_count(self, handle: int, table: str, filter: str = "", options: str = "") -> int:
        return len(self.users) if table.lower() == "user" else 0
