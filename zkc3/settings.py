from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from .models import VerifyApiSettings


def home_dir() -> Path:
    """Thư mục chứa settings.json và logs/: $ZKC3_HOME hoặc thư mục hiện tại."""
    return Path(os.environ.get("ZKC3_HOME") or Path.cwd())


@dataclass
class AppSettings:
    """Lưu thông số kết nối gần nhất vào settings.json."""

    ip: str = "192.168.1.201"
    port: int = 4370
    timeout_ms: int = 4000
    poll_interval_ms: int = 500
    auto_reconnect: bool = True
    open_seconds: int = 5
    verify: VerifyApiSettings = field(default_factory=VerifyApiSettings)

    @staticmethod
    def file_path() -> Path:
        return home_dir() / "settings.json"

    @classmethod
    def load(cls) -> AppSettings:
        try:
            data = json.loads(cls.file_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        if not isinstance(data, dict):
            return cls()
        verify = _from_dict(VerifyApiSettings, data.pop("verify", None))
        s = _from_dict(cls, data)
        s.verify = verify
        return s

    def save(self) -> None:
        try:
            self.file_path().write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass


def _from_dict(cls, data):
    """Bỏ qua khoá lạ và khoá sai kiểu để file settings cũ/hỏng không làm app không mở được."""
    obj = cls()
    if not isinstance(data, dict):
        return obj
    for f in fields(cls):
        if f.name in data and type(data[f.name]) is type(getattr(obj, f.name)):
            setattr(obj, f.name, data[f.name])
    return obj
