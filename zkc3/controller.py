"""
Quản lý kết nối tới C3-100 qua PullSDK: kết nối, polling GetRTLog, tự kết nối lại,
điều khiển cửa. Mọi lời gọi SDK đi qua một khoá duy nhất vì plcommpro.dll không thread-safe.

Các method đều chặn (blocking); UI nên gọi chúng từ thread phụ. Callback được gọi
từ thread polling.
"""

from __future__ import annotations

import ctypes
import threading
import time
from datetime import datetime
from enum import Enum
from typing import Callable, Generic, TypeVar

from . import rtlog
from .device_time import decode_device_time, encode_device_time
from .logger import AppLogger
from .models import AccessEvent, ConnectionSettings, DeviceInfo, DoorStatus
from .sdk import PullSdk, SdkLoadError, describe_error

T = TypeVar("T")

NO_HANDLE = -999


class ConnectionState(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"


class Signal(Generic[T]):
    """Danh sách callback. Lỗi trong một callback được báo qua ``on_error`` thay vì làm chết thread polling."""

    def __init__(self, on_error: Callable[[Exception], None] | None = None) -> None:
        self._handlers: list[Callable[[T], None]] = []
        self._on_error = on_error

    def connect(self, handler: Callable[[T], None]) -> None:
        self._handlers.append(handler)

    def emit(self, value: T) -> None:
        for h in self._handlers:
            try:
                h(value)
            except Exception as ex:  # noqa: BLE001
                if self._on_error is None:
                    raise
                self._on_error(ex)


class C3Controller:
    MAX_POLL_FAILURES = 3
    RECONNECT_DELAY_S = 3.0
    RT_BUFFER_SIZE = 256 * 1024

    def __init__(self, log: AppLogger, sdk_factory: Callable[[], PullSdk] = PullSdk):
        self._log = log
        self._sdk_factory = sdk_factory
        self._sdk: PullSdk | None = None
        self._gate = threading.RLock()
        self._rt_buffer = ctypes.create_string_buffer(self.RT_BUFFER_SIZE)

        self._handle = 0
        self._stop = threading.Event()
        self._poll_thread: threading.Thread | None = None
        self._settings: ConnectionSettings | None = None
        self._state = ConnectionState.DISCONNECTED

        on_error = lambda ex: self._log.error(f"Lỗi trong callback: {type(ex).__name__}: {ex}")  # noqa: E731
        self.state_changed: Signal[ConnectionState] = Signal(on_error)
        self.events_received: Signal[list[AccessEvent]] = Signal(on_error)
        self.status_received: Signal[DoorStatus] = Signal(on_error)
        self.device_info_received: Signal[DeviceInfo] = Signal(on_error)

    @property
    def state(self) -> ConnectionState:
        return self._state

    @property
    def is_connected(self) -> bool:
        return self._state == ConnectionState.CONNECTED

    @property
    def settings(self) -> ConnectionSettings | None:
        return self._settings

    def connect(self, settings: ConnectionSettings) -> bool:
        if self._state != ConnectionState.DISCONNECTED:
            return self.is_connected

        self._settings = settings
        self._set_state(ConnectionState.CONNECTING)
        self._log.info(f"Kết nối: {settings.to_safe_string()}")

        if not self._try_open(settings):
            self._set_state(ConnectionState.DISCONNECTED)
            return False

        self._set_state(ConnectionState.CONNECTED)
        self.refresh_device_info()
        self._start_polling()
        return True

    def disconnect(self) -> None:
        if self._state == ConnectionState.DISCONNECTED:
            return
        self._stop_polling()
        self._close_handle()
        self._log.info("Đã ngắt kết nối")
        self._set_state(ConnectionState.DISCONNECTED)

    def refresh_device_info(self) -> DeviceInfo | None:
        items = "~SerialNumber,FirmVer,LockCount,DateTime"
        self._log.debug(f"GetDeviceParam {items}")

        ret, text = self._call(lambda sdk, h: sdk.get_device_param(h, items), (NO_HANDLE, ""))
        if ret < 0:
            self._log.warn(f"GetDeviceParam lỗi {ret} (PullLastError={self._last_error()})")
            return None

        values = parse_key_values(text)
        info = DeviceInfo(
            serial=values.get("~serialnumber", "?"),
            firmware=values.get("firmver", "?"),
            lock_count=_to_int(values.get("lockcount", "")),
            device_time=decode_device_time(_to_int(values["datetime"])) if "datetime" in values else None,
        )
        dt = f"{info.device_time:%Y-%m-%d %H:%M:%S}" if info.device_time else "?"
        self._log.info(f"Thiết bị: SN={info.serial}, FW={info.firmware}, LockCount={info.lock_count}, Giờ={dt}")
        self.device_info_received.emit(info)
        return info

    def sync_time(self) -> bool:
        now = datetime.now()
        ret = self._call(lambda sdk, h: sdk.set_device_param(h, f"DateTime={encode_device_time(now)}"), NO_HANDLE)
        if ret < 0:
            self._log.error(f"Đồng bộ giờ thất bại: {ret} (PullLastError={self._last_error()})")
            return False
        self._log.info(f"Đã đồng bộ giờ thiết bị = {now:%Y-%m-%d %H:%M:%S}")
        self.refresh_device_info()
        return True

    def set_door(self, door: int, seconds: int) -> bool:
        """``seconds``: 1..254 giây, 255 = mở thường trực, 0 = đóng."""
        seconds = max(0, min(255, seconds))
        ret = self._call(lambda sdk, h: sdk.control_device(h, 1, door, 1, seconds, 0, ""), NO_HANDLE)
        action = "Đóng" if seconds == 0 else "Mở thường trực" if seconds == 255 else f"Mở {seconds}s"
        if ret < 0:
            self._log.error(f"{action} cửa {door} thất bại: {ret} (PullLastError={self._last_error()})")
            return False
        self._log.info(f"{action} cửa {door}: OK")
        return True

    # ---------------------------------------------------------------- bảng dữ liệu

    def get_table(self, table: str, fields: str = "*", filter: str = "") -> list[dict[str, str]] | None:
        """Đọc một bảng (user, userauthorize, transaction...). Trả về None nếu lỗi."""
        ret, text = self._call(lambda sdk, h: sdk.get_device_data(h, table, fields, filter), (NO_HANDLE, ""))
        if ret < 0:
            self._log.error(f"GetDeviceData {table} lỗi {ret} (PullLastError={self._last_error()})")
            return None
        lines = [ln for ln in text.splitlines() if ln.strip()]
        if not lines:
            return []
        header = lines[0].split(",")
        return [dict(zip(header, ln.split(","))) for ln in lines[1:]]

    def set_table(self, table: str, rows: list[dict[str, object]]) -> bool:
        data = "\r\n".join("\t".join(f"{k}={v}" for k, v in r.items()) for r in rows)
        ret = self._call(lambda sdk, h: sdk.set_device_data(h, table, data, ""), NO_HANDLE)
        if ret < 0:
            self._log.error(f"SetDeviceData {table} lỗi {ret} (PullLastError={self._last_error()})")
            return False
        self._log.info(f"SetDeviceData {table}: {len(rows)} bản ghi")
        return True

    def delete_table(self, table: str, conditions: list[dict[str, object]]) -> bool:
        data = "\r\n".join("\t".join(f"{k}={v}" for k, v in r.items()) for r in conditions)
        ret = self._call(lambda sdk, h: sdk.delete_device_data(h, table, data, ""), NO_HANDLE)
        if ret < 0:
            self._log.error(f"DeleteDeviceData {table} lỗi {ret} (PullLastError={self._last_error()})")
            return False
        self._log.info(f"DeleteDeviceData {table}: {len(conditions)} điều kiện")
        return True

    # ---------------------------------------------------------------- polling

    def _start_polling(self) -> None:
        # Vòng polling cũ có thể đã tự kết thúc (mất kết nối, không bật tự kết nối lại).
        self._stop = threading.Event()
        self._poll_thread = threading.Thread(target=self._poll_loop, args=(self._stop,), name="c3-poll", daemon=True)
        self._poll_thread.start()
        self._log.info(f"Bắt đầu polling GetRTLog mỗi {self._settings.poll_interval_ms} ms")

    def _stop_polling(self) -> None:
        if self._poll_thread is None:
            return
        self._stop.set()
        if self._poll_thread is not threading.current_thread():
            self._poll_thread.join()
        self._poll_thread = None
        self._log.info("Dừng polling")

    def _poll_loop(self, stop: threading.Event) -> None:
        failures = 0
        while not stop.is_set():
            ret, raw = self._call(lambda sdk, h: sdk.get_rt_log(h, self._rt_buffer), (NO_HANDLE, ""))

            if ret >= 0:
                if failures > 0:
                    self._log.info("GetRTLog đã phục hồi")
                failures = 0
                self._handle_rt_log(raw)
            else:
                failures += 1
                self._log.warn(f"GetRTLog trả về {ret}, lỗi {failures}/{self.MAX_POLL_FAILURES}")
                if failures >= self.MAX_POLL_FAILURES:
                    self._log.error("Mất kết nối với thiết bị")
                    if not self._settings.auto_reconnect:
                        self._close_handle()
                        self._poll_thread = None
                        self._set_state(ConnectionState.DISCONNECTED)
                        return
                    self._reconnect(stop)
                    failures = 0

            stop.wait(self._settings.poll_interval_ms / 1000)

    def _handle_rt_log(self, raw: str) -> None:
        if not raw.strip():
            return
        events, statuses = rtlog.parse(raw)
        for e in events:
            self._log.debug(f"RTLog: {e.raw}")
        if events:
            self.events_received.emit(events)
        if statuses:
            self.status_received.emit(statuses[-1])

    def _reconnect(self, stop: threading.Event) -> None:
        self._set_state(ConnectionState.RECONNECTING)
        self._close_handle()

        attempt = 1
        while not stop.is_set():
            self._log.info(f"Thử kết nối lại lần {attempt}...")
            if self._try_open(self._settings):
                self._set_state(ConnectionState.CONNECTED)
                self.refresh_device_info()
                return
            stop.wait(self.RECONNECT_DELAY_S)
            attempt += 1

    # ---------------------------------------------------------------- SDK helpers

    def _try_open(self, s: ConnectionSettings) -> bool:
        started = time.monotonic()
        with self._gate:
            try:
                if self._sdk is None:
                    self._sdk = self._sdk_factory()
            except SdkLoadError as ex:
                self._log.error(str(ex))
                return False

            handle = self._sdk.connect(s.to_connect_string())
            last_error = self._sdk.pull_last_error() if not handle else 0
            self._handle = handle

        elapsed = int((time.monotonic() - started) * 1000)
        if not handle:
            self._log.error(f"Connect thất bại sau {elapsed} ms, PullLastError={last_error} ({describe_error(last_error)})")
            return False

        self._log.info(f"Connect OK, handle=0x{handle:08X} ({elapsed} ms)")
        return True

    def _close_handle(self) -> None:
        with self._gate:
            if not self._handle:
                return
            h, self._handle = self._handle, 0
            self._sdk.disconnect(h)
        self._log.info(f"Disconnect handle=0x{h:08X}")

    def _call(self, fn: Callable[[PullSdk, int], T], no_handle: T) -> T:
        """Gọi một hàm SDK cần handle, tuần tự hoá qua khoá. Trả về ``no_handle`` nếu chưa có handle."""
        with self._gate:
            if not self._handle:
                return no_handle
            return fn(self._sdk, self._handle)

    def _last_error(self) -> int:
        with self._gate:
            return self._sdk.pull_last_error() if self._sdk else 0

    def _set_state(self, s: ConnectionState) -> None:
        if self._state == s:
            return
        self._state = s
        self.state_changed.emit(s)

    def close(self) -> None:
        """Giải phóng khi thoát ứng dụng."""
        self._stop.set()
        if self._poll_thread and self._poll_thread is not threading.current_thread():
            self._poll_thread.join(2)
        with self._gate:
            if self._handle and self._sdk:
                try:
                    self._sdk.disconnect(self._handle)
                except OSError:
                    pass  # đang thoát ứng dụng
            self._handle = 0

    def __enter__(self) -> C3Controller:
        return self

    def __exit__(self, *exc) -> None:
        self.disconnect()
        self.close()


def parse_key_values(s: str) -> dict[str, str]:
    """``"a=1,B=2"`` → ``{"a": "1", "b": "2"}`` (khoá viết thường)."""
    result = {}
    for part in s.split(","):
        k, sep, v = part.partition("=")
        if sep and k.strip():
            result[k.strip().lower()] = v.strip()
    return result


def _to_int(s: str) -> int:
    try:
        return int(s.strip())
    except ValueError:
        return 0
