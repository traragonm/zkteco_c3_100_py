from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum
from urllib.parse import urlparse


class LogLevel(IntEnum):
    DEBUG = 0
    INFO = 1
    WARN = 2
    ERROR = 3


@dataclass(frozen=True)
class LogEntry:
    time: datetime
    level: LogLevel
    message: str

    def __str__(self) -> str:
        return f"{self.time:%Y-%m-%d %H:%M:%S}.{self.time.microsecond // 1000:03d} [{self.level.name}] {self.message}"


@dataclass(eq=False)
class AccessEvent:
    """Một sự kiện quét QR/thẻ đọc được từ GetRTLog. So sánh theo đối tượng (eq=False)."""

    time: datetime
    door: int = 0
    direction: str = ""
    code: str = ""
    pin: str = ""
    event_type: int = 0
    event_name: str = ""
    verify_type: int = 0
    granted: bool = False
    """Controller đã cho phép (thẻ/QR đăng ký trên thiết bị)."""
    raw: str = ""

    # Kết quả cuối cùng sau khi xác thực bằng API / người vận hành.
    pending: bool = False
    door_opened: bool = False
    verify_note: str = ""

    @property
    def door_text(self) -> str:
        return f"{self.door} · {self.direction}"

    @property
    def result(self) -> str:
        return "Chờ xác thực" if self.pending else "Mở cửa" if self.door_opened else "Từ chối"


@dataclass(frozen=True)
class DoorStatus:
    """Bản ghi trạng thái (eventtype = 255) mà C3 trả về định kỳ."""

    time: datetime
    door1_sensor: int
    """0 = không có sensor, 1 = đóng, 2 = mở."""
    alarm: int


@dataclass(frozen=True)
class DeviceInfo:
    serial: str
    firmware: str
    lock_count: int
    device_time: datetime | None


@dataclass(frozen=True)
class ConnectionSettings:
    ip: str
    port: int = 4370
    timeout_ms: int = 4000
    password: str = ""
    poll_interval_ms: int = 500
    auto_reconnect: bool = True

    def to_connect_string(self) -> str:
        return f"protocol=TCP,ipaddress={self.ip},port={self.port},timeout={self.timeout_ms},passwd={self.password}"

    def to_safe_string(self) -> str:
        masked = "***" if self.password else ""
        return f"protocol=TCP,ipaddress={self.ip},port={self.port},timeout={self.timeout_ms},passwd={masked}"


DEFAULT_BODY = (
    '{\n  "code": "{code}",\n  "pin": "{pin}",\n  "door": {door},\n  "direction": "{direction}",\n'
    '  "eventType": {eventType},\n  "time": "{time}",\n  "deviceSerial": "{deviceSerial}"\n}'
)


@dataclass
class VerifyApiSettings:
    """
    Cấu hình gọi API xác thực QR/Card. URL, Headers và Body là template:
    {code} {pin} {door} {direction} {eventType} {eventName} {time} {deviceSerial}.
    """

    enabled: bool = False
    method: str = "POST"
    url: str = ""
    headers: str = "Content-Type: application/json"
    """Mỗi dòng một header dạng "Tên: Giá trị"."""
    body: str = DEFAULT_BODY
    timeout_ms: int = 3000
    result_field: str = "allow"
    """Đường dẫn tới trường kết quả trong JSON trả về, hỗ trợ dạng lồng "data.allow"."""
    prompt_on_error: bool = True
    """True = API lỗi thì hỏi người vận hành; False = từ chối."""
    skip_granted: bool = True
    """Bỏ qua lượt quét controller đã cho phép (thẻ/QR đã đăng ký trên thiết bị)."""
    open_seconds: int = 5
    duplicate_window_seconds: int = 3
    prompt_timeout_seconds: int = 20

    @property
    def is_configured(self) -> bool:
        if not self.enabled:
            return False
        u = urlparse(self.url.strip())
        return u.scheme in ("http", "https") and bool(u.netloc)

    def clone(self) -> VerifyApiSettings:
        return copy.copy(self)
